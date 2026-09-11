import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from tacp import __version__


@dataclass(frozen=True)
class OutputLimits:
    max_file_read_bytes: int = 65536  # 64 KB
    max_dir_entries: int = 200
    max_search_results: int = 100
    max_processes: int = 100
    max_audit_results: int = 100
    max_patch_bytes: int = 262144  # 256 KB
    max_file_size_bytes: int = 1048576  # 1 MB
    max_resulting_file_bytes: int = 2097152  # 2 MB
    max_batch_files: int = 10
    max_batch_patch_total_bytes: int = 1048576  # 1 MB
    max_batch_resulting_total_bytes: int = 5242880  # 5 MB
    max_execution_duration_seconds: int = 15
    max_stdout_bytes: int = 65536  # 64 KB
    max_stderr_bytes: int = 65536  # 64 KB
    max_argv_count: int = 64
    max_arg_length: int = 4096
    max_env_count: int = 16


@dataclass(frozen=True)
class TacpConfig:
    data_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get("TACP_DATA_DIR", Path.home() / ".tacp")
        ).resolve()
    )
    version: str = __version__
    db_path: Path = field(default=Path())
    log_level: str = "INFO"
    read_only: bool = True
    mutation_enabled: bool = False
    batch_mutation_enabled: bool = False
    execution_enabled: bool = False
    network_enabled: bool = False
    remote_enabled: bool = False
    remote_read_only: bool = True
    remote_mutation_enabled: bool = False
    remote_execution_enabled: bool = False
    trust_profile: str = field(
        default_factory=lambda: os.environ.get("TACP_TRUST_PROFILE", "BALANCED").upper()
    )
    lease_default_duration_seconds: int = 1200
    lease_max_duration_seconds: int = 3600
    limits: OutputLimits = field(default_factory=OutputLimits)
    allowed_workspace_roots: List[Path] = field(default_factory=list)

    @property
    def database_path(self) -> Path:
        return self.db_path

    def __post_init__(self) -> None:
        if not self.db_path or self.db_path == Path():
            object.__setattr__(self, "db_path", self.data_dir / "tacp.db")
        if not self.allowed_workspace_roots:
            # Default to projects directory or current workspace
            default_root = Path.home() / "projects"
            object.__setattr__(self, "allowed_workspace_roots", [default_root])
        # If mutation is disabled, enforce read_only = True and batch_mutation_enabled = False
        if not self.mutation_enabled:
            object.__setattr__(self, "read_only", True)
            object.__setattr__(self, "batch_mutation_enabled", False)
        if self.trust_profile == "REMOTE_READ_ONLY" or self.remote_read_only:
            object.__setattr__(self, "remote_read_only", True)
            object.__setattr__(self, "remote_mutation_enabled", False)
            object.__setattr__(self, "remote_execution_enabled", False)

    @classmethod
    def load(cls) -> "TacpConfig":
        data_dir_str = os.environ.get("TACP_DATA_DIR")
        data_dir = Path(data_dir_str).resolve() if data_dir_str else Path.home() / ".tacp"
        db_path_str = os.environ.get("TACP_DB_PATH")
        db_path = Path(db_path_str).resolve() if db_path_str else data_dir / "tacp.db"
        log_level = os.environ.get("TACP_LOG_LEVEL", "INFO").upper()
        mutation_enabled = os.environ.get("TACP_MUTATION_ENABLED", "0").lower() in (
            "1",
            "true",
            "yes",
        )
        batch_mutation_enabled = os.environ.get("TACP_BATCH_MUTATION_ENABLED", "0").lower() in (
            "1",
            "true",
            "yes",
        )
        execution_enabled = os.environ.get("TACP_EXECUTION_ENABLED", "0").lower() in (
            "1",
            "true",
            "yes",
        )
        network_enabled = os.environ.get("TACP_NETWORK_ENABLED", "0").lower() in (
            "1",
            "true",
            "yes",
        )
        remote_enabled = os.environ.get("TACP_REMOTE_ENABLED", "0").lower() in (
            "1",
            "true",
            "yes",
        )
        remote_read_only = os.environ.get("TACP_REMOTE_READ_ONLY", "1").lower() in (
            "1",
            "true",
            "yes",
        )
        remote_mutation_enabled = os.environ.get("TACP_REMOTE_MUTATION_ENABLED", "0").lower() in (
            "1",
            "true",
            "yes",
        )
        remote_execution_enabled = os.environ.get("TACP_REMOTE_EXECUTION_ENABLED", "0").lower() in (
            "1",
            "true",
            "yes",
        )
        read_only = not mutation_enabled
        if "TACP_READ_ONLY" in os.environ:
            read_only = os.environ.get("TACP_READ_ONLY", "1").lower() in ("1", "true", "yes")

        return cls(
            data_dir=data_dir,
            db_path=db_path,
            log_level=log_level,
            read_only=read_only,
            mutation_enabled=mutation_enabled,
            batch_mutation_enabled=batch_mutation_enabled,
            execution_enabled=execution_enabled,
            network_enabled=network_enabled,
            remote_enabled=remote_enabled,
            remote_read_only=remote_read_only,
            remote_mutation_enabled=remote_mutation_enabled,
            remote_execution_enabled=remote_execution_enabled,
            limits=OutputLimits(),
        )
