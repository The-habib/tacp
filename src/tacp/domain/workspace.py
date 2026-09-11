from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


@dataclass(frozen=True)
class Workspace:
    id: str
    name: str
    root_path: Path
    trust_level: str = "RESTRICTED"
    status: str = "ACTIVE"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "root_path": str(self.root_path),
            "trust_level": self.trust_level,
            "status": self.status,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }
