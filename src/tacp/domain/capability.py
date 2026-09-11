from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class Capability:
    name: str
    domain: str
    description: str
    read_only: bool = True
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "domain": self.domain,
            "description": self.description,
            "read_only": self.read_only,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
        }
