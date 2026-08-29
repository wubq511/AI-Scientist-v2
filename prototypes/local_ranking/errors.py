from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class HarnessError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def as_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            value["details"] = self.details
        return value


def fail(code: str, message: str, **details: Any) -> None:
    raise HarnessError(code, message, details or None)
