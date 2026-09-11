from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseProvider(ABC):
    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        pass
