from typing import Any, Dict

from tacp.infrastructure.database import Database
from tacp.providers.system import SystemProvider


class SystemService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.provider = SystemProvider()

    def inspect_system(self) -> Dict[str, Any]:
        return self.provider.get_system_info()

    def get_health(self) -> Dict[str, Any]:
        health = self.provider.get_health()
        db_healthy = self.db.is_healthy()
        overall = "HEALTHY" if health["status"] == "HEALTHY" and db_healthy else "DEGRADED"

        return {
            "status": overall,
            "database_healthy": db_healthy,
            "system_health": health,
        }

    @staticmethod
    def get_version() -> Dict[str, Any]:
        return {
            "tacp_version": "0.1.0-rc.1",
            "mcp_protocol_version": "2026-07-28",
            "supported_mcp_versions": ["2026-07-28", "2024-11-05"],
            "phase": "0.1",
            "mode": "READ_ONLY",
        }
