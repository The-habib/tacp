"""Property-based generative test suite for Phase 5 execution core invariants.

Tests 8 fundamental security and execution invariants over randomized inputs:
1. Argv Validation Invariant
2. Path Normalization Invariant
3. Execution Contract Hashing Invariant
4. Safe Environment Filtering Invariant
5. Output Sanitization Invariant
6. Approval State Machine Invariant
7. Audit Hash Chain Integrity Invariant
8. MCP Request Validation Invariant
"""

import json
import random
import string
from pathlib import Path
from typing import Any, Dict

import pytest

from tacp.access.mcp.protocol import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    PARSE_ERROR,
    McpProtocolError,
    parse_message,
)
from tacp.control.approval import (
    STATUS_APPROVED,
    STATUS_CONSUMED,
    STATUS_DENIED,
    STATUS_PENDING,
    STATUS_REVOKED,
    ApprovalEngine,
)
from tacp.core.audit_service import AuditService
from tacp.core.execution_resolver import ExecutionResolver
from tacp.domain.audit import AuditEvent
from tacp.domain.errors import (
    TacpApprovalRequiredError,
    TacpSecurityError,
    TacpValidationError,
)
from tacp.domain.execution import (
    ExecutionContract,
    NetworkIsolationState,
    compute_execution_contract_hash,
)
from tacp.infrastructure.config import OutputLimits
from tacp.infrastructure.database import Database
from tacp.providers.process_executor import sanitize_output

RNG_SEED = 42


# =========================================================================
# Invariant 1: Argv Validation Invariant
# =========================================================================


def test_property_argv_validation_invariants() -> None:
    """Property: Null bytes, length overflows, and count overflows are strictly rejected,
    while valid inputs are deterministically preserved."""
    rng = random.Random(RNG_SEED)
    limits = OutputLimits(max_argv_count=16, max_arg_length=128)
    resolver = ExecutionResolver(limits=limits)

    # 1. Randomized valid argv sequences must always preserve structure
    for _ in range(50):
        count = rng.randint(1, 15)
        args = ["printf"]
        for _ in range(count - 1):
            arg_len = rng.randint(1, 64)
            arg_str = "".join(
                rng.choice(string.ascii_letters + string.digits + " _-.") for _ in range(arg_len)
            )
            args.append(arg_str)

        res = resolver.validate_argv("printf", args)
        assert res == tuple(args)

    # 2. Any argument containing null bytes must always raise TacpSecurityError
    for _ in range(30):
        count = rng.randint(1, 10)
        args = ["printf"] + [f"arg_{i}" for i in range(count)]
        poison_idx = rng.randint(0, len(args) - 1)
        insert_pos = rng.randint(0, len(args[poison_idx]))
        args[poison_idx] = args[poison_idx][:insert_pos] + "\x00" + args[poison_idx][insert_pos:]

        with pytest.raises(TacpSecurityError):
            resolver.validate_argv("printf", args)

    # 3. Any argument exceeding max_arg_length must raise TacpValidationError
    for _ in range(20):
        long_arg = "a" * rng.randint(129, 300)
        with pytest.raises(TacpValidationError):
            resolver.validate_argv("printf", ["printf", long_arg])

    # 4. Any argv exceeding max_argv_count must raise TacpValidationError
    for _ in range(20):
        excessive = ["printf"] + [f"arg_{i}" for i in range(rng.randint(16, 40))]
        with pytest.raises(TacpValidationError):
            resolver.validate_argv("printf", excessive)


# =========================================================================
# Invariant 2: Path Normalization & Symlink Resolution Invariant
# =========================================================================


def test_property_path_normalization_invariant(tmp_path: Path) -> None:
    """Property: Any resolved working directory must strictly reside within workspace root."""
    rng = random.Random(RNG_SEED)
    ws_root = tmp_path / "workspace_prop"
    ws_root.mkdir(parents=True)
    (ws_root / "subdir").mkdir()
    (ws_root / "nested" / "deep").mkdir(parents=True)

    resolver = ExecutionResolver()

    # Valid relative paths resolve to descendants
    valid_paths = [".", "subdir", "nested", "nested/deep", "./subdir", "nested/../nested/deep"]
    for p in valid_paths:
        resolved = resolver.resolve_working_directory(ws_root, p)
        assert Path(resolved).resolve().is_relative_to(ws_root.resolve())

    # Randomized path traversal attempts must strictly be rejected
    traversal_fragments = ["..", "../..", "../outside", "nested/../../..", "subdir/../../../etc"]
    for _ in range(50):
        parts = [rng.choice(traversal_fragments)]
        depth = rng.randint(1, 5)
        for _ in range(depth):
            parts.append(rng.choice(["..", "foo", "../bar", "../../../baz"]))
        traversal = "/".join(parts)

        with pytest.raises(TacpSecurityError):
            resolver.resolve_working_directory(ws_root, traversal)


