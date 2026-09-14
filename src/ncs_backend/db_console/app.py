"""Flask application for the small local database console."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from flask import Flask, jsonify, render_template, request

from ncs_backend.db_console.connections import connection_factory_from_url
from ncs_backend.db_console.log_store import ConsoleLogEntry, ConsoleLogStore
from ncs_backend.db_console.runtime import (
    DatabaseRuntime,
    DatabaseRuntimeError,
    UnmanagedDatabaseRuntime,
    WindowsServiceDatabaseRuntime,
)
from ncs_backend.db_console.sql_executor import SqlExecutionError, SqlExecutor, json_value
from ncs_backend.shared.config import Settings
from ncs_backend.shared.errors import AppError


def create_app(
    settings: Settings | None = None,
    *,
    connection_factory=None,
    runtime: DatabaseRuntime | None = None,
    log_store: ConsoleLogStore | None = None,
    sql_executor: SqlExecutor | None = None,
) -> Flask:
    current = settings or Settings.from_env()
    logs = log_store or ConsoleLogStore()
    factory = connection_factory
    if factory is None and current.database_url:
        try:
            factory = connection_factory_from_url(current.database_url)
        except ValueError as exc:
            raise AppError("DB_CONSOLE_NOT_CONFIGURED", str(exc), 503) from exc
    selected_runtime = runtime or _runtime_from_settings(current)
    executor = sql_executor or (
        SqlExecutor(factory, logs, max_rows=current.db_console_max_rows) if factory else None
    )

    app = Flask(__name__, template_folder="templates", static_folder="static", static_url_path="/internal/db-console/static")
    app.config.update(
        NCS_DB_CONSOLE_SETTINGS=current,
        NCS_DB_CONSOLE_LOGS=logs,
        NCS_DB_CONSOLE_RUNTIME=selected_runtime,
        NCS_DB_CONSOLE_EXECUTOR=executor,
    )

    @app.get("/db-console")
    def page():
        return render_template("db_console.html")

    @app.get("/internal/db-console/status")
    def status():
        connection_status = "DISCONNECTED"
        if factory is not None:
            try:
                connection = factory()
                cursor = connection.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                cursor.close()
                connection.close()
                connection_status = "CONNECTED"
            except Exception:
                connection_status = "DISCONNECTED"
        try:
            runtime_status = selected_runtime.status()
        except DatabaseRuntimeError:
            runtime_status = "UNKNOWN"
        return _success(
            {
                "databaseType": _database_type(current.database_url),
                "runtimeMode": selected_runtime.mode,
                "runtimeStatus": runtime_status,
                "connectionStatus": connection_status,
                "databaseName": _database_name(current.database_url),
                "startStopSupported": selected_runtime.start_stop_supported,
                "checkedAt": datetime.now().astimezone(),
            }
        )

    @app.post("/internal/db-console/runtime")
    def runtime_action():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or payload.get("action") not in {"START", "STOP", "RESTART"}:
            raise AppError("DB_RUNTIME_ACTION_INVALID", "action must be START, STOP or RESTART", 400)
        action = payload["action"]
        try:
            result = getattr(selected_runtime, action.lower())()
        except DatabaseRuntimeError as exc:
            raise AppError(exc.code, str(exc), 409 if exc.code == "DB_RUNTIME_NOT_MANAGED" else 503) from exc
        logs.append(category="DB", level="INFO", action=action, message=f"数据库服务状态：{result}")
        return _success({"action": action, "runtimeStatus": result, "connectionStatus": "UNKNOWN"})

    @app.post("/internal/db-console/sql")
    def execute_sql():
        if executor is None:
            raise AppError("DB_CONSOLE_NOT_CONFIGURED", "database connection is not configured", 503)
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or not isinstance(payload.get("statement"), str):
            raise AppError("SQL_STATEMENT_REQUIRED", "statement is required", 400)
        try:
            result = executor.execute(payload["statement"])
        except ValueError as exc:
            code = "SQL_STATEMENT_REQUIRED" if "required" in str(exc) else "SQL_STATEMENT_INVALID"
            raise AppError(code, str(exc), 400) from exc
        except SqlExecutionError as exc:
            raise AppError(
                "SQL_EXECUTION_FAILED",
                "SQL 执行失败",
                400,
                {"queryId": exc.query_id, "statementType": exc.statement_type, "databaseMessage": str(exc.cause)[:300]},
            ) from exc
        return _success(
            {
                "queryId": result.query_id,
                "statementType": result.statement_type,
                "columns": list(result.columns),
                "rows": [[json_value(value) for value in row] for row in result.rows],
                "rowCount": result.row_count,
                "affectedRows": result.affected_rows,
                "truncated": result.truncated,
                "durationMs": result.duration_ms,
            }
        )

    @app.get("/internal/db-console/logs")
    def list_logs():
        try:
            after = int(request.args.get("after", "0"))
            limit = int(request.args.get("limit", "200"))
        except ValueError as exc:
            raise AppError("LOG_CURSOR_INVALID", "after and limit must be integers", 400) from exc
        if after < 0 or not 1 <= limit <= 500:
            raise AppError("LOG_CURSOR_INVALID", "after must be non-negative and limit must be 1..500", 400)
        entries = logs.list(after=after, limit=limit)
        return _success({"items": [_log_json(entry) for entry in entries], "lastSequence": logs.last_sequence})

    @app.errorhandler(AppError)
    def handle_app_error(error: AppError):
        return jsonify(error.to_dict()), error.status_code

    return app


def _runtime_from_settings(settings: Settings) -> DatabaseRuntime:
    if settings.db_runtime_mode == "windows_service" and settings.db_service_name:
        return WindowsServiceDatabaseRuntime(settings.db_service_name)
    return UnmanagedDatabaseRuntime()


def _success(data: Any):
    return jsonify({"code": "OK", "message": "ok", "data": _json_value(data), "meta": {}})


def _log_json(entry: ConsoleLogEntry) -> dict[str, Any]:
    return {
        "sequence": entry.sequence,
        "time": entry.time,
        "category": entry.category,
        "level": entry.level,
        "action": entry.action,
        "message": entry.message,
        "durationMs": entry.duration_ms,
    }


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime, Decimal)):
        return json_value(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _database_type(database_url: str | None) -> str:
    if not database_url:
        return "unknown"
    return "sqlite" if database_url.startswith("sqlite:") else "mysql"


def _database_name(database_url: str | None) -> str | None:
    if not database_url:
        return None
    return database_url.rsplit("/", 1)[-1].split("?", 1)[0] or None
