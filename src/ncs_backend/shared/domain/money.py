"""Exact decimal types for amounts and ratios."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Money:
    value: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal):
            raise TypeError("Money requires Decimal")


@dataclass(frozen=True, slots=True)
class Ratio:
    value: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal):
            raise TypeError("Ratio requires Decimal")
        if not Decimal("0") <= self.value <= Decimal("1"):
            raise ValueError("Ratio must be within [0, 1]")
