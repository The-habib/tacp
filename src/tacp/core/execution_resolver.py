"""Execution Resolver.

Handles deterministic binary resolution, trusted root enforcement,
executable identity verification, workspace containment, and safe environment assembly.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from tacp.domain.errors import (
    ErrorCode,
    TacpNotFoundError,
    TacpSecurityError,
    TacpValidationError,
)
from tacp.infrastructure.config import OutputLimits

# Whitelisted executables for controlled command execution
PERMITTED_EXECUTABLE_NAMES: Set[str] = {"printf", "echo", "true"}

# Standard directories searched in strict order (never trusting caller PATH)
SAFE_SEARCH_PATHS: List[Path] = [
    Path("/data/data/com.termux/files/usr/bin"),
    Path("/system/bin"),
    Path("/usr/bin"),
    Path("/bin"),
]

# Trusted system multicall binary names that provide permitted subcommands
TRUSTED_MULTICALL_BINARIES: Set[str] = {
    "coreutils",
    "toybox",
    "toolbox",
    "busybox",
}

# Blacklisted executables and interpreters explicitly denied in all contexts
FORBIDDEN_EXECUTABLE_NAMES: Set[str] = {
    "bash",
    "sh",
    "zsh",
    "dash",
    "ksh",
    "csh",
    "python",
    "python3",
    "python3.11",
    "python3.12",
    "python3.13",
    "python3.14",
    "node",
    "nodejs",
    "perl",
    "ruby",
    "php",
    "lua",
    "env",
    "sudo",
    "su",
    "doas",
    "rm",
    "dd",
    "mkfs",
    "mount",
    "umount",
    "chmod",
    "chown",
    "kill",
    "pkill",
    "killall",
    "curl",
    "wget",
    "nc",
    "ncat",
    "netcat",
    "socat",
    "ssh",
    "scp",
    "rsync",
    "pkg",
    "apt",
    "apt-get",
    "pip",
    "uv",
    "npm",
    "pnpm",
    "yarn",
    "cargo",
    "gem",
}

# Variable name pattern: alphanumeric + underscores
ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")

# Safe Caller Environment Allowlist (explicit known non-hazardous variables)
SAFE_CALLER_ENV_ALLOWLIST: Set[str] = {
    "TZ",
    "COLORTERM",
    "FORCE_COLOR",
    "NO_COLOR",
    "COLUMNS",
    "LINES",
    "CI",
    "DEBUG",
    "OUTPUT_FORMAT",
    "LOG_LEVEL",
    "VERBOSITY",
}

# Safe Caller Variable Prefixes
SAFE_CALLER_PREFIXES: Tuple[str, ...] = ("CUSTOM_", "APP_", "USER_", "TEST_", "VAR", "MY_")

# Unconditional blacklist patterns for environment variables
FORBIDDEN_ENV_PATTERNS = [
    re.compile(
        r"^(TACP_|AWS_|AZURE_|GCP_|GOOGLE_|OPENAI_|ANTHROPIC_|GEMINI_|GITHUB_|GITLAB_|NPM_|PYPI_)",
        re.IGNORECASE,
    ),
    re.compile(r".*(TOKEN|SECRET|KEY|PASSWORD|AUTH|CREDENTIAL|PRIV|CERT).*", re.IGNORECASE),
    re.compile(r"^(LD_|DYLD_)", re.IGNORECASE),
    re.compile(r"^(PYTHON|NODE|RUBY|PERL|JAVA|CLASSPATH|PHP|LUA)", re.IGNORECASE),
    re.compile(r"^(GIT_)", re.IGNORECASE),
    re.compile(r"^(BASH_|ENV$|IFS$|SHELLOPTS|PROMPT_COMMAND)", re.IGNORECASE),
    re.compile(r"^(PAGER|EDITOR|VISUAL|SUDO_|SYSTEMD_)", re.IGNORECASE),
    re.compile(r"^(HTTP_PROXY|HTTPS_PROXY|ALL_PROXY|NO_PROXY)", re.IGNORECASE),
]

# Cache for executable sha256 digests: (inode, device, mtime_ns) -> sha256_hex
_DIGEST_CACHE: Dict[Tuple[int, int, int], str] = {}


@dataclass(frozen=True)
class ExecutableIdentity:
    """Cryptographic and filesystem identity of an authorized executable."""

    canonical_path: str
    basename: str
    trusted_root: str
    inode: int
    device: int
    size: int
    sha256_digest: str


class ExecutionResolver:
    """Handles deterministic binary resolution, workspace containment, and environment assembly."""

    def __init__(self, limits: Optional[OutputLimits] = None) -> None:
        self.limits = limits or OutputLimits()

    def resolve_executable(self, name_or_path: str) -> str:
        """Resolve and validate the executable binary path.

        Guarantees that the resolved binary:
        1. Resides strictly inside an approved trusted root in SAFE_SEARCH_PATHS.
        2. Has its realpath basename in PERMITTED_EXECUTABLE_NAMES or TRUSTED_MULTICALL_BINARIES.
        3. Is not forbidden by platform policy.
        4. Is a regular executable file, not world-writable.
        """
        identity = self.resolve_executable_identity(name_or_path)
        return identity.canonical_path

    def resolve_executable_identity(self, name_or_path: str) -> ExecutableIdentity:
        """Resolve full cryptographic and filesystem identity of executable."""
        if not name_or_path or not isinstance(name_or_path, str):
            raise TacpValidationError("Executable name or path is required and must be a string")

        if "\x00" in name_or_path:
            raise TacpSecurityError(
                ErrorCode.INVALID_INPUT,
                "Executable path contains null byte injection",
            )

        clean_path = name_or_path.strip()
        parts = clean_path.replace("\\", "/").split("/")
        if ".." in parts:
            raise TacpSecurityError(
                ErrorCode.NOT_AUTHORIZED,
                f"Path traversal detected in executable path: '{name_or_path}'",
            )

        basename = Path(clean_path).name.lower()

        # Check explicit forbidden interpreters / destructive utilities
        if basename in FORBIDDEN_EXECUTABLE_NAMES:
            raise TacpSecurityError(
                ErrorCode.NOT_AUTHORIZED,
                f"Execution of '{basename}' is forbidden by Platform Policy",
            )

        # Check permitted whitelist for controlled command execution
        if basename not in PERMITTED_EXECUTABLE_NAMES:
            raise TacpSecurityError(
                ErrorCode.NOT_AUTHORIZED,
                f"Executable '{basename}' is not permitted in controlled command execution",
            )

        chosen_candidate: Optional[Path] = None
        matched_root: Optional[Path] = None

        if "/" in clean_path:
            # Explicit path provided
            candidate = Path(clean_path)
            if not candidate.exists():
                raise TacpNotFoundError(f"Executable path '{clean_path}' does not exist")
            if not candidate.is_file():
                raise TacpSecurityError(
                    ErrorCode.NOT_AUTHORIZED,
                    f"Executable path '{clean_path}' is not a regular file",
                )
            if not os.access(str(candidate), os.X_OK):
                raise TacpSecurityError(
                    ErrorCode.NOT_AUTHORIZED,
                    f"Executable path '{clean_path}' is not marked executable",
                )

            # CRITICAL SECURITY INVARIANT:
            # Candidate path MUST reside strictly within an existing trusted search path!
            for safe_dir in SAFE_SEARCH_PATHS:
                if not safe_dir.exists():
                    continue
                safe_real = safe_dir.resolve()
                if candidate.resolve().is_relative_to(safe_real) or candidate.is_relative_to(
                    safe_dir
                ):
                    matched_root = safe_real
                    chosen_candidate = candidate
                    break

            if not chosen_candidate or not matched_root:
                raise TacpSecurityError(
                    ErrorCode.NOT_AUTHORIZED,
                    f"Executable '{clean_path}' is outside trusted system search paths",
                )
        else:
            # Bare executable name, search SAFE_SEARCH_PATHS in order
            for search_dir in SAFE_SEARCH_PATHS:
                if not search_dir.exists():
                    continue
                candidate = search_dir / clean_path
                if (
                    candidate.exists()
                    and candidate.is_file()
                    and os.access(str(candidate), os.X_OK)
                ):
                    matched_root = search_dir.resolve()
                    chosen_candidate = candidate
                    break

        if not chosen_candidate or not matched_root:
            raise TacpNotFoundError(
                f"Permitted executable '{clean_path}' not found or not executable in trusted roots"
            )

        # Verify real target through symlinks
        real_target = chosen_candidate.resolve()
        is_target_in_safe_root = any(
            real_target.is_relative_to(safe_dir.resolve())
            for safe_dir in SAFE_SEARCH_PATHS
            if safe_dir.exists()
        )
        if not is_target_in_safe_root:
            raise TacpSecurityError(
                ErrorCode.NOT_AUTHORIZED,
                f"Executable '{clean_path}' resolves to '{real_target}', "
                f"which is outside trusted system search paths",
            )

        target_name = real_target.name.lower()
        if target_name in FORBIDDEN_EXECUTABLE_NAMES:
            raise TacpSecurityError(
                ErrorCode.NOT_AUTHORIZED,
                f"Executable '{clean_path}' resolves to forbidden target '{target_name}'",
            )

        # Permitted target check: must be in allowlist or trusted multicall binaries
        if (
            target_name not in PERMITTED_EXECUTABLE_NAMES
            and target_name not in TRUSTED_MULTICALL_BINARIES
        ):
            raise TacpSecurityError(
                ErrorCode.NOT_AUTHORIZED,
                f"Resolved target '{target_name}' is not in permitted executables list",
            )

        # Inode & permissions check on target
        stat_res = real_target.stat()
        if stat_res.st_mode & 0o002:  # world-writable
            raise TacpSecurityError(
                ErrorCode.NOT_AUTHORIZED,
                f"Executable '{real_target}' is insecurely world-writable",
            )

        # Compute or retrieve cached digest
        cache_key = (
            stat_res.st_ino,
            stat_res.st_dev,
            getattr(stat_res, "st_mtime_ns", int(stat_res.st_mtime * 1e9)),
        )
        if cache_key in _DIGEST_CACHE:
            digest = _DIGEST_CACHE[cache_key]
        else:
            hasher = hashlib.sha256()
            with open(real_target, "rb") as bf:
                while chunk := bf.read(65536):
                    hasher.update(chunk)
            digest = hasher.hexdigest()
            _DIGEST_CACHE[cache_key] = digest

        return ExecutableIdentity(
            canonical_path=str(chosen_candidate),
            basename=chosen_candidate.name.lower(),
            trusted_root=str(matched_root),
            inode=stat_res.st_ino,
            device=stat_res.st_dev,
            size=stat_res.st_size,
            sha256_digest=digest,
        )

    def resolve_working_directory(self, workspace_root: Path, req_cwd: Optional[str]) -> str:
        """Validate and jail the working directory within the workspace root."""
        clean_root = workspace_root.resolve()
        if not clean_root.exists() or not clean_root.is_dir():
            raise TacpValidationError(
                f"Workspace root '{clean_root}' does not exist or is not a directory"
            )

        if not req_cwd or req_cwd.strip() in ("", ".", "./"):
            return str(clean_root)

        clean_cwd = req_cwd.strip()
        if "\x00" in clean_cwd:
            raise TacpSecurityError(ErrorCode.INVALID_INPUT, "Working directory contains null byte")

        # Canonicalize target path
        target = (clean_root / clean_cwd).resolve()

        if not target.is_relative_to(clean_root):
            raise TacpSecurityError(
                ErrorCode.NOT_AUTHORIZED,
                f"Working directory '{req_cwd}' escapes workspace boundary '{clean_root}'",
            )

        if not target.exists():
            raise TacpValidationError(f"Working directory '{target}' does not exist")

        if not target.is_dir():
            raise TacpValidationError(f"Working directory '{target}' is not a directory")

        return str(target)

    def validate_argv(self, executable: str, argv: List[str]) -> Tuple[str, ...]:
        """Validate argument vector against bounds and injection vectors."""
        if not isinstance(argv, list):
            raise TacpValidationError("Parameter 'argv' must be a list of strings")

        if len(argv) == 0:
            raise TacpValidationError("Argument vector cannot be empty")

        exe_name = Path(executable).name
        raw_argv = list(argv)
        if raw_argv and raw_argv[0] != exe_name:
            raw_argv = [exe_name] + raw_argv

        if len(raw_argv) > self.limits.max_argv_count:
            raise TacpValidationError(
                f"Argument count {len(raw_argv)} exceeds limit of {self.limits.max_argv_count}"
            )

        validated_args: List[str] = []
        for i, arg in enumerate(raw_argv):
            if not isinstance(arg, str):
                raise TacpValidationError(
                    f"Argument at index {i} must be a string, got {type(arg).__name__}"
                )

            if "\x00" in arg:
                raise TacpSecurityError(
                    ErrorCode.INVALID_INPUT,
                    f"Argument at index {i} contains null byte",
                )

            arg_bytes = arg.encode("utf-8")
            if len(arg_bytes) > self.limits.max_arg_length:
                raise TacpValidationError(
                    f"Argument at index {i} ({len(arg_bytes)} bytes) "
                    f"exceeds limit of {self.limits.max_arg_length} bytes"
                )

            validated_args.append(arg)

        return tuple(validated_args)

    def assemble_environment(
        self,
        workspace_root: Path,
        cwd: str,
        caller_env: Optional[Dict[str, str]] = None,
    ) -> Tuple[Tuple[str, str], ...]:
        """Construct the hermetic Base Safe Environment with caller variables.

        Uses the Safe Environment Allowlist model:
        - System variables (PATH, HOME, TMPDIR, PWD, LANG, LC_ALL, TERM) are authoritative.
        - Caller variables matching FORBIDDEN_ENV_PATTERNS are stripped.
        - Caller variables must match SAFE_CALLER_ENV_ALLOWLIST or SAFE_CALLER_PREFIXES.
        """
        # Curate minimal safe PATH
        existing_paths = [str(p) for p in SAFE_SEARCH_PATHS if p.exists()]
        curated_path = ":".join(existing_paths) if existing_paths else "/system/bin:/bin"

        base_env: Dict[str, str] = {
            "PATH": curated_path,
            "HOME": str(workspace_root.resolve()),
            "TMPDIR": tempfile.gettempdir(),
            "PWD": cwd,
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "TERM": "dumb",
        }

        if caller_env:
            if not isinstance(caller_env, dict):
                raise TacpValidationError("Parameter 'environment' must be a dictionary")

            if len(caller_env) > 16:
                raise TacpValidationError("Cannot specify more than 16 environment variables")

            for key, val in caller_env.items():
                if not isinstance(key, str) or not isinstance(val, str):
                    raise TacpValidationError("Environment keys and values must be strings")

                if not ENV_KEY_PATTERN.match(key):
                    raise TacpValidationError(f"Invalid environment variable key name: '{key}'")

                if "\x00" in val:
                    raise TacpSecurityError(
                        ErrorCode.INVALID_INPUT,
                        f"Environment variable '{key}' value contains null byte",
                    )

                if len(val.encode("utf-8")) > 2048:
                    raise TacpValidationError(
                        f"Environment variable '{key}' exceeds 2048 byte value limit"
                    )

                if key in ("PATH", "HOME", "PWD", "TMPDIR", "LANG", "LC_ALL", "TERM"):
                    # System-managed environment variables cannot be overridden by caller
                    continue

                # Check against unconditional forbidden patterns
                is_forbidden = any(pattern.match(key) for pattern in FORBIDDEN_ENV_PATTERNS)
                if is_forbidden:
                    continue

                # Safe Environment Allowlist Check
                is_allowed = (key in SAFE_CALLER_ENV_ALLOWLIST) or any(
                    key.startswith(p) for p in SAFE_CALLER_PREFIXES
                )
                if not is_allowed:
                    # Strip unapproved caller variables
                    continue

                base_env[key] = val

        sorted_pairs = tuple(sorted(base_env.items(), key=lambda item: item[0]))
        return sorted_pairs