# =========================================================================
# Invariant 3: Execution Contract Hashing Determinism & Collision Invariant
# =========================================================================


def test_property_execution_contract_hashing_invariants(tmp_path: Path) -> None:
    """Property: Contract hashing is strictly deterministic and sensitive to every field."""

    def make_contract(**kwargs: Any) -> ExecutionContract:
        default: Dict[str, Any] = {
            "workspace_id": "ws-prop",
            "executable": "/system/bin/printf",
            "argv": ("printf", "hello"),
            "cwd": str(tmp_path),
            "environment": (("KEY1", "VAL1"), ("KEY2", "VAL2")),
            "network_enabled": False,
            "timeout_seconds": 10,
            "max_stdout_bytes": 1024,
            "max_stderr_bytes": 1024,
            "contract_version": 1,
            "executable_digest": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "principal_id": "agent-test",
            "network_state": NetworkIsolationState.NETWORK_DENIED.value,
        }
        default.update(kwargs)
        return ExecutionContract(**default)

    base = make_contract()
    base_hash = compute_execution_contract_hash(base)

    # 1. Determinism: 100 evaluations must match identically
    for _ in range(100):
        h = compute_execution_contract_hash(base)
        assert h == base_hash
        assert len(h) == 64

    # 2. Perturbation sensitivity: Mutating any field changes the hash
    mutations: list[dict[str, Any]] = [
        {"workspace_id": "ws-other"},
        {"executable": "/data/data/com.termux/files/usr/bin/printf"},
        {"argv": ("printf", "hello", "extra")},
        {"cwd": str(tmp_path / "sub")},
        {"environment": (("KEY1", "VAL1"),)},
        {"environment": (("KEY1", "VAL_MUTATED"), ("KEY2", "VAL2"))},
        {"network_enabled": True},
        {"timeout_seconds": 15},
        {"max_stdout_bytes": 2048},
        {"max_stderr_bytes": 2048},
        {"contract_version": 2},
        {"executable_digest": "0" * 64},
        {"principal_id": "other-principal"},
        {"network_state": NetworkIsolationState.NETWORK_ALLOWED.value},
    ]

    for mutation in mutations:
        mutated_contract = make_contract(**mutation)
        mutated_hash = compute_execution_contract_hash(mutated_contract)
        assert mutated_hash != base_hash, f"Hash collision for mutation: {mutation}"


# =========================================================================
# Invariant 4: Safe Environment Filtering Invariant
# =========================================================================


