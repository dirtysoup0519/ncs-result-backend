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
from ncs_backend.shared.db import DatabaseDialect, SQLITE_DIALECT


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

    def __init__(self, connection_factory: ConnectionFactory, *, dialect: DatabaseDialect = SQLITE_DIALECT) -> None:
        self._connection_factory = connection_factory
        self._empty = EmptyDashboardRepository()
        self._dialect = dialect

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

    def filter_options(self, topic: str) -> Mapping[str, Any]:
        resource = {
            "globalStatus": "data_status",
            "overview": "overview",
            "platformDistribution": "platform",
            "durationDistribution": "duration",
            "weekdayWeekendProfile": "weekday_weekend",
            "loadPrediction": "prediction",
            "stationHourHeatmap": "heatmap",
            "stationRanking": "ranking",
            "feeEnergyTrend": "fee_energy_trend",
            "processSummary": "process_summary",
        }.get(topic)
        if resource is None:
            return {"topic": topic, "regions": [], "stations": [], "dateRange": None}

        stations: list[dict[str, Any]] = []
        if resource in {"ranking", "heatmap"}:
            try:
                station_rows = self._query(
                    f"SELECT DISTINCT station_id, station_name, region_id FROM {self.VIEW_BY_RESOURCE[resource]} ORDER BY station_id",
                    (),
                )
            except Exception:
                station_rows = []
            stations = [
                {"stationId": row.get("station_id"), "stationName": row.get("station_name"), "regionId": row.get("region_id")}
                for row in station_rows
            ]

        date_range = None
        if resource in self.VIEW_BY_RESOURCE:
            view = self.VIEW_BY_RESOURCE[resource]
            date_column = "period_start" if resource == "fee_energy_trend" else "start_date" if resource == "weekday_weekend" else "data_date"
            try:
                row = self._query(
                    f"SELECT MIN({date_column}) AS min_date, MAX({date_column}) AS max_date FROM {view}",
                    (),
                )[0]
            except Exception:
                row = {}
            if row.get("min_date") is not None:
                date_range = {"minDate": _date_text(row.get("min_date")), "maxDate": _date_text(row.get("max_date"))}
        return {"topic": topic, "regions": [], "stations": stations, "dateRange": date_range}

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
            SELECT metric_code, display_name, metric_value, unit, `precision`,
                   data_date, data_version, generated_at, staleness
            FROM api_v1_dashboard_overview
            WHERE {' AND '.join(where)}
            ORDER BY metric_code
            """,
            values,
        )
        mapped_items = [
            {
                "metricCode": row.get("metric_code"),
                "displayName": row.get("display_name"),
                "value": _metric_value(row.get("metric_value"), row.get("unit")),
                "unit": row.get("unit"),
                "precision": _integer(row.get("precision")),
            }
            for row in rows
        ]
        return self._payload({"items": mapped_items}, rows)

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
        by_code = {item["bucketCode"]: item for item in items}
        items = []
        for item in _duration_defaults():
            items.append({**item, **by_code.get(item["bucketCode"], {})})
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

    def _fetch_heatmap(self, params: Mapping[str, Any]) -> QueryPayload:
        metric = params.get("metric", "kwh")
        where = ["(data_date IS NULL OR data_date = (SELECT MAX(data_date) FROM api_v1_station_hour_heatmap))", "metric = ?"]
        values: list[Any] = [metric]
        if params.get("regionId") is not None:
            where.append("region_id = ?")
            values.append(params["regionId"])
        station_ids = _split_ids(params.get("stationIds"))
        if station_ids:
            where.append("station_id IN (" + ",".join("?" for _ in station_ids) + ")")
            values.extend(station_ids)
        rows = self._query(
            f"""
            SELECT station_id, station_name, hour, value, is_observed,
                   metric_code, unit, data_date, data_version, generated_at, staleness
            FROM api_v1_station_hour_heatmap
            WHERE {' AND '.join(where)}
            ORDER BY value DESC, station_id ASC, hour ASC
            """,
            values,
        )
        limit = int(params.get("limit", 8))
        selected_stations: list[Any] = []
        for row in rows:
            station_id = row.get("station_id")
            if station_id not in selected_stations:
                selected_stations.append(station_id)
            if len(selected_stations) >= limit:
                break
        selected = set(selected_stations)
        station_rows = {row.get("station_id"): row for row in rows if row.get("station_id") in selected}
        point_rows = {
            (row.get("station_id"), _integer(row.get("hour"))): row
            for row in rows
            if row.get("station_id") in selected
        }
        points = []
        for station_id in selected_stations:
            for hour in range(24):
                row = point_rows.get((station_id, hour))
                points.append(
                    {
                        "stationId": station_id,
                        "hour": hour,
                        "value": _decimal_text(row.get("value")) if row is not None else "0",
                        "isObserved": _bool(row.get("is_observed")) if row is not None else False,
                    }
                )
        values_for_range = [row.get("value") for row in rows if row.get("station_id") in selected and row.get("value") is not None]
        metric_code = _metric_code(rows[0].get("metric_code") if rows else None, metric)
        unit = rows[0].get("unit") if rows else _heatmap_unit(metric)
        data = {
            "availability": "AVAILABLE" if rows else "UNAVAILABLE",
            "metricCode": metric_code,
            "unit": unit,
            "hours": list(range(24)),
            "stations": [
                {"stationId": station_id, "stationName": row.get("station_name")}
                for station_id, row in station_rows.items()
            ],
            "points": points,
            "valueRange": {
                "min": _decimal_text(min(values_for_range)),
                "max": _decimal_text(max(values_for_range)),
            }
            if values_for_range
            else None,
        }
        return self._payload(data, rows)

    def _fetch_weekday_weekend(self, params: Mapping[str, Any]) -> QueryPayload:
        where: list[str] = []
        values: list[Any] = []
        if params.get("startDate") is not None:
            where.append("start_date >= ?")
            values.append(params["startDate"])
        if params.get("endDate") is not None:
            where.append("end_date <= ?")
            values.append(params["endDate"])
        if params.get("regionId") is not None:
            where.append("region_id = ?")
            values.append(params["regionId"])
        if not where:
            where.append("1 = 1")
        rows = self._query(
            f"""
            SELECT day_type, metric_key, label, unit, metric_order, max_value,
                   raw_value, normalized_value, normalization_method,
                   normalization_version, start_date, end_date, data_version,
                   generated_at, staleness
            FROM api_v1_weekday_weekend
            WHERE {' AND '.join(where)}
            ORDER BY metric_order, day_type
            """,
            values,
        )
        indicator_rows: dict[str, Mapping[str, Any]] = {}
        series_rows: dict[str, dict[str, Mapping[str, Any]]] = {"WEEKDAY": {}, "WEEKEND": {}}
        for row in rows:
            key = row.get("metric_key")
            indicator_rows.setdefault(key, row)
            series_rows.setdefault(row.get("day_type"), {})[key] = row
        indicators = [
            {
                "key": key,
                "label": row.get("label"),
                "unit": row.get("unit"),
                "max": _decimal_text(row.get("max_value")),
            }
            for key, row in indicator_rows.items()
        ]
        if not indicators:
            indicators = _profile_indicator_defaults()
        indicator_keys = [indicator["key"] for indicator in indicators]
        series = []
        for day_type in ("WEEKDAY", "WEEKEND"):
            day_rows = series_rows.get(day_type, {})
            series.append(
                {
                    "dayType": day_type,
                    "rawValues": [_metric_value(day_rows[key].get("raw_value"), next((item["unit"] for item in indicators if item["key"] == key), None)) if key in day_rows else None for key in indicator_keys],
                    "normalizedValues": [_decimal_text(day_rows[key].get("normalized_value")) for key in indicator_keys]
                    if day_rows and all(key in day_rows and day_rows[key].get("normalized_value") is not None for key in indicator_keys)
                    else None,
                }
            )
        methods = {row.get("normalization_method") for row in rows if row.get("normalization_method")}
        versions = {row.get("normalization_version") for row in rows if row.get("normalization_version")}
        normalization = {"method": next(iter(methods)), "version": next(iter(versions))} if methods and versions else None
        return self._payload({"indicators": indicators, "series": series, "normalization": normalization}, rows)

    def _fetch_prediction(self, params: Mapping[str, Any]) -> QueryPayload:
        where = ["prediction_date = ?", "cutoff_hour = ?"]
        values: list[Any] = [params.get("date"), params.get("cutoffHour")]
        if params.get("stationId") is not None:
            where.append("station_id = ?")
            values.append(params["stationId"])
        if params.get("regionId") is not None:
            where.append("region_id = ?")
            values.append(params["regionId"])
        if params.get("horizon") is not None:
            where.append("horizon = ?")
            values.append(params["horizon"])
        rows = self._query(
            f"""
            SELECT series_type, target_time, order_count, charging_energy,
                   lower_bound, upper_bound, prediction_date, cutoff_hour,
                   forecast_start_at, interval_available, confidence_level,
                   model_version, prediction_run_id, generated_at, data_version,
                   staleness
            FROM api_v1_load_prediction
            WHERE {' AND '.join(where)}
            ORDER BY target_time
            """,
            values,
        )
        actual = []
        forecast = []
        cutoff = params.get("cutoffHour")
        for row in rows:
            target_time = _datetime_value(row.get("target_time"))
            if row.get("series_type") == "ACTUAL":
                if target_time is not None and target_time.hour >= cutoff:
                    continue
                actual.append(
                    {
                        "time": _datetime_text(target_time),
                        "orderCount": _integer(row.get("order_count")),
                        "chargingEnergy": _decimal_text(row.get("charging_energy")),
                        "isObserved": True,
                    }
                )
            else:
                forecast.append(
                    {
                        "time": _datetime_text(target_time),
                        "chargingEnergy": _decimal_text(row.get("charging_energy")),
                        "lowerBound": _decimal_text(row.get("lower_bound")),
                        "upperBound": _decimal_text(row.get("upper_bound")),
                    }
                )
        first = rows[0] if rows else {}
        interval_available = _bool(first.get("interval_available")) if rows else False
        data = {
            "availability": "AVAILABLE" if rows else "UNAVAILABLE",
            "date": _date_text(params.get("date")),
            "cutoffHour": cutoff,
            "forecastStartAt": _datetime_text(first.get("forecast_start_at")),
            "energyUnit": "kWh",
            "orderCountUnit": "count",
            "actual": actual,
            "forecast": forecast,
            "interval": {
                "available": interval_available,
                "confidenceLevel": _decimal_text(first.get("confidence_level")) if interval_available else None,
            },
            "modelVersion": first.get("model_version"),
            "predictionRunId": first.get("prediction_run_id"),
            "generatedAt": _datetime_text(first.get("generated_at")),
        }
        return self._payload(data, rows)

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
            return QueryPayload(
                data={
                    "scope": {"type": "ALL_STATIONS", "stationId": None, "startDate": None, "endDate": None},
                    "recordCount": 0,
                    "sessionCount": 0,
                    "metrics": _process_metric_defaults(),
                }
            )
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
            cursor = self._dialect.cursor(connection)
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


def _split_ids(value: Any) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.upper() in {"1", "TRUE", "T", "Y", "YES"}
    return bool(value)


def _metric_code(value: Any, metric: str) -> str:
    if value:
        return str(value)
    return {"kwh": "charging_energy", "orders": "order_count", "fees": "total_fees"}.get(metric, metric)


def _heatmap_unit(metric: str) -> str:
    return {"kwh": "kWh", "orders": "count", "fees": "CNY"}.get(metric, "kWh")


def _duration_defaults() -> list[dict[str, Any]]:
    return [
        {"bucketCode": "PT0H_PT1H", "label": "0-1h", "lowerMinutes": 0, "upperMinutes": 60, "orderCount": 0, "ratio": "0"},
        {"bucketCode": "PT1H_PT2H", "label": "1-2h", "lowerMinutes": 60, "upperMinutes": 120, "orderCount": 0, "ratio": "0"},
        {"bucketCode": "PT2H_PT3H", "label": "2-3h", "lowerMinutes": 120, "upperMinutes": 180, "orderCount": 0, "ratio": "0"},
        {"bucketCode": "PT3H_PLUS", "label": "3h+", "lowerMinutes": 180, "upperMinutes": None, "orderCount": 0, "ratio": "0"},
    ]


def _profile_indicator_defaults() -> list[dict[str, Any]]:
    return [
        {"key": "order_count", "label": "订单量", "unit": "count", "max": None},
        {"key": "charging_energy", "label": "充电量", "unit": "kWh", "max": None},
        {"key": "total_fees", "label": "费用", "unit": "CNY", "max": None},
        {"key": "user_count", "label": "用户数", "unit": "count", "max": None},
        {"key": "average_charge_hours", "label": "平均时长", "unit": "hour", "max": None},
    ]


def _process_metric_defaults() -> list[dict[str, Any]]:
    return [
        {"metricCode": "average_soc", "value": None, "unit": "ratio", "precision": 3},
        {"metricCode": "average_current", "value": None, "unit": "A", "precision": 1},
        {"metricCode": "average_voltage", "value": None, "unit": "V", "precision": 1},
        {"metricCode": "average_max_temperature", "value": None, "unit": "celsius", "precision": 1},
    ]


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
