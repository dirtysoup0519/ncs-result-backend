"""Application errors and the stable error response shape."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AppError(Exception):
    code: str
    message: str
    status_code: int = 500
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.message

    def to_dict(self, trace_id: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "data": None,
            "errors": [],
            "meta": {"requestId": trace_id},
        }
        if self.details:
            body["errors"] = [self.details]
        return body


class ConfigurationError(AppError):
    def __init__(self, message: str = "service configuration is incomplete") -> None:
        super().__init__("CONFIGURATION_ERROR", message, 503)
