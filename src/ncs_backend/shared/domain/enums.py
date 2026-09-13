"""Shared state and capability enums."""

from enum import StrEnum


class BatchStatus(StrEnum):
    CREATED = "CREATED"
    LOADING = "LOADING"
    VALIDATING = "VALIDATING"
    READY = "READY"
    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class CapabilityStatus(StrEnum):
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"
    UNKNOWN = "UNKNOWN"


class ModelStatus(StrEnum):
    REGISTERED = "REGISTERED"
    VALIDATED = "VALIDATED"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"
    REJECTED = "REJECTED"


class PredictionRunStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    VALIDATING = "VALIDATING"
    READY = "READY"
    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
