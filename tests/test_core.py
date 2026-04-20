from __future__ import annotations

import datetime as dt
from decimal import Decimal
from unittest.mock import MagicMock

import pymysql
import pytest

from mysql_mcp.config import MySQLSettings
from mysql_mcp.core import (
    DatabaseSelectionError,
    MySQLMcpError,
    MySQLService,
    StatementValidationError,
    ensure_allowed_statement,
    ensure_single_statement,
    normalize_params,
    normalize_limit,
    serialize_value,
)


class FakeCursor:
    def __init__(self, *, rows=None, description=None, rowcount=0, error=None):
        self._rows = rows or []
        self.description = description
        self.rowcount = rowcount
        self._error = error
        self.executed = None

    def execute(self, sql, params=None):
        self.executed = (sql, params)
        if self._error is not None:
            raise self._error

    def fetchall(self):
        return self._rows

    def fetchmany(self, size):
        return self._rows[:size]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self, cursor: FakeCursor, *, warnings=None, insert_id=0):
        self._cursor = cursor
        self._warnings = warnings or []
        self._insert_id = insert_id
        self.commit = MagicMock()
        self.rollback = MagicMock()
        self.close = MagicMock()

    def cursor(self, *args, **kwargs):
        return self._cursor

    def show_warnings(self):
        return self._warnings

    def insert_id(self):
        return self._insert_id


def make_service(*, read_only: bool = True) -> MySQLService:
    settings = MySQLSettings(
        host="127.0.0.1",
        port=3306,
        user="root",
        password="secret",
        database="demo",
        charset="utf8mb4",
        connect_timeout=10,
        read_only=read_only,
        query_default_limit=10,
        query_max_limit=50,
    )
    return MySQLService(settings)


def test_ensure_single_statement_accepts_single_query():
    assert ensure_single_statement("SELECT 1;") == "SELECT 1"
    assert ensure_single_statement("SELECT ';' AS value") == "SELECT ';' AS value"


def test_ensure_single_statement_rejects_multi_statement_sql():
    with pytest.raises(StatementValidationError):
        ensure_single_statement("SELECT 1; DROP TABLE users;")


def test_normalize_params_accepts_list_and_dict():
    assert normalize_params([1, 2]) == [1, 2]
    assert normalize_params({"id": 1}) == {"id": 1}


def test_normalize_params_rejects_strings():
    with pytest.raises(StatementValidationError):
        normalize_params("SELECT 1")


def test_serialize_value_handles_common_mysql_types():
    assert serialize_value(Decimal("12.30")) == "12.30"
    assert serialize_value(dt.date(2026, 4, 17)) == "2026-04-17"
    assert serialize_value(dt.datetime(2026, 4, 17, 10, 30, 5)) == "2026-04-17T10:30:05"
    assert serialize_value(b"hi") == {"type": "bytes", "base64": "aGk="}


def test_normalize_limit_uses_default_and_enforces_max():
    service = make_service()

    assert normalize_limit(None, service.settings) == 10
    assert normalize_limit(20, service.settings) == 20

    with pytest.raises(StatementValidationError):
        normalize_limit(51, service.settings)


def test_read_only_mode_rejects_write_statements():
    service = make_service()

    with pytest.raises(StatementValidationError, match="read-only mode"):
        ensure_allowed_statement("DELETE FROM users", service.settings)


def test_execute_sql_returns_query_shape(monkeypatch):
    cursor = FakeCursor(
        rows=[{"id": 1, "price": Decimal("9.99")}],
        description=[("id",), ("price",)],
        rowcount=1,
    )
    connection = FakeConnection(cursor, warnings=[("Warning", 1000, "demo warning")])
    monkeypatch.setattr("mysql_mcp.core.pymysql.connect", lambda **kwargs: connection)

    result = make_service().execute_sql("SELECT id, price FROM products WHERE id = %s", [1])

    assert result == {
        "statement_type": "SELECT",
        "columns": ["id", "price"],
        "rows": [{"id": 1, "price": "9.99"}],
        "row_count": 1,
        "limit_applied": 10,
        "has_more": False,
        "warnings": [{"level": "Warning", "code": 1000, "message": "demo warning"}],
    }
    connection.commit.assert_not_called()
    connection.close.assert_called_once()


