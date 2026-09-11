from enum import Enum


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskEvaluator:
    @staticmethod
    def evaluate(capability: str, is_read_only: bool = True) -> RiskLevel:
        if not is_read_only:
            return RiskLevel.CRITICAL
        if capability in ["fs.read", "process.inspect"]:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW
