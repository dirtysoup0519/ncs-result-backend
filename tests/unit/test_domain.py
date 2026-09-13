from decimal import Decimal

import pytest

from ncs_backend.shared.domain.identifiers import DatasetCode
from ncs_backend.shared.domain.money import Ratio
from ncs_backend.shared.domain.pagination import PageRequest


def test_dataset_code_accepts_contract_code():
    assert str(DatasetCode("ads.order_daily")) == "ads.order_daily"


def test_dataset_code_rejects_unstable_value():
    with pytest.raises(ValueError):
        DatasetCode("ADS ORDER DAILY")


def test_ratio_is_bounded():
    assert Ratio(Decimal("0.25")).value == Decimal("0.25")
    with pytest.raises(ValueError):
        Ratio(Decimal("1.01"))


def test_page_request_is_bounded_and_calculates_offset():
    page = PageRequest(page=3, page_size=20)
    assert page.offset == 40
    with pytest.raises(ValueError):
        PageRequest(page_size=101)
