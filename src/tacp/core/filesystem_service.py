from typing import Any, Dict

from tacp.core.workspace_service import WorkspaceService
from tacp.providers.filesystem import FilesystemProvider


class FilesystemService:
    def __init__(
        self,
        workspace_service: WorkspaceService,
        provider: FilesystemProvider,
    ) -> None:
        self.workspace_service = workspace_service
        self.provider = provider

    def list_dir(self, workspace_id: str, subpath: str = "") -> Dict[str, Any]:
        ws = self.workspace_service.get_workspace(workspace_id)
        result = self.provider.list_dir(ws.root_path, subpath)
        result["workspace_id"] = ws.id
        return result

    def stat_path(self, workspace_id: str, subpath: str) -> Dict[str, Any]:
        ws = self.workspace_service.get_workspace(workspace_id)
        result = self.provider.stat_path(ws.root_path, subpath)
        result["workspace_id"] = ws.id
        return result

    def read_file(self, workspace_id: str, subpath: str) -> Dict[str, Any]:
        ws = self.workspace_service.get_workspace(workspace_id)
        result = self.provider.read_file(ws.root_path, subpath)
        result["workspace_id"] = ws.id
        return result

    def search_files(
        self,
        workspace_id: str,
        query: str,
        subpath: str = "",
        case_sensitive: bool = False,
    ) -> Dict[str, Any]:
        ws = self.workspace_service.get_workspace(workspace_id)
        result = self.provider.search_files(ws.root_path, query, subpath, case_sensitive)
        result["workspace_id"] = ws.id
        return result
