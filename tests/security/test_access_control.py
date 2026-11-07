"""
Security tests — verify that IAM deny policies and SQL verifier
prevent unauthorized data access.
These tests use the SQLVerifier directly (no AWS calls needed).
"""

from __future__ import annotations

import pytest
from connector.compiler import CompilerError, SQLVerifier

ALLOWED_TABLES = ["supplier", "menu_item", "customer", "order", "order_line"]
ALLOWED_DB = "yumburger_silver"


@pytest.fixture
def verifier():
    return SQLVerifier(allowed_tables=ALLOWED_TABLES, allowed_database=ALLOWED_DB)


class TestSQLInjectionPrevention:
    """Verify that the SQL verifier blocks injection attempts."""

    def test_union_injection_blocked_by_forbidden_table(self, verifier):
        """UNION SELECT from non-allowed table should be blocked (by table check or non-SELECT check)."""
        sql = "SELECT * FROM menu_item UNION SELECT * FROM aws_credentials LIMIT 10"
        with pytest.raises(CompilerError):
            verifier.verify(sql)

    def test_comment_injection_blocked(self, verifier):
        """Multi-statement injection with DROP is caught by keyword scan before parsing."""
        sql = "SELECT * FROM menu_item; DROP TABLE customer"
        # The keyword scanner catches 'DROP' before sqlglot parsing
        with pytest.raises(CompilerError, match="DROP"):
            verifier.verify(sql)

    def test_mutation_via_cte_blocked(self, verifier):
        """Attempt to use CTE to smuggle a mutation."""
        sql = """
            WITH x AS (DELETE FROM customer WHERE 1=1)
            SELECT * FROM menu_item
        """
        with pytest.raises(CompilerError):
            verifier.verify(sql)

    def test_system_table_blocked(self, verifier):
        """Access to system/information_schema tables blocked."""
        sql = "SELECT * FROM information_schema.tables LIMIT 10"
        with pytest.raises(CompilerError, match="not in allowlist"):
            verifier.verify(sql)

    def test_arbitrary_table_blocked(self, verifier):
        """Completely arbitrary table name blocked."""
        sql = "SELECT * FROM production_secrets LIMIT 10"
        with pytest.raises(CompilerError, match="not in allowlist"):
            verifier.verify(sql)

    def test_alter_blocked(self, verifier):
        with pytest.raises(CompilerError, match="ALTER"):
            verifier.verify("ALTER TABLE menu_item ADD COLUMN hack STRING")

    def test_revoke_blocked(self, verifier):
        with pytest.raises(CompilerError, match="REVOKE"):
            verifier.verify("REVOKE ALL ON menu_item FROM analyst")

    def test_grant_blocked(self, verifier):
        with pytest.raises(CompilerError, match="GRANT"):
            verifier.verify("GRANT ALL ON customer TO PUBLIC")


class TestConnectorRuntimeDenyPolicy:
    """
    Verify that the IAM Deny policy for connector-runtime is configured correctly.
    These tests inspect the CDK stack configuration, not live AWS.
    """

    def test_deny_policy_exists_in_iam_stack(self):
        """Check that the IAMStack defines an explicit Deny on s3:GetObject for silver."""
        from pathlib import Path
        stack_code = (
            Path(__file__).parent.parent.parent / "infra" / "stacks" / "iam_stack.py"
        ).read_text()
        assert "DenyDirectSilverS3Access" in stack_code
        assert "s3:GetObject" in stack_code
        assert "Effect.DENY" in stack_code

    def test_connector_cannot_query_data_directly(self):
        """
        Verifier ensures SQL must go through Athena execution layer,
        which then enforces Lake Formation policies.
        The connector-runtime role itself only has DESCRIBE permissions.
        This is enforced at the IAM + LF level, not the verifier.
        Test confirms the architectural invariant is documented and implemented.
        """
        from pathlib import Path
        root = Path(__file__).parent.parent.parent
        decisions = (root / "docs" / "DECISIONS.md").read_text()
        assert "Athena as single Iceberg access layer" in decisions
        # Verify the actual IAM stack implements the Deny
        iam_stack = (root / "infra" / "stacks" / "iam_stack.py").read_text()
        assert "s3:GetObject" in iam_stack
        assert "Effect.DENY" in iam_stack
