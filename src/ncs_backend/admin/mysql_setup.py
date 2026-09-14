"""MySQL ADS schema initialization, fixed-view grants and privilege checks."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
import re
from typing import Any

from ncs_backend.admin.ads_schema import ADS_VIEW_NAMES, initialize_ads_result_schema
from ncs_backend.admin.prediction_schema import PREDICTION_VIEW_NAMES, initialize_prediction_schema
from ncs_backend.admin.migrations import MigrationRunner
from ncs_backend.shared.db import MYSQL_DIALECT

ConnectionFactory = Callable[[], Any]
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")


@dataclass(frozen=True, slots=True)
class MySqlSetupReport:
    initialized: bool
    reader_views: tuple[str, ...]
    reader_physical_tables_denied: bool
    admin_dml_only: bool
    migrator_can_manage_schema: bool


def initialize_mysql_ads(connection_factory: ConnectionFactory) -> bool:
    connection = connection_factory()
    try:
        MigrationRunner(dialect=MYSQL_DIALECT).apply(connection)
        result = initialize_ads_result_schema(connection, dialect=MYSQL_DIALECT)
        initialize_prediction_schema(connection, dialect=MYSQL_DIALECT)
        return result.applied
    finally:
        connection.close()


def grant_reader_views(
    connection_factory: ConnectionFactory,
    *,
    database: str,
    reader_account: str = "ncs_ads_reader",
    reader_host: str = "localhost",
    views: Iterable[str] = (*ADS_VIEW_NAMES, *PREDICTION_VIEW_NAMES),
) -> tuple[str, ...]:
    database = _safe_identifier(database, "database")
    reader_account = _safe_identifier(reader_account, "reader account")
    reader_host = _safe_account_host(reader_host)
    selected = tuple(_safe_identifier(view, "view") for view in views)
    connection = connection_factory()
    cursor = connection.cursor()
    try:
        for view in selected:
            cursor.execute(
                f"GRANT SELECT ON `{database}`.`{view}` TO '{reader_account}'@'{reader_host}'"
            )
        connection.commit()
        return selected
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


def verify_mysql_accounts(
    migrator_factory: ConnectionFactory,
    admin_factory: ConnectionFactory,
    reader_factory: ConnectionFactory,
) -> MySqlSetupReport:
    migrator_grants = _current_grants(migrator_factory)
    admin_grants = _current_grants(admin_factory)
    reader_grants = _current_grants(reader_factory)
    migrator_ok = "ALL PRIVILEGES" in migrator_grants or all(
        privilege in migrator_grants for privilege in ("CREATE", "ALTER", "DROP")
    )
    admin_ok = all(privilege in admin_grants for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE")) and not any(
        privilege in admin_grants for privilege in ("ALL PRIVILEGES", "CREATE", "ALTER", "DROP", "GRANT OPTION")
    )
    visible = _readable_views(reader_factory)
    denied = _physical_tables_denied(reader_factory)
    reader_is_narrow = "ALL PRIVILEGES" not in reader_grants and not any(
        "SELECT" in line and re.search(r"ON\s+`?[^` ]+`?\.\*", line)
        for line in reader_grants.splitlines()
    )
    return MySqlSetupReport(
        initialized=True,
        reader_views=visible,
        reader_physical_tables_denied=denied and reader_is_narrow,
        admin_dml_only=admin_ok,
        migrator_can_manage_schema=migrator_ok,
    )


def _current_grants(connection_factory: ConnectionFactory) -> str:
    connection = connection_factory()
    cursor = connection.cursor()
    try:
        cursor.execute("SHOW GRANTS")
        return "\n".join(str(row[0]).upper() for row in cursor.fetchall())
    finally:
        cursor.close()
        connection.close()


def _readable_views(connection_factory: ConnectionFactory) -> tuple[str, ...]:
    connection = connection_factory()
    cursor = connection.cursor()
    visible: list[str] = []
    try:
        for view in ADS_VIEW_NAMES:
            cursor.execute(f"SELECT * FROM `{view}` LIMIT 0")
            visible.append(view)
        return tuple(visible)
    finally:
        cursor.close()
        connection.close()


def _physical_tables_denied(connection_factory: ConnectionFactory) -> bool:
    connection = connection_factory()
    cursor = connection.cursor()
    denied = 0
    try:
        for table in ("rpt_dashboard_overview", "ctl_import_batch"):
            try:
                cursor.execute(f"SELECT * FROM `{table}` LIMIT 0")
            except Exception as exc:
                if getattr(exc, "args", (None,))[0] == 1142:
                    denied += 1
                else:
                    raise
        return denied == 2
    finally:
        cursor.close()
        connection.close()


def _safe_identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"invalid MySQL {label}")
    return value


def _safe_account_host(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:%-]+", value):
        raise ValueError("invalid MySQL reader host")
    return value
