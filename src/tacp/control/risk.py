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


class RiskEvaluator:
    @staticmethod
    def evaluate(
        capability: str,
        is_read_only: bool = True,
        dry_run: bool = False,
    ) -> RiskLevel:
        if capability == "workspace.patch":
            return RiskLevel.R1 if dry_run else RiskLevel.R2
        if not is_read_only:
            return RiskLevel.CRITICAL
        if capability in ["fs.read", "process.inspect"]:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW
