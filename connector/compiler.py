"""
Query Plane — NL → SQL compiler + verifier.

Flow:
1. Receive natural language question + schema context + ontology mappings
2. Call Bedrock to generate SQL (NEVER executed directly)
3. Parse generated SQL with sqlglot (AST check)
4. Verify: only allowed tables, no DDL/DML mutations, no subquery injection
5. Return verified SQL for execution by engines/athena.py

Key invariant: LLM SQL is NEVER executed. Only verifier-approved SQL is executed.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import boto3
import sqlglot
import sqlglot.expressions as exp

from connector.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# SQL keywords that are never allowed in generated queries
FORBIDDEN_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER",
    "TRUNCATE", "GRANT", "REVOKE", "EXEC", "EXECUTE", "MERGE",
    "CALL", "LOAD", "COPY",
}

SYSTEM_PROMPT = """You are a SQL query generator for YumBurger restaurant analytics.
Generate ONLY a single SELECT query. No explanations, no markdown, just the raw SQL.

Rules:
- Use only the tables and columns provided in the schema context
- Never use INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, or any DDL/DML
- Always use table aliases
- Limit results to 1000 rows maximum unless the question asks for a specific count
- Use LOWER() for case-insensitive string comparisons
- Database: {database}
"""


class CompilerError(Exception):
    """Raised when SQL cannot be compiled or fails verification."""


class SQLVerifier:
    """Verifies that compiler-generated SQL is safe to execute."""

    def __init__(self, allowed_tables: list[str], allowed_database: str) -> None:
        self._allowed_tables = {t.lower() for t in allowed_tables}
        self._allowed_db = allowed_database.lower()

    def verify(self, sql: str) -> str:
        """
        Parse and verify SQL. Returns the original SQL if safe.
        Raises CompilerError if any check fails.
        """
        # Check for forbidden keywords
        upper = sql.upper()
        for kw in FORBIDDEN_KEYWORDS:
            if re.search(rf"\b{kw}\b", upper):
                raise CompilerError(f"Forbidden keyword '{kw}' found in generated SQL")

        # Parse with sqlglot
        try:
            parsed = sqlglot.parse_one(sql, dialect="trino")
        except Exception as e:
            raise CompilerError(f"SQL parse error: {e}") from e

        # Must be a SELECT statement
        if not isinstance(parsed, exp.Select):
            raise CompilerError(f"Generated SQL is not a SELECT statement: {type(parsed).__name__}")

        # Check all referenced tables are in allowlist
        for table in parsed.find_all(exp.Table):
            table_name = table.name.lower()
            if table_name and table_name not in self._allowed_tables:
                raise CompilerError(f"Table not in allowlist: {table_name}")

        needs_limit = not parsed.find(exp.Limit)

        # Regenerate SQL with proper quoting so reserved-word table names
        # (e.g. 'order') are double-quoted in the output.
        try:
            sql = parsed.sql(dialect="trino")
        except Exception:
            pass  # keep original sql if generation fails

        # Append LIMIT after regeneration so it isn't lost
        if needs_limit:
            sql = sql.rstrip().rstrip(";") + " LIMIT 1000"

        return sql


class NLToSQLCompiler:
    """Compiles natural language questions to verified SQL using Bedrock."""

    def __init__(self) -> None:
        self._bedrock = boto3.client("bedrock-runtime", region_name=settings.aws_region)
        self._verifier = SQLVerifier(
            allowed_tables=settings.allowed_tables,
            allowed_database=settings.silver_db,
        )

    def compile(
        self,
        question: str,
        schema_context: dict[str, list[dict[str, Any]]],
        ontology_hints: list[dict[str, Any]] | None = None,
    ) -> str:
        """
        Compile a natural language question to verified SQL.
        Returns verified SQL string ready for Athena execution.
        """
        prompt = self._build_prompt(question, schema_context, ontology_hints or [])
        raw_sql = self._call_bedrock(prompt)
        logger.debug(f"Raw LLM SQL: {raw_sql}")

        # Strip markdown code blocks if present
        raw_sql = re.sub(r"```sql\s*", "", raw_sql, flags=re.IGNORECASE)
        raw_sql = re.sub(r"```\s*", "", raw_sql)
        raw_sql = raw_sql.strip()

        # Verify
        verified_sql = self._verifier.verify(raw_sql)
        logger.info(f"Verified SQL: {verified_sql[:100]}...")
        return verified_sql

    def _build_prompt(
        self,
        question: str,
        schema_context: dict[str, list[dict[str, Any]]],
        ontology_hints: list[dict[str, Any]],
    ) -> str:
        schema_str = json.dumps(schema_context, indent=2)
        hints_str = json.dumps(ontology_hints[:20], indent=2) if ontology_hints else "[]"

        return f"""Schema context (table -> columns):
{schema_str}

Ontology hints (natural language -> table/column mappings):
{hints_str}

Question: {question}

Generate a single SELECT SQL query to answer this question.
Database: {settings.silver_db}
Return ONLY the SQL query, nothing else."""

    def _call_bedrock(self, prompt: str) -> str:
        """Call Bedrock Claude to generate SQL."""
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "system": SYSTEM_PROMPT.format(database=settings.silver_db),
        }

        response = self._bedrock.invoke_model(
            modelId=settings.bedrock_model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )

        result = json.loads(response["body"].read())
        return result["content"][0]["text"]
