"""Build and profile the fixed input contract for load prediction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from typing import Any

from ncs_backend.shared.db import DatabaseDialect, MYSQL_DIALECT, SQLITE_DIALECT


class PredictionDatasetError(ValueError):
    pass


# The frozen prediction contract requires ``forecastStartAt`` to resolve to the
# same business date as ``date`` (docs/预测接口hour跨天扩展说明.md rule 5, enforced
# by dashboardAdapters.js), while the runner starts the forecast one hour after
# the cutoff. A cutoff at 23:00 therefore begins the forecast on the next day and
# the dashboard rejects the entire payload, so no cutoff may resolve past this
# hour. The hour itself belongs to neither series, so 22:00 is still a valid
# cutoff: history runs 0-21 and the forecast covers 23:00 onwards.
SAME_DAY_FORECAST_MAX_CUTOFF_HOUR = 22


@dataclass(frozen=True, slots=True)
class PredictionDataset:
    source_batch_id: str
    data_version: str
    cutoff_time: datetime
    timestamps: tuple[datetime, ...]
    values: tuple[float, ...]
    observed_flags: tuple[bool, ...]
    profile: dict[str, Any]
    tensor: Any
    calendar_tensor: Any
    # Published order counts for the same hours as ``values``. The model only
    # predicts energy, but the dashboard draws observed order counts next to it,
    # so the history has to carry them through to the result rows.
    order_counts: tuple[int | None, ...] = ()


class LoadHourlyDatasetBuilder:
    """Read-only builder for the model's continuous hourly input window."""

    def __init__(self, *, dialect: DatabaseDialect = MYSQL_DIALECT) -> None:
        self._dialect = dialect

    def build(
        self,
        connection: Any,
        *,
        cutoff_time: datetime | str | None = None,
        lookback: int = 512,
        horizon: int = 24,
    ) -> PredictionDataset:
        if lookback < 1:
            raise PredictionDatasetError("lookback must be positive")
        if horizon < 1:
            raise PredictionDatasetError("horizon must be positive")
        cutoff = _parse_datetime(cutoff_time) if cutoff_time is not None else None
        cursor = self._dialect.cursor(connection)
        try:
            if cutoff is None:
                # "Newest available" still has to be renderable, so the implicit
                # window ends at the latest hour that keeps the forecast on the
                # business date rather than at the raw newest row.
                cutoff = self._latest_contract_cutoff(cursor)
            query = (
                "SELECT r.stat_time, r.total_kwh, r.order_count, r.is_observed, r.data_version, r.batch_id "
                "FROM rpt_load_hourly r "
                "JOIN ctl_publication p ON p.dataset_code = 'load_hourly' "
                "AND p.batch_id = r.batch_id AND p.status = 'PUBLISHED' "
            )
            params: list[Any] = []
            if cutoff is not None:
                query += "WHERE r.stat_time <= ? "
                params.append(_db_datetime(cutoff, self._dialect))
            query += "ORDER BY r.stat_time DESC LIMIT ?"
            params.append(lookback)
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
        finally:
            cursor.close()
        if len(rows) < lookback:
            raise PredictionDatasetError(f"load_hourly has only {len(rows)} rows; {lookback} required")
        rows = list(reversed(rows))
        timestamps = tuple(_parse_datetime(row[0]) for row in rows)
        values = tuple(_finite_non_negative(row[1], "total_kwh") for row in rows)
        order_counts = tuple(_optional_non_negative_int(row[2], "order_count") for row in rows)
        observed = tuple(bool(row[3]) for row in rows)
        _check_continuity(timestamps)
        source_batches = {str(row[5]) for row in rows}
        if len(source_batches) != 1:
            raise PredictionDatasetError("input window spans multiple published batches")
        versions = {str(row[4]) for row in rows}
        if len(versions) != 1:
            raise PredictionDatasetError("input window spans multiple data versions")
        actual_cutoff = timestamps[-1]
        if cutoff is not None and actual_cutoff != cutoff:
            raise PredictionDatasetError("cutoff_time must match an available hourly record")
        if actual_cutoff.hour > SAME_DAY_FORECAST_MAX_CUTOFF_HOUR:
            # Refuse at build time instead of publishing a run the dashboard
            # cannot draw: fail loudly here beats a blank prediction panel.
            raise PredictionDatasetError(
                "cutoff_time must be at or before "
                f"{SAME_DAY_FORECAST_MAX_CUTOFF_HOUR}:00 so forecastStartAt stays on the business date"
            )
        profile = _profile(timestamps, values, observed, next(iter(source_batches)), next(iter(versions)))
        tensor, calendar = _build_tensors(timestamps, values, horizon)
        return PredictionDataset(
            source_batch_id=next(iter(source_batches)),
            data_version=next(iter(versions)),
            cutoff_time=actual_cutoff,
            timestamps=timestamps,
            values=values,
            observed_flags=observed,
            profile=profile,
            tensor=tensor,
            calendar_tensor=calendar,
            order_counts=order_counts,
        )

    def _latest_contract_cutoff(self, cursor: Any) -> datetime | None:
        """Newest published hour capped to the last one a forecast may start after."""

        cursor.execute(
            "SELECT MAX(r.stat_time) FROM rpt_load_hourly r "
            "JOIN ctl_publication p ON p.dataset_code = 'load_hourly' "
            "AND p.batch_id = r.batch_id AND p.status = 'PUBLISHED'"
        )
        row = cursor.fetchone()
        if row is None or row[0] is None:
            return None
        newest = _parse_datetime(row[0])
        if newest.hour > SAME_DAY_FORECAST_MAX_CUTOFF_HOUR:
            return newest - timedelta(hours=newest.hour - SAME_DAY_FORECAST_MAX_CUTOFF_HOUR)
        return newest


