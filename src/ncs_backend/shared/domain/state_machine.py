"""Explicit lifecycle transitions for import, model and prediction workflows."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, Mapping, TypeVar

from ncs_backend.shared.domain.enums import BatchStatus, ModelStatus, PredictionRunStatus
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

MODEL_TRANSITIONS = {
    ModelStatus.REGISTERED: frozenset({ModelStatus.VALIDATED, ModelStatus.REJECTED}),
    ModelStatus.VALIDATED: frozenset({ModelStatus.ACTIVE, ModelStatus.REJECTED}),
    ModelStatus.ACTIVE: frozenset({ModelStatus.RETIRED}),
    ModelStatus.RETIRED: frozenset(),
    ModelStatus.REJECTED: frozenset(),
}

PREDICTION_TRANSITIONS = {
    PredictionRunStatus.CREATED: frozenset({PredictionRunStatus.RUNNING, PredictionRunStatus.FAILED}),
    PredictionRunStatus.RUNNING: frozenset({PredictionRunStatus.VALIDATING, PredictionRunStatus.FAILED}),
    PredictionRunStatus.VALIDATING: frozenset(
        {PredictionRunStatus.READY, PredictionRunStatus.REJECTED, PredictionRunStatus.FAILED}
    ),
    PredictionRunStatus.READY: frozenset({PredictionRunStatus.PUBLISHED, PredictionRunStatus.FAILED}),
    PredictionRunStatus.PUBLISHED: frozenset(),
    PredictionRunStatus.REJECTED: frozenset(),
    PredictionRunStatus.FAILED: frozenset(),
}


def batch_state_machine(current: BatchStatus = BatchStatus.CREATED) -> StateMachine[BatchStatus]:
    return StateMachine(current, BATCH_TRANSITIONS)


def model_state_machine(current: ModelStatus = ModelStatus.REGISTERED) -> StateMachine[ModelStatus]:
    return StateMachine(current, MODEL_TRANSITIONS)


def prediction_state_machine(
    current: PredictionRunStatus = PredictionRunStatus.CREATED,
) -> StateMachine[PredictionRunStatus]:
    return StateMachine(current, PREDICTION_TRANSITIONS)
