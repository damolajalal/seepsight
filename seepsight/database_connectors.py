"""Bounded, read-only database query adapters for Seepsight.

Secrets are referenced by Secret Manager resource name, never passed as raw
credentials through Streamlit state. Use database accounts with read-only grants.
"""

import re

from seepsight.secrets_manager import access_secret_json, validate_secret_reference

_ALLOWED_PROVIDERS = {"postgres", "mysql", "sqlserver", "bigquery"}
_BLOCKED_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|TRUNCATE|CALL|EXEC|EXECUTE|GRANT|REVOKE|COPY|LOAD|UNLOAD)\b",
    re.IGNORECASE,
)


def validate_readonly_sql(sql):
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("A read-only SQL query is required.")
    statement = sql.strip()
    if "--" in statement or "/*" in statement or "*/" in statement:
        raise ValueError("SQL comments are not permitted in connector queries.")
    if statement.count(";") > 1 or (";" in statement and not statement.rstrip().endswith(";")):
        raise ValueError("Only one SQL statement may be executed.")
    statement = statement.rstrip().removesuffix(";").strip()
    if not re.match(r"^(SELECT|WITH)\b", statement, re.IGNORECASE):
        raise ValueError("Only SELECT queries and read-only CTEs are permitted.")
    if _BLOCKED_SQL.search(statement) or re.search(r"\bFOR\s+UPDATE\b", statement, re.IGNORECASE):
        raise ValueError("The query contains a write or locking operation.")
    return statement


def _validate_limits(max_rows, timeout_seconds):
    if not isinstance(max_rows, int) or not 1 <= max_rows <= 1000:
        raise ValueError("max_rows must be between 1 and 1000.")
    if not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 60:
        raise ValueError("timeout_seconds must be between 1 and 60.")


def _odbc_escape(value):
    return "{" + str(value).replace("}", "}}") + "}"


def _postgres(secret, sql, parameters, max_rows, timeout_seconds):
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("PostgreSQL support is missing; install psycopg.") from exc
    sslmode = secret.get("sslmode", "require")
    if sslmode not in {"require", "verify-ca", "verify-full"}:
        raise ValueError("PostgreSQL connections must use TLS.")
    connection = psycopg.connect(
        host=secret["host"], port=int(secret.get("port", 5432)),
        dbname=secret["database"], user=secret["username"],
        password=secret["password"], sslmode=sslmode,
        sslrootcert=secret.get("sslrootcert"),
        connect_timeout=10,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute(f"SET LOCAL statement_timeout = {timeout_seconds * 1000}")
            cursor.execute(sql, tuple(parameters or ()))
            columns = [item.name for item in cursor.description or ()]
            rows = cursor.fetchmany(max_rows + 1)
            return columns, [dict(zip(columns, row)) for row in rows[:max_rows]], len(rows) > max_rows
    finally:
        connection.rollback()
        connection.close()


def _mysql(secret, sql, parameters, max_rows, timeout_seconds):
    try:
        import pymysql
        from pymysql.cursors import DictCursor
    except ImportError as exc:
        raise RuntimeError("MySQL support is missing; install PyMySQL.") from exc
    connection = pymysql.connect(
        host=secret["host"], port=int(secret.get("port", 3306)),
        user=secret["username"], password=secret["password"],
        database=secret["database"], connect_timeout=10,
        read_timeout=timeout_seconds + 5, write_timeout=10,
        ssl_verify_cert=True, ssl_verify_identity=True,
        autocommit=False, cursorclass=DictCursor,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            connection.begin()
            cursor.execute(f"SET SESSION MAX_EXECUTION_TIME = {timeout_seconds * 1000}")
            cursor.execute(sql, tuple(parameters or ()))
            rows = cursor.fetchmany(max_rows + 1)
            columns = list(rows[0].keys()) if rows else [item[0] for item in cursor.description or ()]
            return columns, rows[:max_rows], len(rows) > max_rows
    finally:
        connection.rollback()
        connection.close()


def _sqlserver(secret, sql, parameters, max_rows, timeout_seconds):
    try:
        import pyodbc
    except ImportError as exc:
        raise RuntimeError("SQL Server support is missing; install pyodbc and a supported ODBC driver.") from exc
    driver = secret.get("driver", "ODBC Driver 18 for SQL Server")
    parts = [
        f"DRIVER={_odbc_escape(driver)}",
        f"SERVER={_odbc_escape(secret['host'] + ',' + str(secret.get('port', 1433)))}",
        f"DATABASE={_odbc_escape(secret['database'])}",
        f"UID={_odbc_escape(secret['username'])}",
        f"PWD={_odbc_escape(secret['password'])}",
        "Encrypt=yes", "TrustServerCertificate=no", "ApplicationIntent=ReadOnly",
        "Connection Timeout=10",
    ]
    connection = pyodbc.connect(";".join(parts), timeout=10, autocommit=False)
    try:
        cursor = connection.cursor()
        cursor.timeout = timeout_seconds
        cursor.execute(sql, tuple(parameters or ()))
        columns = [item[0] for item in cursor.description or ()]
        rows = cursor.fetchmany(max_rows + 1)
        return columns, [dict(zip(columns, row)) for row in rows[:max_rows]], len(rows) > max_rows
    finally:
        connection.rollback()
        connection.close()


def _bigquery(secret, sql, parameters, max_rows, timeout_seconds):
    try:
        from google.cloud import bigquery
        from google.oauth2 import service_account
    except ImportError as exc:
        raise RuntimeError("BigQuery support is missing; install google-cloud-bigquery.") from exc
    credentials = service_account.Credentials.from_service_account_info(secret)
    client = bigquery.Client(
        project=secret.get("project_id") or credentials.project_id,
        credentials=credentials,
    )
    query_parameters = []
    for item in parameters or ():
        if not isinstance(item, dict) or not {"name", "type", "value"} <= set(item):
            raise ValueError("BigQuery parameters require name, type and value.")
        query_parameters.append(
            bigquery.ScalarQueryParameter(item["name"], item["type"], item["value"])
        )
    job_config = bigquery.QueryJobConfig(
        use_legacy_sql=False,
        maximum_bytes_billed=int(secret.get("maximum_bytes_billed", 100_000_000)),
        query_parameters=query_parameters,
    )
    job = client.query(sql, job_config=job_config, timeout=timeout_seconds)
    rows = list(job.result(max_results=max_rows + 1, timeout=timeout_seconds))
    columns = [field.name for field in job.schema]
    result = [dict(row.items()) for row in rows[:max_rows]]
    return columns, result, len(rows) > max_rows


def execute_readonly_query(provider, secret_reference, sql, parameters=None,
                           max_rows=500, timeout_seconds=15):
    """Execute one bounded read-only query using a Secret Manager credential."""
    provider = str(provider or "").strip().lower()
    if provider not in _ALLOWED_PROVIDERS:
        raise ValueError("Unsupported database provider.")
    resource = validate_secret_reference(secret_reference)
    statement = validate_readonly_sql(sql)
    _validate_limits(max_rows, timeout_seconds)
    secret = access_secret_json(resource)
    adapters = {
        "postgres": _postgres,
        "mysql": _mysql,
        "sqlserver": _sqlserver,
        "bigquery": _bigquery,
    }
    try:
        columns, rows, truncated = adapters[provider](
            secret, statement, parameters, max_rows, timeout_seconds
        )
    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError("The database query failed. Check the connection and read-only account permissions.") from exc
    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
        "provider": provider,
    }
