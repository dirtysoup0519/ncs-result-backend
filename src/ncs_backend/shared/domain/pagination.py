"""Bounded pagination primitives."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PageRequest:
    page: int = 1
    page_size: int = 20
    max_page_size: int = 100

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ValueError("page must be >= 1")
        if self.page_size < 1 or self.page_size > self.max_page_size:
            raise ValueError(f"page_size must be between 1 and {self.max_page_size}")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size