def test_property_safe_environment_filtering_invariants(tmp_path: Path) -> None:
    """Property: No denylisted variable, prefix, or malicious override ever escapes
    into the environment."""
    rng = random.Random(RNG_SEED)
    resolver = ExecutionResolver()
    ws_root = tmp_path / "ws_env"
    ws_root.mkdir(parents=True)

    denylisted_exact = [
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "DYLD_LIBRARY_PATH",
        "DYLD_INSERT_LIBRARIES",
        "PYTHONPATH",
        "PYTHONHOME",
        "RUBYLIB",
        "PERL5LIB",
        "SHELL",
        "IFS",
        "PROMPT_COMMAND",
        "BASH_ENV",
        "ENV",
        "PAGER",
        "EDITOR",
        "VISUAL",
        "TERMUX_APK_RELEASE",
        "AWS_SECRET_ACCESS_KEY",
        "GITHUB_TOKEN",
        "OPENAI_API_KEY",
    ]

    for _ in range(50):
        caller_env: Dict[str, str] = {}
        # Add random safe variables with USER_ or APP_ prefix
        for _ in range(rng.randint(2, 5)):
            prefix = rng.choice(["USER_", "APP_", "CUSTOM_"])
            safe_k = prefix + "".join(rng.choice(string.ascii_uppercase) for _ in range(4))
            safe_v = "".join(rng.choice(string.ascii_letters + string.digits) for _ in range(10))
            caller_env[safe_k] = safe_v

        # Inject denylisted exact matches
        chosen_deny = rng.sample(denylisted_exact, k=rng.randint(2, 6))
        for d in chosen_deny:
            caller_env[d] = "malicious_val"

        # Inject dangerous prefix variables
        caller_env["LD_INJECT_" + str(rng.randint(100, 999))] = "bad_so"
        caller_env["DYLD_FAKE_" + str(rng.randint(100, 999))] = "bad_dylib"

        clean = dict(resolver.assemble_environment(ws_root, str(ws_root), caller_env))

        # Check: zero denylisted keys present
        for d in denylisted_exact:
            assert d not in clean

        # Check: zero dangerous prefixes present
        for k in clean:
            assert not k.startswith("LD_")
            assert not k.startswith("DYLD_")
            assert not k.startswith("LIBPATH_")

        # Mandatory system variables present
        assert "PATH" in clean
        assert clean["HOME"] == str(ws_root.resolve())
        assert clean["PWD"] == str(ws_root)
        assert clean["TERM"] == "dumb"


# =========================================================================
# Invariant 5: Output Sanitization Invariant
# =========================================================================


def test_property_output_sanitization_invariants() -> None:
    """Property: Output sanitization guarantees zero ESC chars, zero nulls, and
    normalized newlines."""
    rng = random.Random(RNG_SEED)

    ansi_codes = [
        "\x1b[0m",
        "\x1b[31m",
        "\x1b[1;32m",
        "\x1b[2J",
        "\x1b[H",
        "\x1b[?25l",
        "\x1b]0;Evil Terminal Title\x07",
    ]

    for _ in range(50):
        chunks = []
        for _ in range(rng.randint(5, 15)):
            choice = rng.choice(["ascii", "ansi", "null", "newline", "cr"])
            if choice == "ascii":
                chunks.append("".join(rng.choice(string.ascii_letters + " ") for _ in range(10)))
            elif choice == "ansi":
                chunks.append(rng.choice(ansi_codes))
            elif choice == "null":
                chunks.append("\x00")
            elif choice == "newline":
                chunks.append("\n")
            elif choice == "cr":
                chunks.append("\r\n")

        raw = "".join(chunks)
        sanitized = sanitize_output(raw)

        assert "\x1b" not in sanitized
        assert "\x00" not in sanitized
        assert "\r\n" not in sanitized
        assert "\r" not in sanitized


# =========================================================================
# Invariant 6: Approval State Machine Invariant
# =========================================================================


def test_property_approval_state_machine_invariants(tmp_path: Path) -> None:
    """Property: State machine transitions obey strict one-way lifecycle and terminality."""
    rng = random.Random(RNG_SEED)
    db = Database(tmp_path / "approval_prop.db")
    engine = ApprovalEngine(db)

    for i in range(25):
        clean_target = f"target_path_{i}"
        ticket = engine.create_ticket(
            principal_id="test-agent",
            action_type="execution.request",
            workspace_id=f"ws-{i}",
            target_path=clean_target,
            patch_hash=f"hash-{i}",
        )
        assert ticket.status == STATUS_PENDING

        outcome = rng.choice(["approve_consume", "deny", "revoke"])
        if outcome == "approve_consume":
            app = engine.approve(ticket.token, approved_by="operator")
            assert app.status == STATUS_APPROVED

            # Cannot approve twice (PENDING -> APPROVED only)
            with pytest.raises(TacpSecurityError):
                engine.approve(ticket.token, approved_by="operator")

            # Consume
            consumed = engine.verify_and_consume(
                token=ticket.token,
                principal_id="test-agent",
                action_type="execution.request",
                workspace_id=f"ws-{i}",
                target_path=clean_target,
                patch_hash=f"hash-{i}",
            )
            assert consumed is True

            # Re-fetch ticket to check status
            t_consumed = engine.get_ticket(ticket.token)
            assert t_consumed is not None
            assert t_consumed.status == STATUS_CONSUMED

            # Cannot consume twice
            with pytest.raises(TacpSecurityError):
                engine.verify_and_consume(
                    token=ticket.token,
                    principal_id="test-agent",
                    action_type="execution.request",
                    workspace_id=f"ws-{i}",
                    target_path=clean_target,
                    patch_hash=f"hash-{i}",
                )

        elif outcome == "deny":
            denied = engine.deny(ticket.token, reason="security rejection")
            assert denied.status == STATUS_DENIED

            # Cannot approve denied ticket
            with pytest.raises(TacpSecurityError):
                engine.approve(ticket.token, approved_by="operator")

            # Cannot consume denied ticket
            with pytest.raises(TacpApprovalRequiredError):
                engine.verify_and_consume(
                    token=ticket.token,
                    principal_id="test-agent",
                    action_type="execution.request",
                    workspace_id=f"ws-{i}",
                    target_path=clean_target,
                    patch_hash=f"hash-{i}",
                )

        elif outcome == "revoke":
            revoked = engine.revoke(ticket.token, reason="revoked by admin")
            assert revoked.status == STATUS_REVOKED

            # Cannot approve revoked ticket
            with pytest.raises(TacpSecurityError):
                engine.approve(ticket.token, approved_by="operator")


