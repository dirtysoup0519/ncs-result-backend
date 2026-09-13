import pytest

from ncs_backend.shared.domain.enums import BatchStatus
from ncs_backend.shared.domain.state_machine import (
    InvalidStateTransition,
    batch_state_machine,
)


def test_batch_happy_path():
    machine = batch_state_machine()
    for state in (BatchStatus.LOADING, BatchStatus.VALIDATING, BatchStatus.READY, BatchStatus.PUBLISHED):
        assert machine.transition_to(state) == state


def test_batch_cannot_publish_before_validation():
    with pytest.raises(InvalidStateTransition) as error:
        batch_state_machine().transition_to(BatchStatus.PUBLISHED)
    assert error.value.status_code == 409
