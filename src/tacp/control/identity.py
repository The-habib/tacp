import uuid
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Principal:
    id: str = "anonymous"
    role: str = "agent"
    authenticated: bool = False


@dataclass(frozen=True)
class RequestContext:
    capability: str
    principal: Principal = field(default_factory=Principal)
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
