"""Pydantic v2 models for YumBurger synthetic data."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


def new_id() -> str:
    return str(uuid.uuid4())


class Supplier(BaseModel):
    supplier_id: str = Field(default_factory=new_id)
    name: str
    category: str
    region: str
    state: str
    contact_email: str
    phone: str
    active: bool = True
    contract_start: date
    annual_spend_usd: float

    @field_validator("annual_spend_usd")
    @classmethod
    def round_spend(cls, v: float) -> float:
        return round(v, 2)


class MenuItem(BaseModel):
    item_id: str = Field(default_factory=new_id)
    name: str
    category: str
    price_usd: float
    calories: int
    is_available: bool = True
    introduced_date: date
    allergens: str  # comma-separated

    @field_validator("price_usd")
    @classmethod
    def round_price(cls, v: float) -> float:
        return round(v, 2)


class Customer(BaseModel):
    customer_id: str = Field(default_factory=new_id)
    first_name: str
    last_name: str
    email: str
    tier: str
    region: str
    state: str
    signup_date: date
    birth_year: int
    total_orders: int = 0
    lifetime_spend_usd: float = 0.0

    @field_validator("lifetime_spend_usd")
    @classmethod
    def round_spend(cls, v: float) -> float:
        return round(v, 2)


class Order(BaseModel):
    order_id: str = Field(default_factory=new_id)
    customer_id: str
    location_id: str
    order_ts: datetime
    channel: str
    payment_method: str
    region: str
    state: str
    total_usd: float = 0.0
    item_count: int = 0

    @field_validator("total_usd")
    @classmethod
    def round_total(cls, v: float) -> float:
        return round(v, 2)


class OrderLine(BaseModel):
    line_id: str = Field(default_factory=new_id)
    order_id: str
    item_id: str
    item_name: str
    category: str
    qty: int
    unit_price: float
    line_total: float

    @field_validator("unit_price", "line_total")
    @classmethod
    def round_money(cls, v: float) -> float:
        return round(v, 2)
