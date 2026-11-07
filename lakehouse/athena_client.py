"""Shared Athena client for lakehouse operations."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import boto3

from config_loader import load_settings

CFG = load_settings()
WORKGROUP = CFG["athena"]["workgroup"]
REGION = CFG["project"]["region"]
PROFILE = "default"


def get_athena_client():
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    return session.client("athena")


def run_query(sql: str, database: str | None = None, timeout: int = 120) -> dict[str, Any]:
    """Execute an Athena query and wait for completion."""
    client = get_athena_client()
    kwargs: dict[str, Any] = {
        "QueryString": sql,
        "WorkGroup": WORKGROUP,
    }
    if database:
        kwargs["QueryExecutionContext"] = {"Database": database}

    response = client.start_query_execution(**kwargs)
    execution_id = response["QueryExecutionId"]

    # Poll for completion
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = client.get_query_execution(QueryExecutionId=execution_id)
        state = result["QueryExecution"]["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(2)
    else:
        client.stop_query_execution(QueryExecutionId=execution_id)
        raise TimeoutError(f"Query {execution_id} timed out after {timeout}s")

    if state != "SUCCEEDED":
        reason = result["QueryExecution"]["Status"].get("StateChangeReason", "Unknown")
        raise RuntimeError(f"Athena query {state}: {reason}")

    return result["QueryExecution"]


def run_ddl_file(ddl_path: Path, database: str | None = None) -> None:
    """Run a DDL SQL file (may contain multiple statements split by ';')."""
    sql = ddl_path.read_text()
    # Split on semicolons, skip empty statements
    statements = [s.strip() for s in sql.split(";") if s.strip() and not s.strip().startswith("--")]
    for stmt in statements:
        if not stmt:
            continue
        print(f"  Running DDL: {stmt[:80]}...")
        run_query(stmt, database=database)
        print("  OK")
