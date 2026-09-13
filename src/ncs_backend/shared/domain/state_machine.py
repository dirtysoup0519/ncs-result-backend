"""Explicit lifecycle transitions for processed-data import workflows."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, Mapping, TypeVar

from ncs_backend.shared.domain.enums import BatchStatus
from ncs_backend.shared.errors import AppError

StateT = TypeVar("StateT", bound=StrEnum)


class InvalidStateTransition(AppError):
    def __init__(self, current: StrEnum, target: StrEnum) -> None:
        super().__init__(
            code="INVALID_STATE_TRANSITION",
            message=f"cannot transition from {current.value} to {target.value}",
            status_code=409,
            details={"current": current.value, "target": target.value},
        )


@dataclass(slots=True)
class StateMachine(Generic[StateT]):
    current: StateT
    transitions: Mapping[StateT, frozenset[StateT]]

    def can_transition_to(self, target: StateT) -> bool:
        return target in self.transitions.get(self.current, frozenset())

    def transition_to(self, target: StateT) -> StateT:
        if not self.can_transition_to(target):
            raise InvalidStateTransition(self.current, target)
        self.current = target
        return self.current


BATCH_TRANSITIONS = {
    BatchStatus.CREATED: frozenset({BatchStatus.LOADING, BatchStatus.FAILED}),
    BatchStatus.LOADING: frozenset({BatchStatus.VALIDATING, BatchStatus.FAILED}),
    BatchStatus.VALIDATING: frozenset({BatchStatus.READY, BatchStatus.REJECTED, BatchStatus.FAILED}),
    BatchStatus.READY: frozenset({BatchStatus.PUBLISHED, BatchStatus.FAILED}),
    BatchStatus.PUBLISHED: frozenset(),
    BatchStatus.REJECTED: frozenset(),
    BatchStatus.FAILED: frozenset(),
}

def batch_state_machine(current: BatchStatus = BatchStatus.CREATED) -> StateMachine[BatchStatus]:
    return StateMachine(current, BATCH_TRANSITIONS)
