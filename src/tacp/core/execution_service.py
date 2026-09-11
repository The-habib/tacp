"""Execution Service: Core service orchestrating the 16-stage governed execution pipeline."""

from __future__ import annotations

import json
import logging
import os
import signal
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from tacp.control.approval import ApprovalEngine
from tacp.control.identity import Authority, Principal, RequestContext
from tacp.control.policy import PolicyEngine
from tacp.core.audit_service import AuditService
from tacp.core.execution_resolver import ExecutionResolver
from tacp.core.workspace_service import WorkspaceService
from tacp.domain.audit import AuditEvent
from tacp.domain.errors import (
    ErrorCode,
    TacpApprovalRequiredError,
    TacpNotFoundError,
    TacpSecurityError,
    TacpValidationError,
)
from tacp.domain.execution import (
    ExecutionContract,
    ExecutionResult,
    ExecutionStatus,
    NetworkIsolationState,
    compute_execution_contract_hash,
)
from tacp.infrastructure.config import TacpConfig
from tacp.infrastructure.database import Database
from tacp.infrastructure.logging import redact_dict
from tacp.providers.process_executor import ProcessExecutor

logger = logging.getLogger(__name__)


class ExecutionService:
    """Orchestrates governed command execution through the authoritative 16-stage pipeline."""

    def __init__(
        self,
        db: Database,
        config: TacpConfig,
        policy_engine: PolicyEngine,
        approval_engine: ApprovalEngine,
        audit_service: AuditService,
        workspace_service: WorkspaceService,
        resolver: Optional[ExecutionResolver] = None,
        executor: Optional[ProcessExecutor] = None,
        lease_engine: Optional[Any] = None,
    ) -> None:
        self.db = db
        self.config = config
        self.policy_engine = policy_engine
        self.approval_engine = approval_engine
        self.audit_service = audit_service
        self.workspace_service = workspace_service
        self.resolver = resolver or ExecutionResolver(limits=config.limits)
        self.executor = executor or ProcessExecutor()
        self.lease_engine = lease_engine

    def execute_command(
        self,
        workspace_id: str,
        executable: str,
        argv: List[str],
        cwd: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None,
        timeout_seconds: Optional[int] = None,
        dry_run: bool = False,
        approval_token: Optional[str] = None,
        principal_id: str = "local_agent",
        request_id: Optional[str] = None,
        principal: Optional[Principal] = None,
        lease_id: Optional[str] = None,
    ) -> ExecutionResult:
        """Execute a command through the full 16-stage pipeline."""
        start_perf = time.perf_counter()
        req_id = request_id or str(uuid.uuid4())
        execution_id = f"exec-{uuid.uuid4().hex[:12]}"

        # Stage 1: Request Ingestion & Schema Validation
        if not workspace_id or not isinstance(workspace_id, str):
            raise TacpValidationError("Parameter 'workspace_id' is required and must be a string")

        if timeout_seconds is not None:
            if (
                not isinstance(timeout_seconds, int)
                or isinstance(timeout_seconds, bool)
                or timeout_seconds <= 0
            ):
                raise TacpValidationError("Parameter 'timeout_seconds' must be a positive integer")

        validated_argv = self.resolver.validate_argv(executable, argv)

        # Stage 2: Feature Flag Check
        if not self.config.execution_enabled:
            raise TacpSecurityError(
                ErrorCode.POLICY_DENIED,
                "Command execution is disabled in TACP configuration",
            )

        # Stage 3: Principal & Identity Context
        caller_principal = principal or Principal.local_agent(principal_id)
        context = RequestContext(
            capability="execution.request",
            principal=caller_principal,
            request_id=req_id,
        )

        # Stage 4: Workspace Resolution & Containment
        workspace = self.workspace_service.get_workspace(workspace_id)
        if not workspace:
            raise TacpNotFoundError(f"Workspace '{workspace_id}' not found")

        resolved_cwd = self.resolver.resolve_working_directory(
            workspace_root=workspace.root,
            req_cwd=cwd,
        )

        # Stage 5: Executable Binary Resolution & Whitelist
        identity = self.resolver.resolve_executable_identity(executable)
        resolved_bin = identity.canonical_path
        executable_digest = identity.sha256_digest

        # Stage 7: Environment Stripping & Base Assembly
        clean_env = self.resolver.assemble_environment(
            workspace_root=workspace.root,
            cwd=resolved_cwd,
            caller_env=environment,
        )

        # Stage 8: Resource Limits & Timeout Binding
        effective_timeout = min(
            timeout_seconds or self.config.limits.max_execution_duration_seconds,
            60,  # Hard upper cap
        )
        if effective_timeout <= 0:
            effective_timeout = self.config.limits.max_execution_duration_seconds

        # Stage 9: Canonical ExecutionContract Hashing
        contract = ExecutionContract(
            workspace_id=workspace_id,
            executable=resolved_bin,
            argv=validated_argv,
            cwd=resolved_cwd,
            environment=clean_env,
            network_enabled=self.config.network_enabled,
            timeout_seconds=effective_timeout,
            max_stdout_bytes=self.config.limits.max_stdout_bytes,
            max_stderr_bytes=self.config.limits.max_stderr_bytes,
            contract_version=1,
            network_state=NetworkIsolationState.NETWORK_UNENFORCED.value,
            executable_digest=executable_digest,
            principal_id=caller_principal.id,
        )
        contract_hash = compute_execution_contract_hash(contract)

        # Stage 10: Policy Engine Evaluation
        decision = self.policy_engine.evaluate_request(
            context=context,
            workspace=workspace,
            target_path=resolved_bin,
            dry_run=dry_run,
            has_approval=bool(approval_token),
            lease_id=lease_id,
        )

        # Stage 11a: Dry-Run Handling
        if dry_run:
            duration_ms = int((time.perf_counter() - start_perf) * 1000)
            self.audit_service.record_event(
                AuditEvent(
                    capability="execution.request",
                    action="execution.dry_run",
                    policy_decision=decision.decision_type,
                    result="SUCCESS",
                    duration_ms=duration_ms,
                    principal=caller_principal.id,
                    request_id=req_id,
                    workspace_id=workspace_id,
                    parameters_redacted=redact_dict(
                        {
                            "executable": resolved_bin,
                            "argv": list(validated_argv),
                            "cwd": resolved_cwd,
                            "contract_hash": contract_hash,
                            "dry_run": True,
                        }
                    ),
                )
            )
            return ExecutionResult(
                execution_id=execution_id,
                status=ExecutionStatus.DRY_RUN.value,
                exit_code=None,
                stdout="",
                stderr="",
                duration_ms=duration_ms,
                contract_hash=contract_hash,
                metadata={
                    "dry_run": True,
                    "resolved_executable": resolved_bin,
                    "argv": list(validated_argv),
                    "cwd": resolved_cwd,
                    "timeout_seconds": effective_timeout,
                    "policy_decision": decision.decision_type,
                },
            )

        # Stage 11b: Approval Gate
        if decision.requires_approval():
            ticket = self.approval_engine.create_ticket(
                principal_id=caller_principal.id,
                action_type="execution.request",
                workspace_id=workspace_id,
                target_path=resolved_bin,
                patch_hash=contract_hash,
                metadata={
                    "execution_id": execution_id,
                    "argv": list(validated_argv),
                    "cwd": resolved_cwd,
                    "timeout_seconds": effective_timeout,
                },
            )
            duration_ms = int((time.perf_counter() - start_perf) * 1000)
            self.audit_service.record_event(
                AuditEvent(
                    capability="execution.request",
                    action="execution.approval_required",
                    policy_decision="REQUIRE_APPROVAL",
                    result="PENDING_APPROVAL",
                    duration_ms=duration_ms,
                    principal=caller_principal.id,
                    request_id=req_id,
                    workspace_id=workspace_id,
                    parameters_redacted=redact_dict(
                        {
                            "ticket_id": ticket.id,
                            "contract_hash": contract_hash,
                            "executable": resolved_bin,
                        }
                    ),
                )
            )
            raise TacpApprovalRequiredError(
                f"Execution of '{executable}' requires explicit human approval",
                details={
                    "ticket_id": ticket.id,
                    "token": ticket.token,
                    "contract_hash": contract_hash,
                    "expires_at": ticket.expires_at,
                },
            )

        if not decision.allowed:
            raise TacpSecurityError(
                ErrorCode.POLICY_DENIED,
                f"Execution denied by policy: {decision.reason}",
            )

        # Stage 12: Approval Token / Lease Single-Use Consumption
        if lease_id and self.lease_engine:
            self.lease_engine.verify_and_consume(
                lease_id=lease_id,
                principal_id=caller_principal.id,
                capability="execution.request",
                workspace_id=workspace_id,
                risk_level="R3",
                target_path=resolved_bin,
            )
        elif approval_token:
            self.approval_engine.verify_and_consume(
                token=approval_token,
                principal_id=caller_principal.id,
                action_type="execution.request",
                workspace_id=workspace_id,
                target_path=resolved_bin,
                patch_hash=contract_hash,
            )

        # Stage 13: Pre-Execution Persistence
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        conn = self.db.connect()
        with conn:
            conn.execute(
                """
                INSERT INTO executions (
                    id, execution_id, action_type, workspace_id, executable,
                    argv_json, cwd, contract_hash, principal_id, status,
                    created_at, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    execution_id,
                    execution_id,
                    "execution.request",
                    workspace_id,
                    resolved_bin,
                    json.dumps(list(validated_argv)),
                    resolved_cwd,
                    contract_hash,
                    caller_principal.id,
                    ExecutionStatus.RUNNING.value,
                    now_iso,
                    now_iso,
                ),
            )

        # Stage 14: Process Group Spawning in New Session
        result = self.executor.execute(execution_id=execution_id, contract=contract)

        # Stage 15 & 16: Completion, DB Update & Tamper-Evident Audit Logging
        duration_ms = int((time.perf_counter() - start_perf) * 1000)
        end_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        with conn:
            conn.execute(
                """
                UPDATE executions
                SET status = ?, exit_code = ?, term_signal = ?, duration_ms = ?,
                    stdout_truncated = ?, stderr_truncated = ?, timed_out = ?,
                    cancelled = ?, pid = ?, pgid = ?, terminated_at = ?
                WHERE execution_id = ?;
                """,
                (
                    result.status,
                    result.exit_code,
                    result.term_signal,
                    duration_ms,
                    1 if result.stdout_truncated else 0,
                    1 if result.stderr_truncated else 0,
                    1 if result.timed_out else 0,
                    1 if result.cancelled else 0,
                    result.pid,
                    result.pgid,
                    end_iso,
                    execution_id,
                ),
            )

        # Cryptographic Audit Event
        self.audit_service.record_event(
            AuditEvent(
                capability="execution.request",
                action="execution.run",
                policy_decision=decision.decision_type,
                result=result.status,
                duration_ms=duration_ms,
                principal=caller_principal.id,
                request_id=req_id,
                workspace_id=workspace_id,
                parameters_redacted=redact_dict(
                    {
                        "execution_id": execution_id,
                        "executable": resolved_bin,
                        "argv": list(validated_argv),
                        "contract_hash": contract_hash,
                        "exit_code": result.exit_code,
                        "timed_out": result.timed_out,
                    }
                ),
            )
        )

        return ExecutionResult(
            execution_id=execution_id,
            status=result.status,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_ms=duration_ms,
            stdout_truncated=result.stdout_truncated,
            stderr_truncated=result.stderr_truncated,
            timed_out=result.timed_out,
            cancelled=result.cancelled,
            contract_hash=contract_hash,
            pid=result.pid,
            pgid=result.pgid,
            term_signal=result.term_signal,
        )

    def inspect_execution(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Inspect recorded execution state from the database."""
        conn = self.db.connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, execution_id, action_type, workspace_id, executable,
                   argv_json, cwd, contract_hash, principal_id, status,
                   exit_code, term_signal, duration_ms, stdout_truncated,
                   stderr_truncated, timed_out, cancelled, pid, pgid,
                   created_at, started_at, terminated_at, metadata_json
            FROM executions
            WHERE execution_id = ? OR id = ?;
            """,
            (execution_id, execution_id),
        )
        row = cur.fetchone()
        if not row:
            return None

        return {
            "execution_id": row["execution_id"],
            "action_type": row["action_type"],
            "workspace_id": row["workspace_id"],
            "executable": row["executable"],
            "argv": json.loads(row["argv_json"]),
            "cwd": row["cwd"],
            "contract_hash": row["contract_hash"],
            "principal_id": row["principal_id"],
            "status": row["status"],
            "exit_code": row["exit_code"],
            "term_signal": row["term_signal"],
            "duration_ms": row["duration_ms"],
            "stdout_truncated": bool(row["stdout_truncated"]),
            "stderr_truncated": bool(row["stderr_truncated"]),
            "timed_out": bool(row["timed_out"]),
            "cancelled": bool(row["cancelled"]),
            "pid": row["pid"],
            "pgid": row["pgid"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "terminated_at": row["terminated_at"],
        }

    def list_executions(
        self, workspace_id: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """List execution history."""
        conn = self.db.connect()
        cur = conn.cursor()
        if workspace_id:
            cur.execute(
                """
                SELECT execution_id, action_type, workspace_id, executable,
                       argv_json, status, exit_code, duration_ms, created_at
                FROM executions
                WHERE workspace_id = ?
                ORDER BY rowid DESC
                LIMIT ?;
                """,
                (workspace_id, max(1, min(limit, 100))),
            )
        else:
            cur.execute(
                """
                SELECT execution_id, action_type, workspace_id, executable,
                       argv_json, status, exit_code, duration_ms, created_at
                FROM executions
                ORDER BY rowid DESC
                LIMIT ?;
                """,
                (max(1, min(limit, 100)),),
            )
        rows = cur.fetchall()
        results = []
        for r in rows:
            results.append(
                {
                    "execution_id": r["execution_id"],
                    "action_type": r["action_type"],
                    "workspace_id": r["workspace_id"],
                    "executable": r["executable"],
                    "argv": json.loads(r["argv_json"]),
                    "status": r["status"],
                    "exit_code": r["exit_code"],
                    "duration_ms": r["duration_ms"],
                    "created_at": r["created_at"],
                }
            )
        return results

    def cancel_execution(
        self, execution_id: str, principal: Optional[Principal] = None
    ) -> Dict[str, Any]:
        """Cancel an active execution process group with PID reuse defense."""
        exec_info = self.inspect_execution(execution_id)
        if not exec_info:
            raise TacpNotFoundError(f"Execution '{execution_id}' not found")

        if exec_info["status"] != ExecutionStatus.RUNNING.value:
            return {
                "execution_id": execution_id,
                "status": exec_info["status"],
                "message": f"Execution is already in terminal state '{exec_info['status']}'",
            }

        pgid = exec_info.get("pgid")
        active = self.executor.get_active(execution_id)
        if active and active.pgid == pgid:
            try:
                os.killpg(pgid, signal.SIGTERM)
                time.sleep(0.05)
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif pgid:
            # PID reuse defense: process is not in active memory registry.
            # Do not signal an unverified PID to avoid killing recycled foreign processes.
            logger.warning(
                "Execution '%s' is not in active process registry; skipping killpg for PGID %s",
                execution_id,
                pgid,
            )

        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        conn = self.db.connect()
        with conn:
            conn.execute(
                """
                UPDATE executions
                SET status = ?, cancelled = 1, terminated_at = ?
                WHERE execution_id = ?;
                """,
                (ExecutionStatus.CANCELLED.value, now_iso, execution_id),
            )

        p_id = principal.id if principal else exec_info.get("principal_id", "operator")
        self.audit_service.record_event(
            AuditEvent(
                capability="execution.cancel",
                action="execution.cancel",
                policy_decision="ALLOW",
                result=ExecutionStatus.CANCELLED.value,
                duration_ms=0,
                principal=p_id,
                request_id=str(uuid.uuid4()),
                workspace_id=exec_info.get("workspace_id", "*"),
                parameters_redacted={"execution_id": execution_id},
            )
        )

        return {
            "execution_id": execution_id,
            "status": ExecutionStatus.CANCELLED.value,
            "message": "Execution process group cancelled and terminated",
        }

    def emergency_stop(self, principal: Optional[Principal] = None) -> int:
        """Emergency stop: terminate all active execution process groups with audit logging."""
        p = principal or Principal.human_operator("emergency-stop")
        if not p.is_elevated() and not p.has_authority(Authority.ADMIN_EMERGENCY_STOP):
            raise TacpSecurityError(
                ErrorCode.NOT_AUTHORIZED,
                f"Principal '{p.id}' is not authorized to execute emergency stop",
            )

        active_procs = self.executor.get_all_active()
        stopped_count = 0
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        for active in active_procs:
            try:
                os.killpg(active.pgid, signal.SIGTERM)
                time.sleep(0.05)
                os.killpg(active.pgid, signal.SIGKILL)
                stopped_count += 1
            except ProcessLookupError:
                pass

        conn = self.db.connect()
        with conn:
            conn.execute(
                """
                UPDATE executions
                SET status = ?, cancelled = 1, terminated_at = ?
                WHERE status IN (?, ?, ?);
                """,
                (
                    ExecutionStatus.CANCELLED.value,
                    now_iso,
                    ExecutionStatus.RUNNING.value,
                    ExecutionStatus.STARTING.value,
                    ExecutionStatus.QUEUED.value,
                ),
            )

        self.audit_service.record_event(
            AuditEvent(
                capability="execution.emergency_stop",
                action="execution.emergency_stop",
                policy_decision="ALLOW",
                result="SUCCESS",
                duration_ms=0,
                principal=p.id,
                request_id=str(uuid.uuid4()),
                workspace_id="*",
                parameters_redacted={"stopped_count": stopped_count},
            )
        )
        return stopped_count

    def reconcile_orphans(self) -> int:
        """Startup recovery: inspect executions stuck in RUNNING or STARTING and reconcile state."""
        conn = self.db.connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT execution_id, pid, pgid, status
            FROM executions
            WHERE status IN (?, ?);
            """,
            (ExecutionStatus.RUNNING.value, ExecutionStatus.STARTING.value),
        )
        rows = cur.fetchall()
        reconciled = 0
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        for r in rows:
            exec_id = r["execution_id"]
            pid = r["pid"]
            is_alive = False
            if pid and pid > 0:
                proc_path = Path(f"/proc/{pid}")
                is_alive = proc_path.exists()

            new_status = (
                ExecutionStatus.ORPHANED.value if is_alive else ExecutionStatus.FAILED.value
            )
            with conn:
                conn.execute(
                    """
                    UPDATE executions
                    SET status = ?, terminated_at = ?
                    WHERE execution_id = ?;
                    """,
                    (new_status, now_iso, exec_id),
                )
            reconciled += 1

        return reconciled
