"""Composable in-memory quality rules used before storage adapters exist."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, Iterable, Mapping, Protocol, Sequence

from ncs_backend.shared.contracts.schema import DatasetSchema, FieldDefinition, FieldType

Row = Mapping[str, Any]


class QualitySeverity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass(frozen=True, slots=True)
class QualityIssue:
    rule_code: str
    message: str
    severity: QualitySeverity = QualitySeverity.ERROR
    row_index: int | None = None
    field: str | None = None


@dataclass(frozen=True, slots=True)
class QualityReport:
    dataset_code: str
    row_count: int
    issues: tuple[QualityIssue, ...]

    @property
    def passed(self) -> bool:
        return not any(issue.severity == QualitySeverity.ERROR for issue in self.issues)


class QualityRule(Protocol):
    def evaluate(self, rows: Sequence[Row], schema: DatasetSchema) -> Iterable[QualityIssue]: ...


class SchemaRule:
    code = "SCHEMA_MISMATCH"

    def __init__(self, reject_unknown_fields: bool = False) -> None:
        self.reject_unknown_fields = reject_unknown_fields

    def evaluate(self, rows: Sequence[Row], schema: DatasetSchema) -> Iterable[QualityIssue]:
        definitions = {field.name: field for field in schema.fields}
        for index, row in enumerate(rows):
            for field in schema.fields:
                if field.name not in row:
                    yield QualityIssue(self.code, "required schema field is missing", row_index=index, field=field.name)
                    continue
                value = row[field.name]
                if value is None or value == "":
                    continue
                if not _matches_type(value, field):
                    yield QualityIssue(self.code, f"value does not match {field.type.value}", row_index=index, field=field.name)
            if self.reject_unknown_fields:
                for name in set(row) - set(definitions):
                    yield QualityIssue(self.code, "unknown field is not allowed", row_index=index, field=name)


class NonNullRule:
    code = "NULL_NOT_ALLOWED"

    def evaluate(self, rows: Sequence[Row], schema: DatasetSchema) -> Iterable[QualityIssue]:
        required = [field.name for field in schema.fields if not field.nullable]
        for index, row in enumerate(rows):
            for name in required:
                if row.get(name) is None or row.get(name) == "":
                    yield QualityIssue(self.code, "null value is not allowed", row_index=index, field=name)


class UniqueKeyRule:
    code = "DUPLICATE_UNIQUE_KEY"

    def evaluate(self, rows: Sequence[Row], schema: DatasetSchema) -> Iterable[QualityIssue]:
        seen: dict[tuple[Any, ...], int] = {}
        for index, row in enumerate(rows):
            key = tuple(row.get(name) for name in schema.unique_key)
            if key in seen:
                yield QualityIssue(
                    self.code,
                    f"duplicate key; first seen at row {seen[key]}",
                    row_index=index,
                    field=",".join(schema.unique_key),
                )
            else:
                seen[key] = index


class RowCountRule:
    code = "ROW_COUNT_MISMATCH"

    def __init__(self, expected: int) -> None:
        if expected < 0:
            raise ValueError("expected row count must be >= 0")
        self.expected = expected

    def evaluate(self, rows: Sequence[Row], schema: DatasetSchema) -> Iterable[QualityIssue]:
        if len(rows) != self.expected:
            yield QualityIssue(self.code, f"expected {self.expected} rows but received {len(rows)}")


class RangeRule:
    code = "VALUE_OUT_OF_RANGE"

    def __init__(self, field: str, minimum: Decimal | None = None, maximum: Decimal | None = None) -> None:
        if minimum is None and maximum is None:
            raise ValueError("at least one range bound is required")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError("minimum must not exceed maximum")
        self.field = field
        self.minimum = minimum
        self.maximum = maximum

    def evaluate(self, rows: Sequence[Row], schema: DatasetSchema) -> Iterable[QualityIssue]:
        if self.field not in schema.field_names:
            raise ValueError(f"range field is not defined by schema: {self.field}")
        for index, row in enumerate(rows):
            raw = row.get(self.field)
            if raw is None or raw == "":
                continue
            try:
                value = Decimal(str(raw))
            except InvalidOperation:
                continue
            if self.minimum is not None and value < self.minimum:
                yield QualityIssue(self.code, f"value must be >= {self.minimum}", row_index=index, field=self.field)
            if self.maximum is not None and value > self.maximum:
                yield QualityIssue(self.code, f"value must be <= {self.maximum}", row_index=index, field=self.field)


class QualityValidator:
    def __init__(self, rules: Iterable[QualityRule]) -> None:
        self.rules = tuple(rules)

    def validate(self, rows: Iterable[Row], schema: DatasetSchema) -> QualityReport:
        materialized = tuple(rows)
        issues = tuple(issue for rule in self.rules for issue in rule.evaluate(materialized, schema))
        return QualityReport(str(schema.dataset_code), len(materialized), issues)


def _matches_type(value: Any, field: FieldDefinition) -> bool:
    try:
        if field.type == FieldType.STRING:
            return isinstance(value, str)
        if field.type == FieldType.INTEGER:
            if isinstance(value, bool):
                return False
            int(str(value))
            return "." not in str(value)
        if field.type == FieldType.DECIMAL:
            Decimal(str(value))
            return True
        if field.type == FieldType.BOOLEAN:
            return isinstance(value, bool) or str(value).lower() in {"true", "false", "0", "1"}
        if field.type == FieldType.DATE:
            date.fromisoformat(str(value))
            return True
        if field.type == FieldType.DATETIME:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed.tzinfo is not None
    except (TypeError, ValueError, InvalidOperation):
        return False
    return False
