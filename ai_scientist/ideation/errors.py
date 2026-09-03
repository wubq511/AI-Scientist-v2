from __future__ import annotations

from typing import Any, NoReturn


class IdeationInputError(RuntimeError):
    """A stable, fail-closed error at an ideation input boundary."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.details = details


def fail(code: str, message: str, **details: Any) -> NoReturn:
    raise IdeationInputError(code, message, **details)
