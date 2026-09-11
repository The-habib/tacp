import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, FrozenSet, Union


class PrincipalType(str, Enum):
    AGENT = "AGENT"
    HUMAN = "HUMAN"
    SYSTEM = "SYSTEM"
    SERVICE = "SERVICE"
    REMOTE_AI = "REMOTE_AI"


class TrustTier(str, Enum):
    UNTRUSTED = "UNTRUSTED"
    RESTRICTED = "RESTRICTED"
    PRIVILEGED = "PRIVILEGED"


class CredentialSource(str, Enum):
    LOCAL_STDIO = "LOCAL_STDIO"
    TOKEN = "TOKEN"
    SYSTEM = "SYSTEM"
    NONE = "NONE"
    TUNNEL = "TUNNEL"


class Role(str, Enum):
    AGENT = "agent"
    OPERATOR = "operator"
    ADMIN = "admin"
    SYSTEM = "system"
    AUDITOR = "auditor"
    ANONYMOUS = "anonymous"


class Authority(str, Enum):
    READ_WORKSPACE = "read:workspace"
    MUTATE_WORKSPACE = "mutate:workspace"
    EXECUTE_COMMAND = "execute:command"
    EXECUTE_DANGEROUS = "execute:dangerous"
    APPROVE_ACTION = "approve:action"
    REVOKE_ACTION = "revoke:action"
    ADMIN_EMERGENCY_STOP = "admin:emergency_stop"
    VIEW_AUDIT = "view:audit"
    OPERATOR_ROLLBACK = "operator:rollback"


@dataclass(frozen=True)
class Principal:
    id: str = "anonymous"
    role: str = "agent"
    authenticated: bool = False
    principal_type: PrincipalType = PrincipalType.AGENT
    trust_tier: TrustTier = TrustTier.RESTRICTED
    credential_source: CredentialSource = CredentialSource.LOCAL_STDIO
    authorities: FrozenSet[str] = field(default_factory=frozenset)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def type(self) -> str:
        return self.principal_type.value

    def has_authority(self, authority: Union[str, Authority]) -> bool:
        """Check whether principal possesses explicit authority or privileged override."""
        if self.trust_tier == TrustTier.PRIVILEGED:
            return True
        auth_val = authority.value if isinstance(authority, Authority) else authority
        return auth_val in self.authorities

    def is_elevated(self) -> bool:
        """Check whether principal belongs to an elevated tier or type."""
        return self.trust_tier == TrustTier.PRIVILEGED or self.principal_type in (
            PrincipalType.HUMAN,
            PrincipalType.SYSTEM,
        )

    @classmethod
    def anonymous(cls) -> "Principal":
        return cls(
            id="anonymous",
            role=Role.ANONYMOUS.value,
            authenticated=False,
            principal_type=PrincipalType.AGENT,
            trust_tier=TrustTier.UNTRUSTED,
            credential_source=CredentialSource.NONE,
            authorities=frozenset(),
        )

    @classmethod
    def local_agent(cls, agent_id: str = "local_agent") -> "Principal":
        return cls(
            id=agent_id,
            role=Role.AGENT.value,
            authenticated=False,
            principal_type=PrincipalType.AGENT,
            trust_tier=TrustTier.RESTRICTED,
            credential_source=CredentialSource.LOCAL_STDIO,
            authorities=frozenset(
                [Authority.READ_WORKSPACE.value, Authority.EXECUTE_COMMAND.value]
            ),
        )

    @classmethod
    def remote_ai(cls, agent_id: str = "remote_chatgpt") -> "Principal":
        return cls(
            id=agent_id,
            role=Role.AGENT.value,
            authenticated=True,
            principal_type=PrincipalType.REMOTE_AI,
            trust_tier=TrustTier.RESTRICTED,
            credential_source=CredentialSource.TUNNEL,
            authorities=frozenset([Authority.READ_WORKSPACE.value]),
        )

    @classmethod
    def human_operator(cls, operator_id: str = "human_operator") -> "Principal":
        return cls(
            id=operator_id,
            role=Role.OPERATOR.value,
            authenticated=True,
            principal_type=PrincipalType.HUMAN,
            trust_tier=TrustTier.PRIVILEGED,
            credential_source=CredentialSource.LOCAL_STDIO,
            authorities=frozenset(a.value for a in Authority),
        )

    @classmethod
    def system(cls, system_id: str = "system") -> "Principal":
        return cls(
            id=system_id,
            role=Role.SYSTEM.value,
            authenticated=True,
            principal_type=PrincipalType.SYSTEM,
            trust_tier=TrustTier.PRIVILEGED,
            credential_source=CredentialSource.SYSTEM,
            authorities=frozenset(a.value for a in Authority),
        )


@dataclass(frozen=True)
class Session:
    session_id: str
    principal: Principal
    created_at: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RequestContext:
    capability: str
    principal: Principal = field(default_factory=Principal)
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    metadata: Dict[str, Any] = field(default_factory=dict)
