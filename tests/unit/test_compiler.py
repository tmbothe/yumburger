"""Unit tests for the SQL verifier/compiler."""

from __future__ import annotations

import pytest
from connector.compiler import CompilerError, SQLVerifier

ALLOWED_TABLES = ["supplier", "menu_item", "customer", "order", "order_line"]
ALLOWED_DB = "yumburger_silver"


@pytest.fixture
def verifier():
    return SQLVerifier(allowed_tables=ALLOWED_TABLES, allowed_database=ALLOWED_DB)


class TestSQLVerifier:
    def test_valid_select(self, verifier):
        sql = "SELECT name, price_usd FROM menu_item WHERE category = 'Burger' LIMIT 10"
        result = verifier.verify(sql)
        assert "SELECT" in result.upper()

    def test_forbidden_insert(self, verifier):
        with pytest.raises(CompilerError, match="INSERT"):
            verifier.verify("INSERT INTO menu_item VALUES ('a','b','c')")

    def test_forbidden_drop(self, verifier):
        with pytest.raises(CompilerError, match="DROP"):
            verifier.verify("DROP TABLE menu_item")

    def test_forbidden_delete(self, verifier):
        with pytest.raises(CompilerError, match="DELETE"):
            verifier.verify("DELETE FROM customer WHERE customer_id = '123'")

    def test_forbidden_update(self, verifier):
        with pytest.raises(CompilerError, match="UPDATE"):
            verifier.verify("UPDATE supplier SET active = false")

    def test_forbidden_create(self, verifier):
        with pytest.raises(CompilerError, match="CREATE"):
            verifier.verify("CREATE TABLE hack AS SELECT * FROM customer")

    def test_unknown_table_blocked(self, verifier):
        with pytest.raises(CompilerError, match="not in allowlist"):
            verifier.verify("SELECT * FROM secret_table LIMIT 10")

    def test_non_select_statement_blocked(self, verifier):
        with pytest.raises(CompilerError):
            verifier.verify("SHOW TABLES")

    def test_limit_added_if_missing(self, verifier):
        sql = "SELECT COUNT(*) FROM order"
        result = verifier.verify(sql)
        assert "LIMIT" in result.upper()

    def test_aggregate_query_valid(self, verifier):
        sql = """
            SELECT category, AVG(price_usd) as avg_price
            FROM menu_item
            GROUP BY category
            ORDER BY avg_price DESC
            LIMIT 10
        """
        result = verifier.verify(sql)
        assert result is not None

    def test_join_allowed_tables_valid(self, verifier):
        sql = """
            SELECT o.order_id, m.name, ol.qty
            FROM order o
            JOIN order_line ol ON o.order_id = ol.order_id
            JOIN menu_item m ON ol.item_id = m.item_id
            LIMIT 100
        """
        result = verifier.verify(sql)
        assert result is not None

    def test_subquery_with_allowed_tables(self, verifier):
        sql = """
            SELECT * FROM (
                SELECT customer_id, SUM(total_usd) as total
                FROM order
                GROUP BY customer_id
            ) sub
            ORDER BY total DESC
            LIMIT 10
        """
        result = verifier.verify(sql)
        assert result is not None
