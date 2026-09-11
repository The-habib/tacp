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
