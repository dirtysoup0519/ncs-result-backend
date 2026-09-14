"""Flask application for the small local database console."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from flask import Flask, jsonify, render_template, request

from ncs_backend.db_console.connections import connection_factory_from_url, database_dialect_from_url
from ncs_backend.db_console.log_store import ConsoleLogEntry, ConsoleLogStore
from ncs_backend.db_console.maintenance import MaintenanceError, MaintenanceOperations
from ncs_backend.db_console.runtime import (
    DatabaseRuntime,
    DatabaseRuntimeError,
    UnmanagedDatabaseRuntime,
    WindowsServiceDatabaseRuntime,
)
from ncs_backend.db_console.schema_inspector import SchemaInspector
from ncs_backend.db_console.script_runner import ScriptRunner
from ncs_backend.db_console.sql_executor import SqlExecutionError, SqlExecutor, json_value
from ncs_backend.db_console.sql_identifiers import IdentifierError
from ncs_backend.db_console.table_operations import TableOperationError, TableOperations
from ncs_backend.shared.config import Settings
from ncs_backend.shared.db import DatabaseDialect
from ncs_backend.shared.errors import AppError


def create_app(
    settings: Settings | None = None,
    *,
    connection_factory=None,
    dialect: DatabaseDialect | None = None,
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
    selected_dialect = dialect
    if selected_dialect is None and current.database_url:
        try:
            selected_dialect = database_dialect_from_url(current.database_url)
        except ValueError:
            selected_dialect = None
    selected_runtime = runtime or _runtime_from_settings(current)
    executor = sql_executor or (
        SqlExecutor(factory, logs, max_rows=current.db_console_max_rows) if factory else None
    )
    inspector = SchemaInspector(factory, dialect=selected_dialect) if factory and selected_dialect else None
    operations = TableOperations(factory, dialect=selected_dialect) if factory and selected_dialect else None
    maintenance = MaintenanceOperations(factory, dialect=selected_dialect) if factory and selected_dialect else None
    scripts = ScriptRunner(factory, logs, dialect=selected_dialect) if factory and selected_dialect else None

    app = Flask(__name__, template_folder="templates", static_folder="static", static_url_path="/internal/db-console/static")
    app.config.update(
        NCS_DB_CONSOLE_SETTINGS=current,
        NCS_DB_CONSOLE_LOGS=logs,
        NCS_DB_CONSOLE_RUNTIME=selected_runtime,
        NCS_DB_CONSOLE_EXECUTOR=executor,
        NCS_DB_CONSOLE_INSPECTOR=inspector,
        NCS_DB_CONSOLE_OPERATIONS=operations,
        NCS_DB_CONSOLE_MAINTENANCE=maintenance,
        NCS_DB_CONSOLE_SCRIPTS=scripts,
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

    # ------------------------------------------------------------- management

    def _require_inspector():
        if inspector is None:
            raise AppError("DB_CONSOLE_NOT_CONFIGURED", "database connection is not configured", 503)
        return inspector

    def _require_operations():
        if operations is None:
            raise AppError("DB_CONSOLE_NOT_CONFIGURED", "database connection is not configured", 503)
        return operations

    def _require_maintenance():
        if maintenance is None:
            raise AppError("DB_CONSOLE_NOT_CONFIGURED", "database connection is not configured", 503)
        return maintenance

    def _require_scripts():
        if scripts is None:
            raise AppError("DB_CONSOLE_NOT_CONFIGURED", "database connection is not configured", 503)
        return scripts

    @app.get("/internal/db-console/schema")
    def list_schema():
        tables = _require_inspector().list_tables()
        return _success(
            {
                "items": [
                    {
                        "name": table.name,
                        "kind": table.kind,
                        "columnCount": table.column_count,
                        "rowCount": table.row_count,
                    }
                    for table in tables
                ]
            }
        )

    @app.get("/internal/db-console/schema/tables/<table_name>")
    def table_schema(table_name: str):
        detail = _require_inspector().table_detail(table_name)
        return _success(
            {
                "table": detail["table"],
                "columns": detail["columns"],
                "indexes": detail["indexes"],
                "rowCount": detail["row_count"],
            }
        )

    @app.get("/internal/db-console/tables/<table_name>/rows")
    def browse_rows(table_name: str):
        args = request.args
        try:
            limit = int(args.get("limit", "50"))
            offset = int(args.get("offset", "0"))
        except ValueError as exc:
            raise AppError("DB_PAGE_INVALID", "limit and offset must be integers", 400) from exc
        result = _require_operations().browse(
            table_name,
            limit=limit,
            offset=offset,
            order_by=args.get("order_by"),
            descending=args.get("direction", "asc").lower() == "desc",
            column=args.get("column"),
            search=args.get("search"),
        )
        return _success(
            {
                "table": result["table"],
                "total": result["total"],
                "columns": result["columns"],
                "rows": [[json_value(value) for value in row] for row in result["rows"]],
            }
        )

    @app.post("/internal/db-console/tables/<table_name>/rows")
    def insert_row(table_name: str):
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or not isinstance(payload.get("values"), dict):
            raise AppError("DB_VALUES_REQUIRED", "values object is required", 400)
        affected = _require_operations().insert(table_name, payload["values"])
        logs.append(category="MANAGE", level="INFO", action="INSERT", message=f"{table_name}: inserted {affected} row(s)")
        return _success({"affectedRows": affected})

    @app.patch("/internal/db-console/tables/<table_name>/rows")
    def update_rows(table_name: str):
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or not isinstance(payload.get("keys"), dict):
            raise AppError("DB_KEYS_REQUIRED", "keys object is required", 400)
        if not isinstance(payload.get("values"), dict):
            raise AppError("DB_VALUES_REQUIRED", "values object is required", 400)
        affected = _require_operations().update(table_name, payload["keys"], payload["values"])
        logs.append(category="MANAGE", level="INFO", action="UPDATE", message=f"{table_name}: updated {affected} row(s)")
        return _success({"affectedRows": affected})

    @app.delete("/internal/db-console/tables/<table_name>/rows")
    def delete_rows(table_name: str):
        payload = request.get_json(silent=True) or {}
        keys = payload.get("keys")
        if not isinstance(keys, dict) or not keys:
            raise AppError("DB_KEYS_REQUIRED", "keys object is required", 400)
        affected = _require_operations().delete(table_name, keys)
        logs.append(category="MANAGE", level="WARNING", action="DELETE", message=f"{table_name}: deleted {affected} row(s)")
        return _success({"affectedRows": affected})

    @app.post("/internal/db-console/tables/<table_name>/truncate")
    def truncate_table(table_name: str):
        payload = request.get_json(silent=True) or {}
        _require_operations().truncate(table_name, confirm=payload.get("confirm") is True)
        logs.append(category="MANAGE", level="WARNING", action="TRUNCATE", message=f"{table_name}: truncated")
        return _success({"action": "truncated", "table": table_name})

    @app.post("/internal/db-console/tables/<table_name>/drop")
    def drop_table(table_name: str):
        payload = request.get_json(silent=True) or {}
        _require_operations().drop(table_name, confirm=payload.get("confirm") is True)
        logs.append(category="MANAGE", level="WARNING", action="DROP", message=f"{table_name}: dropped")
        return _success({"action": "dropped", "table": table_name})

    @app.get("/internal/db-console/maintenance/info")
    def maintenance_info():
        return _success(_require_maintenance().server_info())

    @app.get("/internal/db-console/maintenance/processlist")
    def maintenance_processlist():
        result = _require_maintenance().processlist()
        return _success(
            {
                "columns": result["columns"],
                "rows": [[json_value(value) for value in row] for row in result["rows"]],
            }
        )

    @app.post("/internal/db-console/maintenance/kill-query")
    def maintenance_kill_query():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or not isinstance(payload.get("connectionId"), int):
            raise AppError("DB_QUERY_ID_INVALID", "connectionId must be an integer", 400)
        message = _require_maintenance().kill_query(payload["connectionId"], confirm=payload.get("confirm") is True)
        logs.append(category="MANAGE", level="WARNING", action="KILL", message=message)
        return _success({"message": message})

    @app.post("/internal/db-console/maintenance/optimize")
    def maintenance_optimize():
        payload = request.get_json(silent=True) or {}
        table = payload.get("table")
        if table is not None and not isinstance(table, str):
            raise AppError("DB_TABLE_INVALID", "table must be a string", 400)
        message = _require_maintenance().optimize(table)
        logs.append(category="MANAGE", level="INFO", action="OPTIMIZE", message=message)
        return _success({"message": message})

    @app.post("/internal/db-console/maintenance/analyze")
    def maintenance_analyze():
        payload = request.get_json(silent=True) or {}
        table = payload.get("table")
        if table is not None and not isinstance(table, str):
            raise AppError("DB_TABLE_INVALID", "table must be a string", 400)
        message = _require_maintenance().analyze(table)
        logs.append(category="MANAGE", level="INFO", action="ANALYZE", message=message)
        return _success({"message": message})

    @app.post("/internal/db-console/maintenance/vacuum")
    def maintenance_vacuum():
        payload = request.get_json(silent=True) or {}
        message = _require_maintenance().vacuum(confirm=payload.get("confirm") is True)
        logs.append(category="MANAGE", level="WARNING", action="VACUUM", message=message)
        return _success({"message": message})

    @app.post("/internal/db-console/maintenance/checkpoint")
    def maintenance_checkpoint():
        message = _require_maintenance().checkpoint()
        logs.append(category="MANAGE", level="INFO", action="CHECKPOINT", message=message)
        return _success({"message": message})

    @app.get("/internal/db-console/maintenance/integrity-check")
    def maintenance_integrity():
        return _success(_require_maintenance().integrity_check())

    @app.post("/internal/db-console/script")
    def run_script():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or not isinstance(payload.get("statements"), list):
            raise AppError("SQL_STATEMENT_REQUIRED", "statements array is required", 400)
        result = _require_scripts().run(payload["statements"])
        if not result.committed:
            raise AppError(
                "SCRIPT_ROLLED_BACK",
                "script failed and was rolled back",
                400,
                {
                    "scriptId": result.script_id,
                    "statementCount": len(result.statements),
                    "databaseMessage": result.error,
                },
            )
        return _success(
            {
                "scriptId": result.script_id,
                "committed": result.committed,
                "statements": [
                    {
                        "index": item.index,
                        "statementType": item.statement_type,
                        "affectedRows": item.affected_rows,
                    }
                    for item in result.statements
                ],
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

    @app.errorhandler(TableOperationError)
    def handle_table_error(error: TableOperationError):
        status = 409 if error.code == "DB_DESTRUCTIVE_CONFIRM_REQUIRED" else 400
        return jsonify({"code": error.code, "message": str(error), "data": None, "meta": {}}), status

    @app.errorhandler(MaintenanceError)
    def handle_maintenance_error(error: MaintenanceError):
        status = 409 if error.code == "DB_DESTRUCTIVE_CONFIRM_REQUIRED" else 400
        return jsonify({"code": error.code, "message": str(error), "data": None, "meta": {}}), status

    @app.errorhandler(IdentifierError)
    def handle_identifier_error(error: IdentifierError):
        return jsonify({"code": "DB_IDENTIFIER_INVALID", "message": str(error), "data": None, "meta": {}}), 400

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
