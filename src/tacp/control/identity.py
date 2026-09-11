import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


class PrincipalType(str, Enum):
    AGENT = "AGENT"
    HUMAN = "HUMAN"
    SYSTEM = "SYSTEM"


class TrustTier(str, Enum):
    UNTRUSTED = "UNTRUSTED"
    RESTRICTED = "RESTRICTED"
    PRIVILEGED = "PRIVILEGED"


class CredentialSource(str, Enum):
    LOCAL_STDIO = "LOCAL_STDIO"
    TOKEN = "TOKEN"
    SYSTEM = "SYSTEM"
    NONE = "NONE"


@dataclass(frozen=True)
class Principal:
    id: str = "anonymous"
    role: str = "agent"
    authenticated: bool = False
    principal_type: PrincipalType = PrincipalType.AGENT
    trust_tier: TrustTier = TrustTier.RESTRICTED
    credential_source: CredentialSource = CredentialSource.LOCAL_STDIO
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def type(self) -> str:
        return self.principal_type.value

    @classmethod
    def anonymous(cls) -> "Principal":
        return cls(
            id="anonymous",
            role="anonymous",
            authenticated=False,
            principal_type=PrincipalType.AGENT,
            trust_tier=TrustTier.UNTRUSTED,
            credential_source=CredentialSource.NONE,
        )

    @classmethod
    def local_agent(cls, agent_id: str = "local_agent") -> "Principal":
        return cls(
            id=agent_id,
            role="agent",
            authenticated=False,
            principal_type=PrincipalType.AGENT,
            trust_tier=TrustTier.RESTRICTED,
            credential_source=CredentialSource.LOCAL_STDIO,
        )

    @classmethod
    def human_operator(cls, operator_id: str = "human_operator") -> "Principal":
        return cls(
            id=operator_id,
            role="operator",
            authenticated=True,
            principal_type=PrincipalType.HUMAN,
            trust_tier=TrustTier.PRIVILEGED,
            credential_source=CredentialSource.LOCAL_STDIO,
        )

    @classmethod
    def system(cls, system_id: str = "system") -> "Principal":
        return cls(
            id=system_id,
            role="system",
            authenticated=True,
            principal_type=PrincipalType.SYSTEM,
            trust_tier=TrustTier.PRIVILEGED,
            credential_source=CredentialSource.SYSTEM,
        )


@dataclass(frozen=True)
class RequestContext:
    capability: str
    principal: Principal = field(default_factory=Principal)
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    metadata: Dict[str, Any] = field(default_factory=dict)
