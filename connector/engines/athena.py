"""Athena query engine — executes compiled SQL as a persona role."""

from __future__ import annotations

import logging
import time
from typing import Any

import boto3

from connector.settings import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


class AthenaEngine:
    """
    Executes parameterized SQL against Athena as a given persona session.
    All SQL must be compiler-verified before passing here.
    LLM-generated SQL is never executed directly.
    """

    def __init__(self, session: boto3.Session) -> None:
        self._client = session.client("athena", region_name=settings.aws_region)

    def execute(
        self,
        sql: str,
        database: str | None = None,
        timeout: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Execute SQL and return results as a list of dicts.
        Raises RuntimeError if Athena query fails or times out.
        """
        db = database or settings.silver_db
        timeout = timeout or settings.query_timeout_seconds

        logger.info(f"Executing Athena query on database={db}: {sql[:100]}...")

        resp = self._client.start_query_execution(
            QueryString=sql,
            WorkGroup=settings.workgroup,
            QueryExecutionContext={"Database": db},
            ResultConfiguration={
                "OutputLocation": f"s3://{settings.athena_results_bucket}/connector-results/",
            },
        )
        execution_id = resp["QueryExecutionId"]
        logger.debug(f"QueryExecutionId={execution_id}")

        result = self._poll(execution_id, timeout)
        rows = self._fetch_results(execution_id)
        logger.info(f"Query {execution_id} returned {len(rows)} rows")
        return rows

    def _poll(self, execution_id: str, timeout: int) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            result = self._client.get_query_execution(QueryExecutionId=execution_id)
            state = result["QueryExecution"]["Status"]["State"]
            if state == "SUCCEEDED":
                return result
            if state in ("FAILED", "CANCELLED"):
                reason = result["QueryExecution"]["Status"].get("StateChangeReason", "unknown")
                raise RuntimeError(f"Query {state}: {reason}")
            time.sleep(1)

        self._client.stop_query_execution(QueryExecutionId=execution_id)
        raise TimeoutError(f"Query {execution_id} timed out after {timeout}s")

    def _fetch_results(self, execution_id: str) -> list[dict[str, Any]]:
        """Fetch all result pages and return as list of dicts."""
        paginator = self._client.get_paginator("get_query_results")
        pages = paginator.paginate(QueryExecutionId=execution_id)

        rows = []
        columns: list[str] = []
        first_page = True

        for page in pages:
            result_rows = page["ResultSet"]["Rows"]
            if first_page:
                columns = [col["VarCharValue"] for col in result_rows[0]["Data"]]
                result_rows = result_rows[1:]  # skip header row
                first_page = False
            for row in result_rows:
                values = [d.get("VarCharValue", None) for d in row["Data"]]
                rows.append(dict(zip(columns, values)))

        return rows

    def describe_table(self, table: str, database: str | None = None) -> list[dict[str, Any]]:
        """Return column descriptions for a table as {col_name, data_type, comment} dicts.

        Athena DESCRIBE on Iceberg tables returns single-column tab-separated rows.
        This method normalises them into structured dicts.
        """
        db = database or settings.silver_db
        raw = self.execute(f"DESCRIBE {db}.{table}", database=db)
        # Raw rows look like: {"# Table schema:\t\t": "customer_id\tstring\tUUID primary key"}
        # The key is irrelevant; the value is tab-separated col_name, data_type, comment.
        result = []
        for row in raw:
            value = next(iter(row.values()), "") or ""
            parts = value.split("\t")
            col_name = parts[0].strip()
            # Skip blank lines and Iceberg section headers (start with #)
            if not col_name or col_name.startswith("#"):
                continue
            result.append({
                "col_name": col_name,
                "data_type": parts[1].strip() if len(parts) > 1 else "",
                "comment": parts[2].strip() if len(parts) > 2 else "",
            })
        return result

    def show_snapshots(self, table: str, database: str | None = None) -> list[dict[str, Any]]:
        """Return Iceberg snapshot history for a table."""
        db = database or settings.silver_db
        return self.execute(
            f'SELECT * FROM "{db}"."{table}$snapshots" ORDER BY committed_at DESC',
            database=db,
        )