def _build_tensors(timestamps: tuple[datetime, ...], values: tuple[float, ...], horizon: int) -> tuple[Any, Any]:
    try:
        import numpy as np
        import torch
    except ImportError as exc:  # pragma: no cover
        raise PredictionDatasetError("numpy and torch are required to build model tensors") from exc
    future = tuple(timestamps[-1] + timedelta(hours=index) for index in range(1, horizon + 1))
    calendar = np.asarray([_calendar_row(timestamp) for timestamp in (*timestamps, *future)], dtype=np.float32)
    # The adapter applies checkpoint normalization to the target channel.  The
    # calendar channels use the deterministic cyclic values directly.
    features = np.concatenate([
        np.asarray(values, dtype=np.float32).reshape(-1, 1),
        calendar[: len(values)],
    ], axis=1)
    return torch.from_numpy(features).unsqueeze(0), torch.from_numpy(calendar).unsqueeze(0)


def _calendar_row(timestamp: datetime) -> tuple[float, float, float, float]:
    hour = timestamp.hour
    weekday = timestamp.weekday()
    return (
        math.sin(2 * math.pi * hour / 24),
        math.cos(2 * math.pi * hour / 24),
        math.sin(2 * math.pi * weekday / 7),
        math.cos(2 * math.pi * weekday / 7),
    )


def _check_continuity(timestamps: tuple[datetime, ...]) -> None:
    for previous, current in zip(timestamps, timestamps[1:]):
        if current - previous != timedelta(hours=1):
            raise PredictionDatasetError(f"load_hourly is not continuous between {previous} and {current}")


def _profile(timestamps, values, observed, source_batch_id, data_version) -> dict[str, Any]:
    return {
        "sourceBatchId": source_batch_id,
        "dataVersion": data_version,
        "rowCount": len(values),
        "startTime": timestamps[0].isoformat(sep=" "),
        "endTime": timestamps[-1].isoformat(sep=" "),
        "frequency": "1h",
        "missingHours": 0,
        "observedRows": sum(observed),
        "filledRows": len(observed) - sum(observed),
        "minKwh": min(values),
        "maxKwh": max(values),
        "meanKwh": sum(values) / len(values),
        "qualityStatus": "PASSED",
    }


def _optional_non_negative_int(value: Any, field: str) -> int | None:
    """Order counts are optional in the published hourly source."""
    if value is None:
        return None
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise PredictionDatasetError(f"{field} must be an integer") from exc
    if result < 0:
        raise PredictionDatasetError(f"{field} must be non-negative")
    return result


def _finite_non_negative(value: Any, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise PredictionDatasetError(f"{field} must be numeric") from exc
    if not math.isfinite(result) or result < 0:
        raise PredictionDatasetError(f"{field} must be finite and non-negative")
    return result


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if not isinstance(value, str) or not value.strip():
        raise PredictionDatasetError(f"invalid datetime: {value}")
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError as exc:
        raise PredictionDatasetError(f"invalid datetime: {value}") from exc


def _db_datetime(value: datetime, dialect: DatabaseDialect) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")
