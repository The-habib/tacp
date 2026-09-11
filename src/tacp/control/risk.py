from enum import Enum


class RiskLevel(str, Enum):
    # Phase 2 6-tier risk levels
    R0 = "R0"  # Observation / Read-only
    R1 = "R1"  # Low-impact mutation / dry-run
    R2 = "R2"  # Moderate reversible mutation (workspace.patch)
    R3 = "R3"  # Sensitive operation / multi-file / install
    R4 = "R4"  # High-impact operation / process termination
    R5 = "R5"  # Critical / privileged

    # Backward compatibility aliases
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TrustProfile(str, Enum):
    """User-configurable trust profiles governing approval frequency and lease usage."""

    STRICT = "STRICT"
    BALANCED = "BALANCED"
    DEVELOPER = "DEVELOPER"
    LOCKDOWN = "LOCKDOWN"
    REMOTE_READ_ONLY = "REMOTE_READ_ONLY"


class PolicyOutcome(str, Enum):
    """Four formal policy outcomes under Risk-Adaptive Governance."""

    ALLOW = "ALLOW"
    ALLOW_WITH_LEASE = "ALLOW_WITH_LEASE"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"


class RiskEvaluator:
    @staticmethod
    def evaluate(
        capability: str,
        is_read_only: bool = True,
        dry_run: bool = False,
    ) -> RiskLevel:
        if dry_run:
            return RiskLevel.R1

        if capability in ("workspace.patch", "workspace.patch_batch"):
            return RiskLevel.R2

        if capability == "execution.request":
            return RiskLevel.R3

        if capability in ("emergency_stop", "policy.reconfigure"):
            return RiskLevel.R5

        if capability in (
            "system.inspect",
            "system.health",
            "system.version",
            "capabilities.list",
            "workspace.list",
            "workspace.inspect",
            "fs.list",
            "fs.stat",
            "fs.read",
            "fs.search",
            "process.list",
            "process.inspect",
            "audit.recent",
            "audit.verify_integrity",
            "execution.list",
            "execution.inspect",
        ):
            return RiskLevel.R0

        if not is_read_only:
            return RiskLevel.CRITICAL

        if capability in ["fs.read", "process.inspect"]:
            return RiskLevel.MEDIUM

        return RiskLevel.LOW
