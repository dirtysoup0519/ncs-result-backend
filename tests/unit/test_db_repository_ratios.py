"""Ratio contract tests for the dashboard read adapter.

The dashboard validates every ratio twice before it renders a component:

* each item ratio must match ``orderCount / totalOrderCount`` inside half of the
  last decimal place of the emitted literal, and
* the ratios of one component must sum to 1 inside the same tolerance.

The upstream ADS percentages are rounded to two decimals before import, so they
neither reconcile with the counts nor sum to exactly 1 (v3.2 platform: 99.99,
v3.2 duration: 100.01).  Recomputing from the counts is therefore part of the
frozen contract — see ``docs/大屏接口冻结合同_v1.md``: ``orderRatio`` is produced
by the backend from the ``totalOrderCount`` of the same response.

The helpers below port the dashboard rule so a regression in the adapter fails
here instead of blanking the component in the browser.
"""

import math
import re
import sqlite3
from decimal import Decimal

from ncs_backend.query.db_repository import DbApiDashboardRepository, _ratio_text

_LITERAL = re.compile(r"^[+-]?(?:(\d+)(?:\.(\d*))?|\.(\d+))(?:[eE]([+-]?\d+))?$")

# Upstream values as delivered by the v3.2 package: order_ratio is a percentage
# rounded to two decimals, stored as a fraction in DECIMAL(24, 8) columns.  The
# literals below keep the eight decimals MySQL returns, because the dashboard
# infers its tolerance from the emitted literal: passing the stored value
# through turns the platform check into a 5e-9 window while the ratio itself is
# off by 2.8e-5, and the duration ratios add up to 1.0001.
UPSTREAM_PLATFORM = (
    ("ANDROID", "Android", 1662, "0.34230000"),
    ("IOS", "iOS", 3185, "0.65600000"),
    ("WEB", "Web", 8, "0.00160000"),
)
UPSTREAM_DURATION = (
    ("1", "0-1h", 0, 60, 277, "0.05710000"),
    ("2", "1-2h", 60, 120, 790, "0.16270000"),
    ("3", "2-3h", 120, 180, 1752, "0.36090000"),
    ("4", "3h+", 180, None, 2036, "0.41940000"),
)


def _literal_tolerance(value: str) -> float:
    """Half of the last decimal place the dashboard can infer from ``value``."""
    match = _LITERAL.match(value.strip())
    if match is None:
        return 1e-12
    fraction_digits = len(match.group(2) or match.group(3) or "")
    exponent = int(match.group(4) or 0)
    if fraction_digits == 0 and exponent == 0:
        return 1e-12
    step = 10 ** (exponent - fraction_digits)
    tolerance = abs(step) / 2
    return tolerance + 1e-12 if math.isfinite(tolerance) and tolerance > 0 else 1e-12


def _assert_dashboard_accepts(context, raw_ratios, parsed_ratios, counts, total):
    for text, ratio, count in zip(raw_ratios, parsed_ratios, counts):
        assert abs(ratio - count / total) <= _literal_tolerance(text), f"{context} item ratio is inconsistent with count/total"
    tolerance = sum(_literal_tolerance(text) for text in raw_ratios) + 1e-12
    assert abs(sum(parsed_ratios) - 1) <= tolerance, f"{context} ratio sum {sum(parsed_ratios)} exceeds the rounding tolerance"


def _repository(tmp_path):
    database = tmp_path / "views.sqlite"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE api_v1_platform_distribution (
            platform_code TEXT, display_name TEXT, order_count INTEGER, total_fees TEXT,
            order_ratio TEXT, data_date TEXT, data_version TEXT, generated_at TEXT, staleness TEXT
        );
        CREATE TABLE api_v1_duration_distribution (
            bucket_code TEXT, label TEXT, lower_minutes INTEGER, upper_minutes INTEGER,
            order_count INTEGER, ratio TEXT, data_date TEXT, data_version TEXT,
            generated_at TEXT, staleness TEXT, region_id TEXT, station_id TEXT
        );
        """
    )
    stamp = "2026-09-15T06:00:00+00:00"
    connection.executemany(
        "INSERT INTO api_v1_platform_distribution VALUES (?, ?, ?, '0', ?, '2019-12-31', '2.2.0', ?, 'FRESH')",
        [(code, name, count, ratio, stamp) for code, name, count, ratio in UPSTREAM_PLATFORM],
    )
    connection.executemany(
        "INSERT INTO api_v1_duration_distribution VALUES (?, ?, ?, ?, ?, ?, '2019-12-31', '2.2.0', ?, 'FRESH', NULL, NULL)",
        [(code, label, lower, upper, count, ratio, stamp) for code, label, lower, upper, count, ratio in UPSTREAM_DURATION],
    )
    connection.commit()
    connection.close()
    return DbApiDashboardRepository(lambda: sqlite3.connect(database))


def test_platform_payload_reconciles_with_total_order_count(tmp_path):
    payload = _repository(tmp_path).fetch("platform", {}).data
    items = payload["items"]
    total = payload["totalOrderCount"]

    assert [item["orderCount"] for item in items] == [1662, 3185, 8]
    assert sum(item["orderCount"] for item in items) == total
    _assert_dashboard_accepts(
        "platform",
        [item["orderRatio"] for item in items],
        [float(item["orderRatio"]) for item in items],
        [item["orderCount"] for item in items],
        total,
    )


def test_duration_payload_ratios_sum_to_one_within_rounding(tmp_path):
    items = _repository(tmp_path).fetch("duration", {}).data["items"]

    assert [item["bucketCode"] for item in items] == ["PT0H_PT1H", "PT1H_PT2H", "PT2H_PT3H", "PT3H_PLUS"]
    _assert_dashboard_accepts(
        "duration",
        [item["ratio"] for item in items],
        [float(item["ratio"]) for item in items],
        [item["orderCount"] for item in items],
        sum(item["orderCount"] for item in items),
    )


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
