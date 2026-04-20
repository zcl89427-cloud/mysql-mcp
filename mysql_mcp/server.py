from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from mysql_mcp.core import MySQLService

mcp = FastMCP(
    "MySQL Query MCP",
    instructions=(
        "Execute single-statement SQL queries against a MySQL database configured through "
        "environment variables. Use list_tables and describe_table for schema discovery."
    ),
    json_response=True,
)


def _service() -> MySQLService:
    return MySQLService.from_env()


@mcp.tool()
def execute_sql(
    sql: str,
    params: dict[str, Any] | list[Any] | None = None,
    database: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Execute one SQL statement against MySQL."""

    return _service().execute_sql(sql=sql, params=params, database=database, limit=limit)


@mcp.tool()
def list_tables(database: str | None = None) -> dict[str, Any]:
    """List tables for the configured database or an explicitly provided one."""

    return _service().list_tables(database=database)


@mcp.tool()
def list_databases() -> dict[str, Any]:
    """List databases visible to the configured MySQL user."""

    return _service().list_databases()


@mcp.tool()
def describe_table(table_name: str, database: str | None = None) -> dict[str, Any]:
    """Describe a table using information_schema metadata."""

    return _service().describe_table(table_name=table_name, database=database)


@mcp.tool()
def preview_table(
    table_name: str,
    database: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Preview rows from a table using a safe SELECT * ... LIMIT query."""

    return _service().preview_table(table_name=table_name, database=database, limit=limit)


@mcp.tool()
def explain_sql(
    sql: str,
    params: dict[str, Any] | list[Any] | None = None,
    database: str | None = None,
) -> dict[str, Any]:
    """Run EXPLAIN for a read-only SQL statement."""

    return _service().explain_sql(sql=sql, params=params, database=database)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
