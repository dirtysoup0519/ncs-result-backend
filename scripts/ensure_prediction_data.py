"""Publish AI prediction for the current ADS batch when a model package is available."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import sys
from uuid import uuid4
import zipfile

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ncs_backend.db_console.connections import connection_factory_from_url, database_dialect_from_url
from ncs_backend.prediction.management import activate_model, register_model
from ncs_backend.prediction.model_registry import ModelPackage
from ncs_backend.prediction.runner import PredictionRunner
from ncs_backend.shared.local_config import load_local_config


MODEL_ROOT = REPO_ROOT / "data_exchange" / "models"
MODEL_CACHE = REPO_ROOT / ".local" / "models"
NO_MODEL_EXIT = 3


def main() -> int:
    load_local_config(REPO_ROOT / ".local" / "ncs.env")
    database_url = os.getenv("NCS_DATABASE_URL")
    if not database_url:
        print("DATABASE_URL_MISSING: run setup_new_machine.cmd first", file=sys.stderr)
        return 2
    source_batch = _published_load_batch(database_url)
    if not source_batch:
        print("PREDICTION_INPUT_MISSING: load_hourly is not published", file=sys.stderr)
        return 4
    if _prediction_ready(database_url, source_batch):
        print(f"PREDICTION_DATA_READY sourceBatchId={source_batch}")
        return 0

    model_source = _newest_model()
    if model_source is None:
        print(f"NO_MODEL: place a model directory, ZIP or PTH in {MODEL_ROOT}", file=sys.stderr)
        return NO_MODEL_EXIT
    model_path = _materialize_model(model_source)
    package = ModelPackage.open(model_path)
    connection = connection_factory_from_url(database_url)()
    dialect = database_dialect_from_url(database_url)
    try:
        register_model(connection, package, dialect=dialect)
        activate_model(connection, package.model_code, package.model_version, dialect=dialect)
        run_id = PredictionRunner(dialect=dialect).run(connection, package)
    finally:
        connection.close()
    print(f"PREDICTION_DATA_IMPORTED predictionRunId={run_id} sourceBatchId={source_batch}")
    return 0


def _published_load_batch(database_url: str) -> str | None:
    connection = connection_factory_from_url(database_url)()
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT batch_id FROM ctl_publication "
            "WHERE dataset_code = 'load_hourly' AND status = 'PUBLISHED' LIMIT 1"
        )
        row = cursor.fetchone()
        return str(row[0]) if row else None
    finally:
        cursor.close()
        connection.close()


def _prediction_ready(database_url: str, source_batch: str) -> bool:
    connection = connection_factory_from_url(database_url)()
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT COUNT(*) FROM ctl_prediction_run "
            "WHERE source_batch_id = %s AND status = 'PUBLISHED'",
            (source_batch,),
        )
        row = cursor.fetchone()
        return bool(row and int(row[0]) > 0)
    finally:
        cursor.close()
        connection.close()


def _newest_model() -> Path | None:
    MODEL_ROOT.mkdir(parents=True, exist_ok=True)
    candidates = [
        path for path in MODEL_ROOT.iterdir()
        if path.is_dir() or path.name.lower().endswith((".zip", ".pth"))
    ]
    return max(candidates, key=lambda path: path.stat().st_mtime).resolve() if candidates else None


def _materialize_model(source: Path) -> Path:
    if source.is_dir() or source.suffix.lower() == ".pth":
        return source
    MODEL_CACHE.mkdir(parents=True, exist_ok=True)
    target = MODEL_CACHE / f"{source.stem}-{uuid4().hex[:8]}"
    target.mkdir()
    with zipfile.ZipFile(source) as archive:
        for member in archive.infolist():
            destination = (target / member.filename).resolve()
            if target.resolve() not in destination.parents and destination != target.resolve():
                raise ValueError(f"unsafe model archive member: {member.filename}")
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError(f"model archive link is not allowed: {member.filename}")
        archive.extractall(target)
    weights = tuple(target.rglob("model_weights.pth")) or tuple(target.rglob("model_all.pth"))
    if len(weights) != 1:
        raise ValueError("model ZIP must contain exactly one supported weights file")
    return weights[0].parent


if __name__ == "__main__":
    raise SystemExit(main())
