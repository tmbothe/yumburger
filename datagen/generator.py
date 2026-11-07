"""YumBurger synthetic data generator using Faker."""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from faker import Faker

from datagen.dictionary import (
    CUSTOMER_TIERS,
    MENU_ITEMS,
    ORDER_CHANNELS,
    PAYMENT_METHODS,
    REGION_STATES,
    REGIONS,
    SUPPLIER_CATEGORIES,
    SUPPLIER_NAMES,
)
from datagen.models import Customer, MenuItem, Order, OrderLine, Supplier

fake = Faker("en_US")
Faker.seed(42)
random.seed(42)

# Row count targets per scale
SCALE_TARGETS: dict[str, dict[str, int]] = {
    "small": {
        "supplier": 50,
        "menu_item": len(MENU_ITEMS),  # all 30 items
        "customer": 500,
        "order": 2000,
        "order_line": 6000,
    },
    "medium": {
        "supplier": 200,
        "menu_item": len(MENU_ITEMS),
        "customer": 5000,
        "order": 20000,
        "order_line": 60000,
    },
}

ALLERGEN_POOL = ["Gluten", "Dairy", "Eggs", "Soy", "Peanuts", "Sesame", "Fish", "Shellfish"]


def _random_region_state() -> tuple[str, str]:
    region = random.choice(REGIONS)
    state = random.choice(REGION_STATES[region])
    return region, state


def generate_suppliers(n: int) -> list[dict[str, Any]]:
    rows = []
    per_category = max(1, n // len(SUPPLIER_CATEGORIES))
    idx = 0
    for cat in SUPPLIER_CATEGORIES:
        names = SUPPLIER_NAMES.get(cat, [])
        pool = names * (per_category // max(1, len(names)) + 1)
        for name in pool[:per_category]:
            if idx >= n:
                break
            region, state = _random_region_state()
            s = Supplier(
                name=name,
                category=cat,
                region=region,
                state=state,
                contact_email=fake.company_email(),
                phone=fake.phone_number()[:20],
                active=random.random() > 0.05,
                contract_start=fake.date_between(start_date="-5y", end_date="-1y"),
                annual_spend_usd=round(random.uniform(100_000, 5_000_000), 2),
            )
            rows.append(s.model_dump())
            idx += 1
        if idx >= n:
            break
    # fill remaining with random
    while idx < n:
        cat = random.choice(SUPPLIER_CATEGORIES)
        names = SUPPLIER_NAMES.get(cat, ["Generic Supplier"])
        region, state = _random_region_state()
        s = Supplier(
            name=random.choice(names) + f" #{idx}",
            category=cat,
            region=region,
            state=state,
            contact_email=fake.company_email(),
            phone=fake.phone_number()[:20],
            active=random.random() > 0.05,
            contract_start=fake.date_between(start_date="-5y", end_date="-1y"),
            annual_spend_usd=round(random.uniform(100_000, 5_000_000), 2),
        )
        rows.append(s.model_dump())
        idx += 1
    return rows


def generate_menu_items() -> list[dict[str, Any]]:
    rows = []
    base_date = date(2015, 1, 1)
    for item_dict in MENU_ITEMS:
        allergens = random.sample(ALLERGEN_POOL, k=random.randint(1, 4))
        m = MenuItem(
            name=item_dict["name"],
            category=item_dict["category"],
            price_usd=item_dict["price_usd"],
            calories=item_dict["calories"],
            is_available=random.random() > 0.03,
            introduced_date=base_date + timedelta(days=random.randint(0, 1000)),
            allergens=",".join(allergens),
        )
        rows.append(m.model_dump())
    return rows


def generate_customers(n: int) -> list[dict[str, Any]]:
    rows = []
    for _ in range(n):
        region, state = _random_region_state()
        tier_weights = [0.5, 0.3, 0.15, 0.05]
        tier = random.choices(CUSTOMER_TIERS, weights=tier_weights)[0]
        c = Customer(
            first_name=fake.first_name(),
            last_name=fake.last_name(),
            email=fake.email(),
            tier=tier,
            region=region,
            state=state,
            signup_date=fake.date_between(start_date="-3y", end_date="today"),
            birth_year=random.randint(1960, 2005),
        )
        rows.append(c.model_dump())
    return rows


def generate_orders_and_lines(
    customers: list[dict[str, Any]],
    menu_items: list[dict[str, Any]],
    n_orders: int,
    n_lines_target: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    orders = []
    lines = []
    avg_lines = max(1, n_lines_target // n_orders)
    start_ts = datetime(2023, 1, 1, tzinfo=timezone.utc)
    end_ts = datetime(2024, 12, 31, 23, 59, tzinfo=timezone.utc)
    span_seconds = int((end_ts - start_ts).total_seconds())

    for _ in range(n_orders):
        customer = random.choice(customers)
        region = customer["region"]
        state = customer["state"]
        order_ts = start_ts + timedelta(seconds=random.randint(0, span_seconds))
        location_id = f"LOC-{state}-{random.randint(1, 20):03d}"

        o = Order(
            customer_id=customer["customer_id"],
            location_id=location_id,
            order_ts=order_ts,
            channel=random.choice(ORDER_CHANNELS),
            payment_method=random.choice(PAYMENT_METHODS),
            region=region,
            state=state,
        )

        n_lines = max(1, int(random.gauss(avg_lines, 1)))
        order_items = random.choices(menu_items, k=n_lines)

        order_total = 0.0
        for item in order_items:
            qty = random.randint(1, 3)
            line_total = round(item["price_usd"] * qty, 2)
            order_total += line_total
            ln = OrderLine(
                order_id=o.order_id,
                item_id=item["item_id"],
                item_name=item["name"],
                category=item["category"],
                qty=qty,
                unit_price=item["price_usd"],
                line_total=line_total,
            )
            lines.append(ln.model_dump())

        o.total_usd = round(order_total, 2)
        o.item_count = len(order_items)
        orders.append(o.model_dump())

    return orders, lines


def generate_all(scale: str = "small") -> dict[str, pd.DataFrame]:
    targets = SCALE_TARGETS.get(scale, SCALE_TARGETS["small"])

    print(f"Generating data at scale='{scale}'...")

    suppliers = generate_suppliers(targets["supplier"])
    print(f"  supplier:   {len(suppliers):,} rows")

    menu_items = generate_menu_items()
    print(f"  menu_item:  {len(menu_items):,} rows")

    customers = generate_customers(targets["customer"])
    print(f"  customer:   {len(customers):,} rows")

    orders, lines = generate_orders_and_lines(
        customers, menu_items,
        targets["order"],
        targets["order_line"],
    )
    print(f"  order:      {len(orders):,} rows")
    print(f"  order_line: {len(lines):,} rows")

    return {
        "supplier": pd.DataFrame(suppliers),
        "menu_item": pd.DataFrame(menu_items),
        "customer": pd.DataFrame(customers),
        "order": pd.DataFrame(orders),
        "order_line": pd.DataFrame(lines),
    }


def save_parquet(dfs: dict[str, pd.DataFrame], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for table_name, df in dfs.items():
        path = output_dir / f"{table_name}.parquet"
        df.to_parquet(path, index=False, engine="pyarrow")
        size_kb = path.stat().st_size // 1024
        print(f"  Saved {path.name} ({len(df):,} rows, {size_kb} KB)")
