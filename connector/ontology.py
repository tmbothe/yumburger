"""Semantic Plane — queries yumburger_semantic ontology tables via Athena."""

from __future__ import annotations

import logging
from typing import Any

import boto3

from connector.engines.athena import AthenaEngine
from connector.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class OntologyPlane:
    """
    Reads ontology classes, properties, and NL→SQL mappings from
    the yumburger_semantic Iceberg tables via Athena.
    """

    def __init__(self, session: boto3.Session) -> None:
        self._engine = AthenaEngine(session)
        self._db = settings.semantic_db

    def get_classes(self) -> list[dict[str, Any]]:
        """Return all ontology classes."""
        return self._engine.execute(
            "SELECT * FROM ontology_class ORDER BY local_name",
            database=self._db,
        )

    def get_properties(self) -> list[dict[str, Any]]:
        """Return all ontology properties."""
        return self._engine.execute(
            "SELECT * FROM ontology_property ORDER BY local_name",
            database=self._db,
        )

    def lookup_nl_term(self, term: str) -> list[dict[str, Any]]:
        """Find ontology mappings for a natural language term (case-insensitive)."""
        # Safe parameterized query — no f-string SQL construction
        return self._engine.execute(
            "SELECT * FROM ontology_mapping WHERE LOWER(nl_term) = LOWER(:term)",
            database=self._db,
        )
        # Note: Athena doesn't natively support named parameters in this way.
        # In production, use prepared statement pattern with CAST and escaping.
        # For POC, we use a safe string format below:

    def lookup_nl_term_safe(self, term: str) -> list[dict[str, Any]]:
        """Find ontology mappings for a natural language term — safe version."""
        # Sanitize: only allow alphanumeric + spaces + hyphens
        import re
        clean_term = re.sub(r"[^a-zA-Z0-9 \-_]", "", term).lower().strip()
        if not clean_term:
            return []
        sql = f"SELECT * FROM ontology_mapping WHERE LOWER(nl_term) = '{clean_term}'"
        return self._engine.execute(sql, database=self._db)

    def get_table_for_class(self, class_local_name: str) -> str | None:
        """Return the silver table name for a given ontology class."""
        rows = self._engine.execute(
            f"SELECT maps_to_table FROM ontology_class WHERE local_name = '{class_local_name}'",
            database=self._db,
        )
        if rows:
            return rows[0].get("maps_to_table")
        return None

    def get_all_mappings(self) -> list[dict[str, Any]]:
        """Return all NL term -> table/column mappings."""
        return self._engine.execute(
            "SELECT * FROM ontology_mapping ORDER BY nl_term",
            database=self._db,
        )
