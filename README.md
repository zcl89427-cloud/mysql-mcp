# MySQL Query MCP

一个基于 Python 的本地 `stdio` MCP Server，用来查询 MySQL，并提供基础的表结构发现能力。

## 功能

- `execute_sql(sql, params?, database?, limit?)`
- `list_databases()`
- `list_tables(database?)`
- `describe_table(table_name, database?)`
- `preview_table(table_name, database?, limit?)`
- `explain_sql(sql, params?, database?)`

默认开启只读模式，只允许 `SELECT / SHOW / DESCRIBE / DESC / EXPLAIN`。如果你明确需要写操作，可以把 `MYSQL_READ_ONLY=false`。

即使关闭只读模式，每次也只允许执行一条语句。像 `SELECT 1; DROP TABLE users;` 这种多语句输入会被拒绝。

查询语句默认最多返回 10 条。你可以在调用 `execute_sql` 时传 `limit`，但不能超过配置的 `MYSQL_QUERY_LIMIT_MAX`，而且这个上限本身最多只能设到 50。

## 环境变量

复制 `.env.example` 后按需填写：

- `MYSQL_HOST`
- `MYSQL_PORT`，默认 `3306`
- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `MYSQL_DATABASE`，可为空
- `MYSQL_CHARSET`，默认 `utf8mb4`
- `MYSQL_CONNECT_TIMEOUT`，默认 `10`
- `MYSQL_READ_ONLY`，默认 `true`
- `MYSQL_QUERY_LIMIT_DEFAULT`，默认 `10`
- `MYSQL_QUERY_LIMIT_MAX`，默认 `50`，且最大不能超过 `50`

## 安装

```powershell
pip install -e .
```

如果你想带上测试依赖：

```powershell
pip install -e .[dev]
```

## 启动

```powershell
mysql-mcp
```

或者：

```powershell
python -m mysql_mcp.server
```

## MCP 客户端接入示例

Windows 本地可以直接把虚拟环境解释器配置成 MCP 命令：

```json
{
  "mcpServers": {
    "mysql": {
      "command": "D:\\pythonProject\\.venv\\Scripts\\python.exe",
      "args": ["-m", "mysql_mcp.server"],
      "cwd": "D:\\pythonProject",
      "env": {
        "MYSQL_HOST": "127.0.0.1",
        "MYSQL_PORT": "3306",
        "MYSQL_USER": "root",
        "MYSQL_PASSWORD": "your-password",
        "MYSQL_DATABASE": "demo",
        "MYSQL_CHARSET": "utf8mb4",
        "MYSQL_CONNECT_TIMEOUT": "10"
      }
    }
  }
}
```

## 返回格式

查询语句返回：

```json
{
  "statement_type": "SELECT",
  "columns": ["id", "name"],
  "rows": [{"id": 1, "name": "alice"}],
  "row_count": 1,
  "limit_applied": 10,
  "has_more": false,
  "warnings": []
}
```

写语句返回：

```json
{
  "statement_type": "INSERT",
  "affected_rows": 1,
  "last_insert_id": 42,
  "warnings": []
}
```

## 测试

```powershell
pytest
```

当前测试主要覆盖：

- 单条 SQL 校验
- 只读模式语句限制
- 参数归一化
- 查询/写入返回结构
- 数据库列表、表预览、执行计划
- 数据库显式覆盖
- 常见错误消息映射
