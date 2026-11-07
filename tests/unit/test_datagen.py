"""Unit tests for datagen module."""

from __future__ import annotations

import pytest
from datagen.generator import generate_all, generate_menu_items, generate_suppliers, generate_customers
from datagen.models import Customer, MenuItem, Order, OrderLine, Supplier


class TestModels:
    def test_supplier_model(self):
        from datetime import date
        s = Supplier(
            name="Test Supplier",
            category="Beef",
            region="Northeast",
            state="NY",
            contact_email="test@test.com",
            phone="555-1234",
            contract_start=date(2020, 1, 1),
            annual_spend_usd=1_000_000.123,
        )
        assert s.annual_spend_usd == 1_000_000.12

    def test_menu_item_model(self):
        from datetime import date
        m = MenuItem(
            name="Big Yum",
            category="Burger",
            price_usd=5.999,
            calories=550,
            introduced_date=date(2015, 6, 1),
            allergens="Gluten,Dairy",
        )
        assert m.price_usd == 6.0

    def test_supplier_id_is_uuid(self):
        from datetime import date
        s = Supplier(
            name="S",
            category="Beef",
            region="West",
            state="CA",
            contact_email="a@b.com",
            phone="111",
            contract_start=date(2020, 1, 1),
            annual_spend_usd=100.0,
        )
        import uuid
        uuid.UUID(s.supplier_id)  # raises if not valid UUID


class TestGenerator:
    def test_generate_suppliers_count(self):
        rows = generate_suppliers(50)
        assert len(rows) == 50

    def test_generate_menu_items_count(self):
        rows = generate_menu_items()
        assert len(rows) == 30  # 30 items in dictionary

    def test_generate_customers_count(self):
        rows = generate_customers(100)
        assert len(rows) == 100

    def test_generate_all_small(self):
        dfs = generate_all(scale="small")
        assert len(dfs) == 5
        assert len(dfs["supplier"]) == 50
        assert len(dfs["menu_item"]) == 30
        assert len(dfs["customer"]) == 500
        assert len(dfs["order"]) == 2000
        assert len(dfs["order_line"]) > 0

    def test_supplier_categories(self):
        from datagen.dictionary import SUPPLIER_CATEGORIES
        rows = generate_suppliers(50)
        cats = {r["category"] for r in rows}
        assert cats.issubset(set(SUPPLIER_CATEGORIES))

    def test_customer_tiers(self):
        from datagen.dictionary import CUSTOMER_TIERS
        rows = generate_customers(100)
        tiers = {r["tier"] for r in rows}
        assert tiers.issubset(set(CUSTOMER_TIERS))

    def test_order_lines_reference_valid_orders(self):
        dfs = generate_all(scale="small")
        order_ids = set(dfs["order"]["order_id"].tolist())
        line_order_ids = set(dfs["order_line"]["order_id"].tolist())
        assert line_order_ids.issubset(order_ids)

    def test_no_negative_prices(self):
        rows = generate_menu_items()
        assert all(r["price_usd"] > 0 for r in rows)

    def test_parquet_roundtrip(self, tmp_path):
        import pandas as pd
        dfs = generate_all(scale="small")
        from datagen.generator import save_parquet
        save_parquet(dfs, tmp_path)
        for table in dfs:
            path = tmp_path / f"{table}.parquet"
            assert path.exists()
            reloaded = pd.read_parquet(path)
            assert len(reloaded) == len(dfs[table])
