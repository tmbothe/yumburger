"""
YumBurger Federated Semantic Connector — FastAPI application.

Endpoints:
  GET  /health          — health check
  POST /query           — NL question → compiled SQL → Athena results
  GET  /metadata/{table} — Iceberg table schema
  GET  /snapshots/{table} — Iceberg snapshot history
  GET  /ontology/classes  — ontology classes
  GET  /ontology/properties — ontology properties
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

import boto3
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from connector.audit import AuditPlane
from connector.compiler import NLToSQLCompiler, CompilerError
from connector.engines.athena import AthenaEngine
from connector.identity import assume_persona_role
from connector.memory import MemoryPlane
from connector.metadata import MetadataPlane
from connector.models import (
    AskResponse,
    HealthResponse,
    MetadataResponse,
    OntologyClassResponse,
    QueryRequest,
    QueryResponse,
    SnapshotResponse,
)
from connector.ontology import OntologyPlane
from connector.settings import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()

# Module-level singletons (initialized at startup)
_audit: AuditPlane | None = None
_compiler: NLToSQLCompiler | None = None
_memory: MemoryPlane | None = None
_metadata: MetadataPlane | None = None
_ontology: OntologyPlane | None = None

# Cached at startup — schema and ontology are static; no need to re-fetch per request
_schema_cache: dict | None = None
_ontology_cache: list | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _audit, _compiler, _memory, _metadata, _ontology, _schema_cache, _ontology_cache
    logger.info("Starting YumBurger connector...")
    _audit = AuditPlane()
    _compiler = NLToSQLCompiler()
    _memory = MemoryPlane()
    runtime_session = boto3.Session(region_name=settings.aws_region)
    _metadata = MetadataPlane(runtime_session)
    _ontology = OntologyPlane(runtime_session)

    # Pre-warm caches — runs 6 Athena queries once at startup, not on every request
    logger.info("Pre-warming schema and ontology caches...")
    try:
        _schema_cache = _metadata.get_schema_summary()
        logger.info(f"Schema cache loaded for tables: {list(_schema_cache.keys())}")
    except Exception as e:
        logger.warning(f"Schema cache warm-up failed: {e} — will fetch per request")
        _schema_cache = None

    try:
        _ontology_cache = _ontology.get_all_mappings()
        logger.info(f"Ontology cache loaded: {len(_ontology_cache)} mappings")
    except Exception as e:
        logger.warning(f"Ontology cache warm-up failed: {e} — will fetch per request")
        _ontology_cache = None

    logger.info("Connector initialized.")
    yield
    logger.info("Connector shutting down.")


app = FastAPI(
    title="YumBurger Federated Semantic Connector",
    description=(
        "**Where every bite counts.**\n\n"
        "Governed NL→SQL query interface over the YumBurger Iceberg data lake.\n\n"
        "Ask natural language questions — get audited, governed answers from the silver zone."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", checks={"connector": "ok"})


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest) -> QueryResponse:
    """
    Accept a natural language question, compile it to verified SQL,
    execute via Athena as the requested persona, return results.
    """
    request_id = str(uuid.uuid4())
    start = time.monotonic()

    try:
        # 1. Get schema context — use startup cache, fall back to live fetch
        schema_context = _schema_cache if _schema_cache is not None else _metadata.get_schema_summary()

        # 2. Get ontology hints — use startup cache, fall back to live fetch
        ontology_hints = _ontology_cache if _ontology_cache is not None else _ontology.get_all_mappings()

        # 3. Compile NL → verified SQL
        try:
            compiled_sql = _compiler.compile(
                question=req.question,
                schema_context=schema_context,
                ontology_hints=ontology_hints,
            )
        except CompilerError as e:
            raise HTTPException(status_code=422, detail=f"Query compilation failed: {e}")

        # 4. Extract tables accessed (for audit)
        import sqlglot
        import sqlglot.expressions as sexp
        tables_accessed = []
        try:
            parsed = sqlglot.parse_one(compiled_sql, dialect="trino")
            tables_accessed = [t.name for t in parsed.find_all(sexp.Table) if t.name]
        except Exception:
            tables_accessed = ["unknown"]

        # 5. Pre-audit
        _audit.pre_audit(
            request_id=request_id,
            persona=req.persona,
            question=req.question,
            compiled_sql=compiled_sql,
            tables_accessed=tables_accessed,
        )

        # 6. Execute as persona role
        persona_session = assume_persona_role(req.persona)
        engine = AthenaEngine(persona_session)
        rows = engine.execute(compiled_sql)

        # Limit rows in response
        rows = rows[: req.max_rows]
        duration_ms = int((time.monotonic() - start) * 1000)

        # 7. Post-audit
        _audit.post_audit(
            request_id=request_id,
            persona=req.persona,
            row_count=len(rows),
            execution_id=request_id,
            duration_ms=duration_ms,
            success=True,
        )

        return QueryResponse(
            request_id=request_id,
            question=req.question,
            persona=req.persona,
            compiled_sql=compiled_sql,
            rows=rows,
            row_count=len(rows),
            duration_ms=duration_ms,
        )

    except HTTPException:
        raise
    except Exception as e:
        duration_ms = int((time.monotonic() - start) * 1000)
        _audit.post_audit(
            request_id=request_id,
            persona=req.persona,
            row_count=0,
            execution_id=request_id,
            duration_ms=duration_ms,
            success=False,
            error_msg=str(e),
        )
        logger.exception(f"Query failed for request_id={request_id}")
        raise HTTPException(status_code=500, detail="Query execution failed")


_BODHI_SYSTEM = """You are YumBot, the YumBurger restaurant assistant.
You help customers and operations teams understand menu items, supplier data,
sales performance, and customer insights. Be friendly and concise.
Summarize the data results in 2-3 clear sentences."""


@app.post("/ask", response_model=AskResponse)
def ask(req: QueryRequest) -> AskResponse:
    """
    Single-call endpoint for Bedrock Agents / Bodhi.
    Runs the full pipeline (NL→SQL→Athena→summarize) and returns a
    natural language answer. Pass session_id to maintain conversation context.
    """
    request_id = str(uuid.uuid4())
    session_id = req.session_id or str(uuid.uuid4())
    start = time.monotonic()

    try:
        # 1. Load conversation context from memory (non-blocking — empty on failure)
        mem_ctx = _memory.get_context(session_id)
        history_block = mem_ctx.to_prompt_block()

        schema_context = _schema_cache if _schema_cache is not None else _metadata.get_schema_summary()
        ontology_hints = _ontology_cache if _ontology_cache is not None else _ontology.get_all_mappings()

        # 2. Compile NL → SQL, injecting conversation history for follow-up awareness
        try:
            compiled_sql = _compiler.compile(
                question=req.question,
                schema_context=schema_context,
                ontology_hints=ontology_hints,
                conversation_history=history_block,
            )
        except CompilerError as e:
            raise HTTPException(status_code=422, detail=f"Query compilation failed: {e}")

        import sqlglot
        import sqlglot.expressions as sexp
        tables_accessed = []
        try:
            parsed = sqlglot.parse_one(compiled_sql, dialect="trino")
            tables_accessed = [t.name for t in parsed.find_all(sexp.Table) if t.name]
        except Exception:
            tables_accessed = ["unknown"]

        _audit.pre_audit(
            request_id=request_id,
            persona=req.persona,
            question=req.question,
            compiled_sql=compiled_sql,
            tables_accessed=tables_accessed,
        )

        persona_session = assume_persona_role(req.persona)
        engine = AthenaEngine(persona_session)
        rows = engine.execute(compiled_sql)
        rows = rows[: req.max_rows]
        duration_ms = int((time.monotonic() - start) * 1000)

        _audit.post_audit(
            request_id=request_id,
            persona=req.persona,
            row_count=len(rows),
            execution_id=request_id,
            duration_ms=duration_ms,
            success=True,
        )

        # 3. Summarize with Bedrock, injecting conversation context for cohesive replies
        import boto3 as _boto3
        import json as _json
        _bedrock = _boto3.client("bedrock-runtime", region_name=settings.aws_region)
        rows_preview = _json.dumps(rows[:20], indent=2)
        summary_prompt = (
            f"{history_block}\n\n" if history_block else ""
        ) + (
            f"Question: {req.question}\n\n"
            f"SQL executed:\n{compiled_sql}\n\n"
            f"Results ({len(rows)} rows):\n{rows_preview}\n\n"
            "Summarize these results in 2-3 sentences."
        )
        llm_resp = _bedrock.invoke_model(
            modelId=settings.bedrock_model_id,
            body=_json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 512,
                "system": _BODHI_SYSTEM,
                "messages": [{"role": "user", "content": summary_prompt}],
            }),
            contentType="application/json",
            accept="application/json",
        )
        answer = _json.loads(llm_resp["body"].read())["content"][0]["text"]

        # 4. Persist this turn to memory (non-blocking)
        _memory.add_turn(
            session_id=session_id,
            persona=req.persona,
            question=req.question,
            answer=answer,
            sql=compiled_sql,
            row_count=len(rows),
        )

        return AskResponse(
            request_id=request_id,
            question=req.question,
            answer=answer,
            compiled_sql=compiled_sql,
            row_count=len(rows),
            duration_ms=int((time.monotonic() - start) * 1000),
            session_id=session_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"/ask failed for request_id={request_id}")
        raise HTTPException(status_code=500, detail="Ask failed")


@app.get("/metadata/{table}", response_model=MetadataResponse)
def get_metadata(table: str) -> MetadataResponse:
    """Return Iceberg table schema."""
    if table not in settings.allowed_tables:
        raise HTTPException(status_code=404, detail=f"Table not found: {table}")
    columns = _metadata.describe_table(table)
    return MetadataResponse(table=table, columns=columns)


@app.get("/snapshots/{table}", response_model=SnapshotResponse)
def get_snapshots(table: str) -> SnapshotResponse:
    """Return Iceberg snapshot history for a table."""
    if table not in settings.allowed_tables:
        raise HTTPException(status_code=404, detail=f"Table not found: {table}")
    snapshots = _metadata.get_snapshots(table)
    return SnapshotResponse(table=table, snapshots=snapshots)


@app.get("/ontology/classes")
def get_ontology_classes() -> list[dict[str, Any]]:
    """Return all ontology classes from yumburger_semantic."""
    return _ontology.get_classes()


@app.get("/ontology/properties")
def get_ontology_properties() -> list[dict[str, Any]]:
    """Return all ontology properties from yumburger_semantic."""
    return _ontology.get_properties()


@app.get("/tables")
def list_tables() -> dict[str, list[str]]:
    """Return allowed query tables."""
    return {"tables": settings.allowed_tables}


def main() -> None:
    uvicorn.run(
        "connector.main:app",
        host=settings.connector_host,
        port=settings.connector_port,
        log_level=settings.log_level.lower(),
        reload=False,
    )


if __name__ == "__main__":
    main()
