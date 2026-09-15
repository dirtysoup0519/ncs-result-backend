from decimal import Decimal

from ncs_backend.query.db_repository import _ratio_text


def test_v32_platform_ratios_match_counts_and_sum_to_one():
    counts = (1662, 3185, 8)
    ratios = [_ratio_text(count, sum(counts)) for count in counts]

    assert ratios == ["0.342327", "0.656025", "0.001648"]
    assert sum(map(Decimal, ratios)) == Decimal("1")


def test_v32_duration_ratios_match_counts_and_sum_to_one():
    counts = (277, 790, 1752, 2036)
    ratios = [_ratio_text(count, sum(counts)) for count in counts]

    assert ratios == ["0.057055", "0.162719", "0.360865", "0.419361"]
    assert sum(map(Decimal, ratios)) == Decimal("1")


def test_ratio_is_zero_when_total_is_zero():
    assert _ratio_text(0, 0) == "0"
