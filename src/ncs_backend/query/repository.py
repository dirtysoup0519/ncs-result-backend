"""Read-only repository ports and an explicit no-data implementation.

The query layer depends on this module instead of a concrete database driver.
The default repository deliberately returns contract-shaped empty results; it
never fabricates dashboard numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Mapping, Protocol


@dataclass(frozen=True, slots=True)
class QueryPayload:
    """A repository result before the HTTP response envelope is added."""

    data: Mapping[str, Any]
    data_date: date | None = None
    data_version: str | None = None
    generated_at: datetime | None = None
    staleness: str = "UNKNOWN"
    empty: bool = True
    partial: bool = False


class DashboardReadRepository(Protocol):
    """Port implemented by a MySQL ``api_v1_*`` view adapter."""

    def fetch(self, resource: str, params: Mapping[str, Any]) -> QueryPayload:
        """Read one allow-listed dashboard resource."""

    def is_available(self, resource: str) -> bool:
        """Whether the published data source for a resource is usable."""


@dataclass(slots=True)
class EmptyDashboardRepository:
    """Safe local adapter used until the result views are connected."""

    generated_at: datetime | None = None
    _resources: dict[str, QueryPayload] = field(default_factory=dict)

    def fetch(self, resource: str, params: Mapping[str, Any]) -> QueryPayload:
        payload = self._resources.get(resource)
        if payload is not None:
            return payload
        return self._empty(resource)

    def is_available(self, resource: str) -> bool:
        return resource in self._resources and not self._resources[resource].empty

    def _empty(self, resource: str) -> QueryPayload:
        data: dict[str, Any]
        unavailable = resource in {"heatmap", "prediction"}
        if resource == "data_status":
            data = {
                "dataDate": None,
                "sourceRecordCount": 0,
                "stationCount": 0,
                "updatedAt": None,
                "qualityStatus": "UNKNOWN",
                "staleness": "UNKNOWN",
            }
        elif resource == "overview":
            data = {"items": []}
        elif resource == "platform":
            data = {"subject": "ORDER", "totalOrderCount": 0, "unit": "count", "items": []}
        elif resource == "duration":
            data = {"subject": "ORDER", "unit": "count", "items": _duration_buckets()}
        elif resource == "weekday_weekend":
            data = {
                "indicators": _weekday_indicators(),
                "series": [
                    {"dayType": "WEEKDAY", "rawValues": [], "normalizedValues": None},
                    {"dayType": "WEEKEND", "rawValues": [], "normalizedValues": None},
                ],
                "normalization": None,
            }
        elif resource == "heatmap":
            data = {
                "availability": "UNAVAILABLE",
                "metricCode": "charging_energy",
                "unit": "kWh",
                "hours": list(range(24)),
                "stations": [],
                "points": [],
                "valueRange": None,
            }
        elif resource == "ranking":
            data = {"metricCode": "total_fees", "unit": "CNY", "items": []}
        elif resource == "fee_energy_trend":
            data = {
                "granularity": "MONTH",
                "points": [],
                "units": {"totalFees": "CNY", "totalKwh": "kWh"},
            }
        elif resource == "process_summary":
            data = {
                "scope": {"type": "ALL_STATIONS", "stationId": None, "startDate": None, "endDate": None},
                "recordCount": 0,
                "sessionCount": 0,
                "metrics": [
                    {"metricCode": "average_soc", "value": None, "unit": "ratio", "precision": 3},
                    {"metricCode": "average_current", "value": None, "unit": "A", "precision": 1},
                    {"metricCode": "average_voltage", "value": None, "unit": "V", "precision": 1},
                    {"metricCode": "average_max_temperature", "value": None, "unit": "celsius", "precision": 1},
                ],
            }
        elif resource == "prediction":
            data = {
                "availability": "UNAVAILABLE",
                "date": None,
                "cutoffHour": None,
                "forecastStartAt": None,
                "energyUnit": "kWh",
                "orderCountUnit": "count",
                "actual": [],
                "forecast": [],
                "interval": {"available": False, "confidenceLevel": None},
                "modelVersion": None,
                "predictionRunId": None,
                "generatedAt": None,
            }
        else:
            data = {"items": []}
        return QueryPayload(
            data=data,
            generated_at=self.generated_at,
            staleness="UNKNOWN",
            empty=True,
        )


def _duration_buckets() -> list[dict[str, Any]]:
    return [
        {"bucketCode": "PT0H_PT1H", "label": "0-1h", "lowerMinutes": 0, "upperMinutes": 60, "orderCount": 0, "ratio": "0"},
        {"bucketCode": "PT1H_PT2H", "label": "1-2h", "lowerMinutes": 60, "upperMinutes": 120, "orderCount": 0, "ratio": "0"},
        {"bucketCode": "PT2H_PT3H", "label": "2-3h", "lowerMinutes": 120, "upperMinutes": 180, "orderCount": 0, "ratio": "0"},
        {"bucketCode": "PT3H_PLUS", "label": "3h+", "lowerMinutes": 180, "upperMinutes": None, "orderCount": 0, "ratio": "0"},
    ]


def _weekday_indicators() -> list[dict[str, Any]]:
    return [
        {"key": "order_count", "label": "订单量", "unit": "count", "max": None},
        {"key": "charging_energy", "label": "充电量", "unit": "kWh", "max": None},
        {"key": "total_fees", "label": "费用", "unit": "CNY", "max": None},
        {"key": "user_count", "label": "用户数", "unit": "count", "max": None},
        {"key": "average_charge_hours", "label": "平均时长", "unit": "hour", "max": None},
    ]