def test_execute_sql_returns_write_shape(monkeypatch):
    cursor = FakeCursor(description=None, rowcount=2)
    connection = FakeConnection(cursor, insert_id=42)
    monkeypatch.setattr("mysql_mcp.core.pymysql.connect", lambda **kwargs: connection)

    result = make_service(read_only=False).execute_sql("UPDATE users SET active = %s", [True])

    assert result == {
        "statement_type": "UPDATE",
        "affected_rows": 2,
        "last_insert_id": 42,
        "warnings": [],
    }
    connection.commit.assert_called_once()
    connection.close.assert_called_once()


def test_execute_sql_uses_explicit_database_override(monkeypatch):
    cursor = FakeCursor(description=None, rowcount=0)
    connection = FakeConnection(cursor)
    captured_kwargs = {}

    def fake_connect(**kwargs):
        captured_kwargs.update(kwargs)
        return connection

    monkeypatch.setattr("mysql_mcp.core.pymysql.connect", fake_connect)

    make_service(read_only=False).execute_sql("DELETE FROM logs WHERE created_at < NOW()", database="archive")

    assert captured_kwargs["database"] == "archive"


def test_execute_sql_caps_query_result_and_marks_has_more(monkeypatch):
    rows = [{"id": index} for index in range(1, 13)]
    cursor = FakeCursor(rows=rows, description=[("id",)], rowcount=12)
    connection = FakeConnection(cursor)
    monkeypatch.setattr("mysql_mcp.core.pymysql.connect", lambda **kwargs: connection)

    result = make_service().execute_sql("SELECT id FROM logs ORDER BY id", limit=10)

    assert result["row_count"] == 10
    assert result["limit_applied"] == 10
    assert result["has_more"] is True
    assert result["rows"][-1] == {"id": 10}


def test_list_tables_requires_database_when_not_configured():
    settings = MySQLSettings(
        host="127.0.0.1",
        port=3306,
        user="root",
        password="secret",
        database=None,
        charset="utf8mb4",
        connect_timeout=10,
        read_only=True,
        query_default_limit=10,
        query_max_limit=50,
    )
    service = MySQLService(settings)

    with pytest.raises(DatabaseSelectionError):
        service.list_tables()


def test_execute_sql_translates_common_mysql_errors(monkeypatch):
    cursor = FakeCursor(error=pymysql.err.ProgrammingError(1064, "You have an error in your SQL syntax"))
    connection = FakeConnection(cursor)
    monkeypatch.setattr("mysql_mcp.core.pymysql.connect", lambda **kwargs: connection)

    with pytest.raises(MySQLMcpError, match="SQL syntax error"):
        make_service().execute_sql("SELECT FROM")

    connection.rollback.assert_called_once()


def test_list_databases_returns_names(monkeypatch):
    cursor = FakeCursor(
        rows=[{"database_name": "demo"}, {"database_name": "mysql"}],
        description=[("database_name",)],
    )
    connection = FakeConnection(cursor)
    monkeypatch.setattr("mysql_mcp.core.pymysql.connect", lambda **kwargs: connection)

    result = make_service().list_databases()

    assert result == {
        "databases": ["demo", "mysql"],
        "count": 2,
    }


def test_preview_table_builds_limited_select(monkeypatch):
    cursor = FakeCursor(
        rows=[{"id": 1, "name": "alice"}],
        description=[("id",), ("name",)],
    )
    connection = FakeConnection(cursor)
    monkeypatch.setattr("mysql_mcp.core.pymysql.connect", lambda **kwargs: connection)

    result = make_service().preview_table("users", limit=5)

    assert cursor.executed == ("SELECT * FROM `demo`.`users` LIMIT %s", [5])
    assert result["rows"] == [{"id": 1, "name": "alice"}]
    assert result["limit_applied"] == 5


def test_explain_sql_wraps_read_query(monkeypatch):
    cursor = FakeCursor(
        rows=[{"id": 1, "select_type": "SIMPLE"}],
        description=[("id",), ("select_type",)],
    )
    connection = FakeConnection(cursor)
    monkeypatch.setattr("mysql_mcp.core.pymysql.connect", lambda **kwargs: connection)

    result = make_service().explain_sql("SELECT * FROM users WHERE id = %s", params=[1])

    assert cursor.executed == ("EXPLAIN SELECT * FROM users WHERE id = %s", [1])
    assert result["statement_type"] == "EXPLAIN"


def test_explain_sql_rejects_write_statements():
    with pytest.raises(StatementValidationError, match="read-only mode"):
        make_service().explain_sql("UPDATE users SET active = 1")
