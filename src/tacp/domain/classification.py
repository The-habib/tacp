from enum import Enum


class DataClassification(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    PRIVATE = "PRIVATE"
    SENSITIVE = "SENSITIVE"
    SECRET = "SECRET"
    CRITICAL = "CRITICAL"
