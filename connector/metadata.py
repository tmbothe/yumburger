"""Metadata Plane — Athena DESCRIBE / SHOW COLUMNS / $snapshots."""

from __future__ import annotations

import logging
from typing import Any

import boto3

from connector.engines.athena import AthenaEngine
from connector.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class MetadataPlane:
    """
    Queries Iceberg table metadata via Athena.
    Uses the connector-runtime session (not persona) for DESCRIBE queries
    since DESCRIBE doesn't return row data — no row-level filtering needed.
    """

    def __init__(self, session: boto3.Session) -> None:
        self._engine = AthenaEngine(session)

    def describe_table(self, table: str) -> list[dict[str, Any]]:
        """Return column definitions for a silver table."""
        if table not in settings.allowed_tables:
            raise ValueError(f"Table not in allowlist: {table}")
        logger.info(f"DESCRIBE {table}")
        return self._engine.describe_table(table, database=settings.silver_db)

    def list_tables(self) -> list[str]:
        """Return all tables in the silver database."""
        rows = self._engine.execute(
            f"SHOW TABLES IN {settings.silver_db}",
            database=settings.silver_db,
        )
        return [row.get("tab_name", row.get("tableName", "")) for row in rows]

    def get_snapshots(self, table: str) -> list[dict[str, Any]]:
        """Return Iceberg snapshot history for a table."""
        if table not in settings.allowed_tables:
            raise ValueError(f"Table not in allowlist: {table}")
        logger.info(f"Fetching snapshots for {table}")
        return self._engine.show_snapshots(table, database=settings.silver_db)

    def get_schema_summary(self) -> dict[str, list[dict[str, Any]]]:
        """Return schema for all allowed tables."""
        result = {}
        for table in settings.allowed_tables:
            try:
                result[table] = self.describe_table(table)
            except Exception as e:
                logger.warning(f"Could not describe {table}: {e}")
                result[table] = []
        return result
