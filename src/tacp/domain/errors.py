from enum import Enum
from typing import Any, Dict, Optional


class ErrorCode(str, Enum):
    INVALID_INPUT = "INVALID_INPUT"
    NOT_FOUND = "NOT_FOUND"
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    OUTSIDE_WORKSPACE = "OUTSIDE_WORKSPACE"
    SECRET_PROTECTED = "SECRET_PROTECTED"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    UNAVAILABLE = "UNAVAILABLE"
    # Phase 2 Governance & Mutation Error Codes
    POLICY_DENIED = "POLICY_DENIED"
    MUTATION_DISABLED = "MUTATION_DISABLED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    APPROVAL_ALREADY_USED = "APPROVAL_ALREADY_USED"
    CONFLICT = "CONFLICT"
    UNSUPPORTED_FILE = "UNSUPPORTED_FILE"
    PATCH_INVALID = "PATCH_INVALID"
    CHECKPOINT_FAILED = "CHECKPOINT_FAILED"
    MUTATION_FAILED = "MUTATION_FAILED"
    ROLLBACK_FAILED = "ROLLBACK_FAILED"
    LOCK_CONFLICT = "LOCK_CONFLICT"
    LOCK_EXPIRED = "LOCK_EXPIRED"
    LEASE_EXPIRED = "LEASE_EXPIRED"
    # Phase 4 Execution Error Codes
    EXECUTION_DISABLED = "EXECUTION_DISABLED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    EXECUTION_TIMEOUT = "EXECUTION_TIMEOUT"
    EXECUTION_CANCELLED = "EXECUTION_CANCELLED"


class TacpError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": {
                "code": self.code.value,
                "message": self.message,
                "details": self.details,
            }
        }


class TacpSecurityError(TacpError):
    def __init__(
        self, code: ErrorCode, message: str, details: Optional[Dict[str, Any]] = None
    ) -> None:
        super().__init__(code, message, details)


class TacpNotFoundError(TacpError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(ErrorCode.NOT_FOUND, message, details)


class TacpValidationError(TacpError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(ErrorCode.INVALID_INPUT, message, details)


class TacpConflictError(TacpError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(ErrorCode.CONFLICT, message, details)


class TacpPolicyError(TacpSecurityError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(ErrorCode.POLICY_DENIED, message, details)


class TacpApprovalRequiredError(TacpSecurityError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(ErrorCode.APPROVAL_REQUIRED, message, details)
