import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass(frozen=True)
class OutputLimits:
    max_file_read_bytes: int = 65536  # 64 KB
    max_dir_entries: int = 200
    max_search_results: int = 100
    max_processes: int = 100
    max_audit_results: int = 100


@dataclass(frozen=True)
class TacpConfig:
    data_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get("TACP_DATA_DIR", Path.home() / ".tacp")
        ).resolve()
    )
    version: str = "0.1.0"
    db_path: Path = field(default=Path())
    log_level: str = "INFO"
    read_only: bool = True
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

    @classmethod
    def load(cls) -> "TacpConfig":
        data_dir_str = os.environ.get("TACP_DATA_DIR")
        data_dir = Path(data_dir_str).resolve() if data_dir_str else Path.home() / ".tacp"
        db_path_str = os.environ.get("TACP_DB_PATH")
        db_path = Path(db_path_str).resolve() if db_path_str else data_dir / "tacp.db"
        log_level = os.environ.get("TACP_LOG_LEVEL", "INFO").upper()

        return cls(
            data_dir=data_dir,
            db_path=db_path,
            log_level=log_level,
            read_only=True,
            limits=OutputLimits(),
        )
