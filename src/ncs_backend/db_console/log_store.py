"""Thread-safe bounded operation log for the local database console."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Callable


@dataclass(frozen=True, slots=True)
class ConsoleLogEntry:
    sequence: int
    time: datetime
    category: str
    level: str
    action: str
    message: str
    duration_ms: int | None = None


class ConsoleLogStore:
    """Keep the latest console events while preserving a monotonic cursor."""

    def __init__(self, *, max_entries: int = 500, clock: Callable[[], datetime] | None = None) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self._entries: deque[ConsoleLogEntry] = deque(maxlen=max_entries)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = Lock()
        self._next_sequence = 1

    def append(
        self,
        *,
        category: str,
        level: str,
        action: str,
        message: str,
        duration_ms: int | None = None,
    ) -> ConsoleLogEntry:
        with self._lock:
            entry = ConsoleLogEntry(
                sequence=self._next_sequence,
                time=self._clock(),
                category=category,
                level=level,
                action=action,
                message=message,
                duration_ms=duration_ms,
            )
            self._entries.append(entry)
            self._next_sequence += 1
            return entry

    def list(self, *, after: int = 0, limit: int = 200) -> tuple[ConsoleLogEntry, ...]:
        if after < 0:
            raise ValueError("after must be non-negative")
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._lock:
            return tuple(entry for entry in self._entries if entry.sequence > after)[: min(limit, 500)]

    @property
    def last_sequence(self) -> int:
        with self._lock:
            return self._next_sequence - 1
