import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from tacp.domain.errors import TacpNotFoundError, TacpValidationError
from tacp.domain.workspace import Workspace
from tacp.infrastructure.database import Database


class WorkspaceService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self._cache: Dict[str, Workspace] = {}
        self._last_changes: Optional[int] = None

    def invalidate_cache(self) -> None:
        """Clear the in-memory workspace cache."""
        self._cache.clear()
        self._last_changes = None

    def register_workspace(
        self,
        name: str,
        root_path: Path,
        trust_level: str = "RESTRICTED",
    ) -> Workspace:
        resolved = root_path.resolve()
        if not resolved.exists():
            raise TacpValidationError(f"Workspace path does not exist: {root_path}")
        if not resolved.is_dir():
            raise TacpValidationError(f"Workspace path is not a directory: {root_path}")

        ws_id = str(uuid.uuid4())[:8]
        ws = Workspace(
            id=ws_id,
            name=name,
            root_path=resolved,
            trust_level=trust_level,
            status="ACTIVE",
        )

        conn = self.db.connect()
        conn.execute(
            """
            INSERT OR REPLACE INTO workspaces (
                id, name, root_path, trust_level, status, created_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                ws.id,
                ws.name,
                str(ws.root_path),
                ws.trust_level,
                ws.status,
                ws.created_at,
                json.dumps(ws.metadata),
            ),
        )
        conn.commit()
        self._last_changes = getattr(conn, "total_changes", None)
        self._cache[ws.id] = ws
        self._cache[ws.name] = ws
        return ws

    def list_workspaces(self) -> List[Dict[str, Any]]:
        conn = self.db.connect()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, root_path, trust_level, status, created_at FROM workspaces;"
        )
        rows = cursor.fetchall()
        result = []
        for r in rows:
            result.append(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "root_path": r["root_path"],
                    "trust_level": r["trust_level"],
                    "status": r["status"],
                    "created_at": r["created_at"],
                }
            )
        return result

    def get_workspace(self, workspace_id: str) -> Workspace:
        conn = self.db.connect()
        changes = getattr(conn, "total_changes", None)
        if self._last_changes is not None and changes is not None and changes != self._last_changes:
            self._cache.clear()
        self._last_changes = changes

        if workspace_id in self._cache:
            return self._cache[workspace_id]

        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, name, root_path, trust_level, status, created_at, metadata_json
            FROM workspaces WHERE id = ? OR name = ?;
            """,
            (workspace_id, workspace_id),
        )
        row = cursor.fetchone()
        if not row:
            raise TacpNotFoundError(f"Workspace not found: {workspace_id}")

        ws = Workspace(
            id=row["id"],
            name=row["name"],
            root_path=Path(row["root_path"]),
            trust_level=row["trust_level"],
            status=row["status"],
            created_at=row["created_at"],
            metadata=json.loads(row["metadata_json"]),
        )
        self._cache[ws.id] = ws
        self._cache[ws.name] = ws
        return ws

    def inspect_workspace(self, workspace_id: str) -> Dict[str, Any]:
        ws = self.get_workspace(workspace_id)
        root = ws.root_path
        file_count = 0
        dir_count = 0
        total_size = 0

        for p in root.rglob("*"):
            try:
                if ".git" in p.parts:
                    continue
                if p.is_file():
                    file_count += 1
                    total_size += p.stat().st_size
                elif p.is_dir():
                    dir_count += 1
            except OSError:
                continue

        has_git = (root / ".git").is_dir()
        return {
            "workspace": ws.to_dict(),
            "summary": {
                "file_count": file_count,
                "dir_count": dir_count,
                "total_bytes": total_size,
                "has_git": has_git,
            },
        }