# =========================================================================
# Invariant 7: Audit Hash Chain Integrity Invariant
# =========================================================================


def test_property_audit_hash_chain_integrity_invariants(tmp_path: Path) -> None:
    """Property: Tampering with any event, hash, or order strictly invalidates the chain."""
    rng = random.Random(RNG_SEED)
    db = Database(tmp_path / "audit_prop.db")
    audit = AuditService(db)

    # Generate 15 audit events
    for i in range(15):
        event = AuditEvent(
            capability="execution.request",
            action=f"action_{i}",
            policy_decision="ALLOW",
            result="SUCCESS",
            duration_ms=rng.randint(1, 100),
            principal=f"principal_{i % 3}",
            request_id=f"req_{i}",
            workspace_id="ws-prop",
            parameters_redacted={"idx": i},
        )
        audit.record_event(event)

    assert audit.verify_integrity() is True

    # Mutate a random row in the database
    conn = db.connect()
    with conn:
        row_id_to_tamper = rng.randint(1, 15)
        conn.execute(
            "UPDATE audit_logs SET policy_decision = 'DENIED' WHERE rowid = ?",
            (row_id_to_tamper,),
        )

    assert audit.verify_integrity() is False


# =========================================================================
# Invariant 8: MCP Protocol & Request Parsing Invariant
# =========================================================================


def test_property_mcp_request_validation_invariants() -> None:
    """Property: Protocol parser strictly rejects invalid JSON, non-object payloads,
    missing method, or malformed params."""
    rng = random.Random(RNG_SEED)

    # 1. Invalid JSON bytes
    for _ in range(25):
        garbage = "".join(rng.choice('{}[],:"' + string.ascii_letters) for _ in range(15))
        try:
            json.loads(garbage)
        except Exception:
            with pytest.raises(McpProtocolError) as exc:
                parse_message(garbage)
            assert exc.value.code == PARSE_ERROR

    # 2. Non-object root
    non_objects = ["[]", '"a string"', "12345", "true", "null"]
    for no in non_objects:
        with pytest.raises(McpProtocolError) as exc:
            parse_message(no)
        assert exc.value.code == INVALID_REQUEST

    # 3. Missing or invalid jsonrpc version
    invalid_versions = [
        json.dumps({"id": 1, "method": "test"}),
        json.dumps({"jsonrpc": "1.0", "id": 1, "method": "test"}),
        json.dumps({"jsonrpc": 2.0, "id": 1, "method": "test"}),
    ]
    for inv in invalid_versions:
        with pytest.raises(McpProtocolError) as exc:
            parse_message(inv)
        assert exc.value.code == INVALID_REQUEST

    # 4. Non-object params
    invalid_params = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "test", "params": [1, 2, 3]}),
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "test", "params": "string"}),
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "test", "params": 42}),
    ]
    for inv_p in invalid_params:
        with pytest.raises(McpProtocolError) as exc:
            parse_message(inv_p)
        assert exc.value.code == INVALID_PARAMS
