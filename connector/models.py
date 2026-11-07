"""Pydantic models for connector API request/response."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000, description="Natural language question")
    persona: Literal["analyst", "admin"] = Field(default="analyst")
    max_rows: int = Field(default=100, ge=1, le=1000)


class QueryResponse(BaseModel):
    request_id: str
    question: str
    persona: str
    compiled_sql: str
    rows: list[dict[str, Any]]
    row_count: int
    duration_ms: int


class MetadataResponse(BaseModel):
    table: str
    columns: list[dict[str, Any]]


class SnapshotResponse(BaseModel):
    table: str
    snapshots: list[dict[str, Any]]


class OntologyClassResponse(BaseModel):
    class_uri: str
    local_name: str
    label: str
    comment: str
    maps_to_table: str | None


class AskResponse(BaseModel):
    request_id: str
    question: str
    answer: str
    compiled_sql: str
    row_count: int
    duration_ms: int


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"] = "ok"
    version: str = "0.1.0"
    checks: dict[str, str] = Field(default_factory=dict)
