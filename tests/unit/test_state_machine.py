import pytest

from ncs_backend.shared.domain.enums import BatchStatus, ModelStatus, PredictionRunStatus
from ncs_backend.shared.domain.state_machine import (
    InvalidStateTransition,
    batch_state_machine,
    model_state_machine,
    prediction_state_machine,
)


def test_batch_happy_path():
    machine = batch_state_machine()
    for state in (BatchStatus.LOADING, BatchStatus.VALIDATING, BatchStatus.READY, BatchStatus.PUBLISHED):
        assert machine.transition_to(state) == state


def test_batch_cannot_publish_before_validation():
    with pytest.raises(InvalidStateTransition) as error:
        batch_state_machine().transition_to(BatchStatus.PUBLISHED)
    assert error.value.status_code == 409


def test_model_and_prediction_have_independent_lifecycles():
    model = model_state_machine()
    model.transition_to(ModelStatus.VALIDATED)
    model.transition_to(ModelStatus.ACTIVE)
    assert model.current == ModelStatus.ACTIVE

    prediction = prediction_state_machine()
    prediction.transition_to(PredictionRunStatus.RUNNING)
    prediction.transition_to(PredictionRunStatus.FAILED)
    assert prediction.current == PredictionRunStatus.FAILED
