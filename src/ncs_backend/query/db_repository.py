"""DB-API read adapter for the stable ``api_v1_*`` result views.

Only canonical view names and columns are present here.  Physical ADS/result
tables are intentionally absent: data-admin owns those and the query service
is allowed to see published views only.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from ncs_backend.query.repository import EmptyDashboardRepository, QueryPayload


ConnectionFactory = Callable[[], Any]


class DbApiDashboardRepository:
    """Read-only repository backed by any DB-API 2.0 connection factory."""

    VIEW_BY_RESOURCE = {
        "data_status": "api_v1_data_status",
        "overview": "api_v1_dashboard_overview",
        "platform": "api_v1_platform_distribution",
        "duration": "api_v1_duration_distribution",
        "weekday_weekend": "api_v1_weekday_weekend",
        "heatmap": "api_v1_station_hour_heatmap",
        "ranking": "api_v1_station_ranking",
        "fee_energy_trend": "api_v1_fee_energy_trend",
        "process_summary": "api_v1_process_summary",
        "prediction": "api_v1_load_prediction",
    }

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._connection_factory = connection_factory
        self._empty = EmptyDashboardRepository()

    def fetch(self, resource: str, params: Mapping[str, Any]) -> QueryPayload:
        method = getattr(self, f"_fetch_{resource}", None)
        if method is None:
            return self._empty.fetch(resource, params)
        return method(params)

    def is_available(self, resource: str) -> bool:
        view = self.VIEW_BY_RESOURCE.get(resource)
        if view is None:
            return False
        try:
            rows = self._query(f"SELECT 1 AS available FROM {view} LIMIT 1", ())
        except Exception:
            return False
        return bool(rows)

    def _fetch_data_status(self, params: Mapping[str, Any]) -> QueryPayload:
        rows = self._query(
            """
            SELECT data_date, source_record_count, station_count, updated_at,
                   quality_status, staleness, data_version
            FROM api_v1_data_status
            WHERE dataset_code = COALESCE(?, dataset_code)
            ORDER BY data_date DESC
            LIMIT 1
            """,
            (params.get("datasetCode"),),
        )
        if not rows:
            return QueryPayload(data={"dataDate": None, "sourceRecordCount": 0, "stationCount": 0, "updatedAt": None, "qualityStatus": "UNKNOWN", "staleness": "UNKNOWN"})
        row = rows[0]
        return self._payload(
            {
                "dataDate": _date_text(row.get("data_date")),
                "sourceRecordCount": _integer(row.get("source_record_count")),
                "stationCount": _integer(row.get("station_count")),
                "updatedAt": _datetime_text(row.get("updated_at")),
                "qualityStatus": row.get("quality_status") or "UNKNOWN",
                "staleness": row.get("staleness") or "UNKNOWN",
            },
            rows,
        )

    def _fetch_overview(self, params: Mapping[str, Any]) -> QueryPayload:
        where, values = _date_region_filter("data_date", params, "api_v1_dashboard_overview")
        rows = self._query(
            f"""
            SELECT metric_code, display_name, metric_value, unit, precision,
                   data_date, data_version, generated_at, staleness
            FROM api_v1_dashboard_overview
            WHERE {' AND '.join(where)}
            ORDER BY metric_code
            """,
            values,
        )
        items = [
            {
                "metricCode": row.get("metric_code"),
                "displayName": row.get("display_name"),
                "value": _metric_value(row.get("metric_value"), row.get("unit")),
                "unit": row.get("unit"),
                "precision": _integer(row.get("precision")),
            }
            for row in rows
        ]
        return self._payload({"items": items}, rows)

    def _fetch_platform(self, params: Mapping[str, Any]) -> QueryPayload:
        where, values = _date_region_filter("data_date", params, "api_v1_platform_distribution")
        rows = self._query(
            f"""
            SELECT platform_code, display_name, order_count, total_fees,
                   order_ratio, data_date, data_version, generated_at, staleness
            FROM api_v1_platform_distribution
            WHERE {' AND '.join(where)}
            ORDER BY platform_code
            """,
            values,
        )
        total = sum(_integer(row.get("order_count")) for row in rows)
        items = [
            {
                "platformCode": row.get("platform_code"),
                "displayName": row.get("display_name"),
                "orderCount": _integer(row.get("order_count")),
                "totalFees": _decimal_text(row.get("total_fees")),
                "orderRatio": _decimal_text(row.get("order_ratio")) if row.get("order_ratio") is not None else _ratio_text(row.get("order_count"), total),
            }
            for row in rows
        ]
        return self._payload({"subject": "ORDER", "totalOrderCount": total, "unit": "count", "items": items}, rows)

    def _fetch_duration(self, params: Mapping[str, Any]) -> QueryPayload:
        where, values = _range_filter("data_date", params, "api_v1_duration_distribution", include_station=True)
        rows = self._query(
            f"""
            SELECT bucket_code, label, lower_minutes, upper_minutes, order_count,
                   ratio, data_date, data_version, generated_at, staleness
            FROM api_v1_duration_distribution
            WHERE {' AND '.join(where)}
            ORDER BY lower_minutes
            """,
            values,
        )
        items = [
            {
                "bucketCode": row.get("bucket_code"),
                "label": row.get("label"),
                "lowerMinutes": _integer(row.get("lower_minutes")),
                "upperMinutes": _integer(row.get("upper_minutes")) if row.get("upper_minutes") is not None else None,
                "orderCount": _integer(row.get("order_count")),
                "ratio": _decimal_text(row.get("ratio")),
            }
            for row in rows
        ]
        return self._payload({"subject": "ORDER", "unit": "count", "items": items}, rows)

    def _fetch_ranking(self, params: Mapping[str, Any]) -> QueryPayload:
        where, values = _range_filter("data_date", params, "api_v1_station_ranking", include_station=False)
        limit = int(params.get("limit", 10))
        rows = self._query(
            f"""
            SELECT station_id, station_name, order_count, total_fees, total_kwh,
                   data_date, data_version, generated_at, staleness
            FROM api_v1_station_ranking
            WHERE {' AND '.join(where)}
            ORDER BY total_fees DESC, station_id ASC
            LIMIT ?
            """,
            (*values, limit),
        )
        items = [
            {
                "rank": index,
                "stationId": row.get("station_id"),
                "stationName": row.get("station_name"),
                "orderCount": _integer(row.get("order_count")),
                "totalFees": _decimal_text(row.get("total_fees")),
                "totalKwh": _decimal_text(row.get("total_kwh")),
                "value": _decimal_text(row.get("total_fees")),
            }
            for index, row in enumerate(rows, start=1)
        ]
        return self._payload({"metricCode": "total_fees", "unit": "CNY", "items": items}, rows)

    def _fetch_fee_energy_trend(self, params: Mapping[str, Any]) -> QueryPayload:
        where, values = _range_filter("period_start", params, "api_v1_fee_energy_trend", include_station=True, date_range=True)
        granularity = params.get("granularity", "MONTH")
        rows = self._query(
            f"""
            SELECT period, order_count, total_fees, total_kwh,
                   data_date, data_version, generated_at, staleness
            FROM api_v1_fee_energy_trend
            WHERE granularity = ? AND {' AND '.join(where)}
            ORDER BY period
            """,
            (granularity, *values),
        )
        points = [
            {
                "period": row.get("period"),
                "orderCount": _integer(row.get("order_count")),
                "totalFees": _decimal_text(row.get("total_fees")),
                "totalKwh": _decimal_text(row.get("total_kwh")),
            }
            for row in rows
        ]
        return self._payload({"granularity": granularity, "points": points, "units": {"totalFees": "CNY", "totalKwh": "kWh"}}, rows)

    def _fetch_process_summary(self, params: Mapping[str, Any]) -> QueryPayload:
        where, values = _range_filter("data_date", params, "api_v1_process_summary", include_station=True)
        rows = self._query(
            f"""
            SELECT scope_type, station_id, start_date, end_date, record_count,
                   session_count, average_soc, average_current, average_voltage,
                   average_max_temperature, data_date, data_version, generated_at, staleness
            FROM api_v1_process_summary
            WHERE {' AND '.join(where)}
            ORDER BY data_date DESC
            LIMIT 1
            """,
            values,
        )
        if not rows:
            return QueryPayload(data={"scope": {"type": "ALL_STATIONS", "stationId": None, "startDate": None, "endDate": None}, "recordCount": 0, "sessionCount": 0, "metrics": []})
        row = rows[0]
        return self._payload(
            {
                "scope": {
                    "type": row.get("scope_type") or "ALL_STATIONS",
                    "stationId": row.get("station_id"),
                    "startDate": _date_text(row.get("start_date")),
                    "endDate": _date_text(row.get("end_date")),
                },
                "recordCount": _integer(row.get("record_count")),
                "sessionCount": _integer(row.get("session_count")),
                "metrics": [
                    {"metricCode": "average_soc", "value": _decimal_text(row.get("average_soc")), "unit": "ratio", "precision": 3},
                    {"metricCode": "average_current", "value": _decimal_text(row.get("average_current")), "unit": "A", "precision": 1},
                    {"metricCode": "average_voltage", "value": _decimal_text(row.get("average_voltage")), "unit": "V", "precision": 1},
                    {"metricCode": "average_max_temperature", "value": _decimal_text(row.get("average_max_temperature")), "unit": "celsius", "precision": 1},
                ],
            },
            rows,
        )

    def _payload(self, data: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> QueryPayload:
        first = rows[0] if rows else {}
        return QueryPayload(
            data=data,
            data_date=_date_value(first.get("data_date")),
            data_version=first.get("data_version"),
            generated_at=_datetime_value(first.get("generated_at")),
            staleness=first.get("staleness") or "UNKNOWN",
            empty=not bool(rows),
        )

    def _query(self, sql: str, parameters: Sequence[Any]) -> list[dict[str, Any]]:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(sql, tuple(parameters))
            description = cursor.description or ()
            columns = [column[0] for column in description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
            cursor.close()
            return rows
        finally:
            connection.close()


def _date_region_filter(column: str, params: Mapping[str, Any], view: str) -> tuple[list[str], list[Any]]:
    where = [f"{column} = COALESCE(?, (SELECT MAX({column}) FROM {view}))"]
    values: list[Any] = [params.get("dataDate")]
    if params.get("regionId") is not None:
        where.append("region_id = ?")
        values.append(params["regionId"])
    return where, values


def _range_filter(column: str, params: Mapping[str, Any], view: str, *, include_station: bool, date_range: bool = False) -> tuple[list[str], list[Any]]:
    where: list[str] = []
    values: list[Any] = []
    if params.get("dataDate") is not None:
        where.append(f"{column} = ?")
        values.append(params["dataDate"])
    if params.get("startDate") is not None:
        where.append(f"{column} >= ?")
        values.append(params["startDate"])
    if params.get("endDate") is not None:
        where.append(f"{column} <= ?")
        values.append(params["endDate"])
    if not where and not date_range:
        where.append(f"{column} = (SELECT MAX({column}) FROM {view})")
    if params.get("regionId") is not None:
        where.append("region_id = ?")
        values.append(params["regionId"])
    if include_station and params.get("stationId") is not None:
        where.append("station_id = ?")
        values.append(params["stationId"])
    if not where:
        where.append("1 = 1")
    return where, values


def _integer(value: Any) -> int | None:
    return None if value is None else int(value)


def _decimal_text(value: Any) -> str | None:
    if value is None:
        return None
    return format(Decimal(str(value)), "f")


def _metric_value(value: Any, unit: Any) -> int | str | None:
    if value is None:
        return None
    if unit == "count":
        return int(value)
    return _decimal_text(value)


def _ratio_text(numerator: Any, denominator: int) -> str:
    if not denominator:
        return "0"
    return _decimal_text(Decimal(int(numerator)) / Decimal(denominator)) or "0"


def _date_value(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _date_text(value: Any) -> str | None:
    parsed = _date_value(value)
    return parsed.isoformat() if parsed else None


def _datetime_value(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _datetime_text(value: Any) -> str | None:
    parsed = _datetime_value(value)
    return parsed.isoformat() if parsed else None
