"""Abstract base class for TACP remote tunnel and relay providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class TunnelInfo:
    """Information about an active remote tunnel or endpoint."""

    provider_name: str
    public_url: str
    mcp_endpoint: str
    is_active: bool
    status_message: str
    details: Dict[str, Any]


class BaseTunnelProvider(ABC):
    """Abstract interface implemented by all remote transport providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g. 'cloudflare', 'relay', 'direct')."""
        ...

    @abstractmethod
    def start(self, local_port: int, **kwargs: Any) -> TunnelInfo:
        """Start the tunnel connecting external traffic to local_port."""
        ...

    @abstractmethod
    def stop(self) -> bool:
        """Stop the tunnel and clean up resources."""
        ...

    @abstractmethod
    def get_status(self) -> TunnelInfo:
        """Retrieve current tunnel status and public URL."""
        ...
