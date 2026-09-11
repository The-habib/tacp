from typing import Any, Dict

from tacp.providers.process import ProcessProvider


class ProcessService:
    def __init__(self, provider: ProcessProvider) -> None:
        self.provider = provider

    def list_processes(self) -> Dict[str, Any]:
        return self.provider.list_processes()

    def inspect_process(self, pid: int) -> Dict[str, Any]:
        return self.provider.inspect_process(pid)
