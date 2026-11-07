# YumBurger Federated Semantic Connector — Technical Reference

**Author:** Data Engineering / AI Architecture
**Date:** 2026-11-07
**Version:** 0.1.0 (POC)

---

## Table of Contents

1. [What the Connector Does](#1-what-the-connector-does)
2. [High-Level Architecture](#2-high-level-architecture)
3. [The Five Planes](#3-the-five-planes)
4. [Key Libraries](#4-key-libraries)
5. [Step-by-Step Query Flow](#5-step-by-step-query-flow-post-query)
6. [Security Model](#6-security-model)
7. [Configuration](#7-configuration)
8. [API Reference](#8-api-reference)
9. [Running the Connector](#9-running-the-connector)

---

## 1. What the Connector Does

The YumBurger Federated Semantic Connector translates a plain-English business question into a **governed, audited SQL query** executed against the Iceberg silver zone on S3, and returns structured results.

```
"How many active suppliers do we have?"
        |
        v
  [Connector FastAPI]
        |
        |-- fetch schema context (MetadataPlane)
        |-- fetch ontology hints (OntologyPlane)
        |-- generate SQL via Bedrock LLM (QueryPlane - compiler)
        |-- verify SQL with sqlglot AST (QueryPlane - verifier)
        |-- write PRE_QUERY audit event (AuditPlane)
        |-- assume persona IAM role (IdentityPlane)
        |-- execute verified SQL via Athena (QueryPlane - engine)
        |-- write POST_QUERY audit event (AuditPlane)
        |
        v
  { rows: [...], compiled_sql: "...", duration_ms: 420 }
```

**Key invariant:** LLM-generated SQL is **never** executed. Only AST-verified SQL that passes all safety checks reaches Athena.

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Streamlit UI  (port 8501)                   │
│                         app.py                                  │
└──────────────────────────┬──────────────────────────────────────┘
                           │  HTTP REST
                           v
┌─────────────────────────────────────────────────────────────────┐
│          FastAPI Connector Service  (port 8000)                 │
│                     connector/main.py                           │
│                                                                 │
│   ┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│   │ Identity    │  │  Metadata    │  │  Semantic (Ontology) │  │
│   │ Plane       │  │  Plane       │  │  Plane               │  │
│   │ identity.py │  │ metadata.py  │  │  ontology.py         │  │
│   └─────────────┘  └──────────────┘  └──────────────────────┘  │
│                                                                 │
│   ┌─────────────────────────────────┐  ┌──────────────────┐    │
│   │          Query Plane            │  │   Audit Plane    │    │
│   │  compiler.py + engines/athena.py│  │   audit.py       │    │
│   └─────────────────────────────────┘  └──────────────────┘    │
└──────────┬────────────────────────┬────────────────────────────┘
           │  STS AssumeRole        │  Athena API
           v                        v
    ┌─────────────┐         ┌──────────────────┐
    │  AWS IAM    │         │  Amazon Athena    │
    │  Persona    │         │  Engine v3        │
    │  Roles      │         │  (Trino dialect)  │
    └─────────────┘         └────────┬─────────┘
                                     │  LF credential vending
                                     v
                            ┌──────────────────┐
                            │  Apache Iceberg   │
                            │  Silver Zone S3   │
                            │  yumburger_silver │
                            └──────────────────┘
                                     │
                            ┌──────────────────┐
                            │  AWS Lake         │
                            │  Formation        │
                            │  (column/row LF)  │
                            └──────────────────┘
```

**AWS services touched per query:**
| Service | Purpose |
|---------|---------|
| Amazon Bedrock | LLM SQL generation (Claude Haiku) |
| AWS STS | Persona role assumption |
| Amazon Athena | SQL execution over Iceberg |
| AWS Glue Catalog | Table metadata / schema |
| AWS Lake Formation | Column & row-level access control |
| Amazon S3 | Iceberg data files + Athena result output |
| Amazon DynamoDB | Audit trail (PRE/POST events) |

---

## 3. The Five Planes

### 3.1 Identity Plane — `connector/identity.py`

**Purpose:** Exchange the connector-runtime credentials for short-lived persona credentials using AWS STS `AssumeRole`.

```python
def assume_persona_role(persona: PersonaType) -> boto3.Session:
    sts = boto3.client("sts", ...)
    response = sts.assume_role(
        RoleArn="arn:aws:iam::442042510197:role/yumBurger-analyst-persona",
        RoleSessionName="yumBurger-connector-analyst",
        DurationSeconds=900,   # 15-minute temporary credentials
    )
    creds = response["Credentials"]
    return boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
    )
```

**Why it matters:**
- Each query runs under a persona's IAM role, not the connector-runtime role
- Lake Formation enforces column/row policies against the **persona role**, not the connector
- Two personas: `analyst` (read-only, restricted columns) and `admin` (full access)
- Credentials expire in 15 minutes — no long-lived credential exposure

---

### 3.2 Metadata Plane — `connector/metadata.py`

**Purpose:** Fetch Iceberg table schemas and snapshot history from Athena — without touching S3 directly.

Key methods:
- `describe_table(table)` — runs `DESCRIBE yumburger_silver.<table>` via Athena
- `get_snapshots(table)` — queries `"yumburger_silver"."<table>$snapshots"` Iceberg metadata table
- `get_schema_summary()` — returns `{table: [columns]}` dict for all allowed tables — this is the **schema context** fed to the LLM

```python
def get_schema_summary(self) -> dict[str, list[dict]]:
    summary = {}
    for table in settings.allowed_tables:
        try:
            cols = self.describe_table(table)
            summary[table] = cols
        except Exception:
            summary[table] = []
    return summary
```

This schema summary travels to Bedrock so the LLM knows exactly what columns exist and can write syntactically correct SQL against real table structures.

---

### 3.3 Semantic (Ontology) Plane — `connector/ontology.py`

**Purpose:** Read the semantic ontology — classes, properties, and NL-to-SQL term mappings — from `yumburger_semantic` Iceberg tables via Athena.

Key methods:
- `get_classes()` — 7 OWL classes (MenuItem, Customer, Order, etc.) mapped to silver tables
- `get_properties()` — 12 properties (hasPrice, hasTier, etc.) mapped to columns
- `get_all_mappings()` — 74 NL-term mappings (e.g. "active supplier" → `supplier.active = true`)

```python
def get_all_mappings(self) -> list[dict]:
    return self._engine.execute(
        "SELECT * FROM ontology_mapping ORDER BY nl_term",
        database=self._db,
    )
```

**Why ontology matters for query quality:**
The 74 mappings are injected into the Bedrock prompt as "ontology hints". When a user asks "which suppliers are active?" the LLM sees the hint `active supplier → supplier, active, active = true` and generates precise SQL instead of guessing.

---

### 3.4 Query Plane — `connector/compiler.py` + `connector/engines/athena.py`

This is the core plane. It has two components:

#### NLToSQLCompiler (`compiler.py`)

Calls Bedrock to convert the NL question into SQL, then verifies it.

```python
def compile(self, question, schema_context, ontology_hints) -> str:
    prompt = self._build_prompt(question, schema_context, ontology_hints)
    raw_sql = self._call_bedrock(prompt)       # LLM SQL — NEVER executed
    raw_sql = strip_markdown(raw_sql)
    verified_sql = self._verifier.verify(raw_sql)   # AST check
    return verified_sql                        # only this is executed
```

The Bedrock call uses the **Messages API** with a system prompt:

```python
body = {
    "anthropic_version": "bedrock-2023-05-31",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": prompt}],
    "system": SYSTEM_PROMPT,   # rules: SELECT only, table aliases, LIMIT
}
response = self._bedrock.invoke_model(
    modelId=settings.bedrock_model_id,   # us.anthropic.claude-haiku-4-5-20251001-v1:0
    body=json.dumps(body),
)
```

#### SQLVerifier (`compiler.py`)

**The safety gate** — every LLM-generated SQL must pass all four checks before execution:

```
Check 1: Forbidden keyword scan (regex on uppercased SQL)
         INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE, GRANT,
         REVOKE, EXEC, EXECUTE, MERGE, CALL, LOAD, COPY → CompilerError

Check 2: AST parse with sqlglot (dialect="trino")
         If parse fails → CompilerError (malformed SQL blocked)

Check 3: Statement type must be exp.Select
         Any non-SELECT statement → CompilerError

Check 4: Table allowlist — every table in the AST must be in
         {supplier, menu_item, customer, order, order_line}
         Unknown table → CompilerError

Post-check: SQL regenerated via sqlglot for proper quoting
            (reserved word 'order' → "order" automatically)
            LIMIT 1000 appended if no LIMIT clause present
```

```python
def verify(self, sql: str) -> str:
    # Check 1: forbidden keywords
    upper = sql.upper()
    for kw in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{kw}\b", upper):
            raise CompilerError(f"Forbidden keyword '{kw}'")

    # Check 2: parse
    parsed = sqlglot.parse_one(sql, dialect="trino")

    # Check 3: SELECT only
    if not isinstance(parsed, exp.Select):
        raise CompilerError("Not a SELECT")

    # Check 4: table allowlist
    for table in parsed.find_all(exp.Table):
        if table.name.lower() not in self._allowed_tables:
            raise CompilerError(f"Table not in allowlist: {table.name}")

    # Regenerate with proper quoting + enforce LIMIT
    needs_limit = not parsed.find(exp.Limit)
    sql = parsed.sql(dialect="trino")
    if needs_limit:
        sql = sql.rstrip().rstrip(";") + " LIMIT 1000"
    return sql
```

#### AthenaEngine (`engines/athena.py`)

Executes verified SQL against Athena and returns results as a list of dicts.

```python
def execute(self, sql, database=None) -> list[dict]:
    resp = self._client.start_query_execution(
        QueryString=sql,
        WorkGroup=settings.workgroup,
        QueryExecutionContext={"Database": db},
        ResultConfiguration={"OutputLocation": "s3://..."},
    )
    execution_id = resp["QueryExecutionId"]
    self._poll(execution_id, timeout)         # 1-second polling loop
    return self._fetch_results(execution_id)  # paginated result fetch
```

Result fetch uses boto3 paginators to handle result sets of any size:
```python
paginator = self._client.get_paginator("get_query_results")
for page in paginator.paginate(QueryExecutionId=execution_id):
    # first row of first page = column headers
    # all subsequent rows = data
```

---

### 3.5 Audit Plane — `connector/audit.py`

**Purpose:** Write tamper-evident audit events to DynamoDB before and after every query. Never blocks query execution — failures are logged and swallowed.

**PRE_QUERY event** (written before Athena execution):
```
request_id    UUID (partition key)
event_type    "PRE_QUERY"
persona       "analyst" | "admin"
question_hash SHA-256[:16] of the question text  (privacy: raw text not stored)
query_hash    SHA-256[:16] of the compiled SQL
tables        ["supplier", "menu_item", ...]
ts            ISO 8601 UTC timestamp
ttl           Unix epoch + 90 days (DynamoDB auto-delete)
```

**POST_QUERY event** (written after results returned):
```
request_id    UUID + "#post"
event_type    "POST_QUERY"
persona       "analyst" | "admin"
row_count     number of rows returned
duration_ms   end-to-end latency
execution_id  Athena QueryExecutionId
success       true | false
error_msg     first 1000 chars if failed
```

**Privacy design:** The original question is never stored in DynamoDB — only its SHA-256 hash. This satisfies data minimization for audit purposes.

---

## 4. Key Libraries

### FastAPI + Uvicorn

**What it is:** FastAPI is a modern Python web framework built on Starlette and Pydantic. Uvicorn is the ASGI server that runs it.

**How it's used:**
- `FastAPI()` creates the app with OpenAPI docs auto-generated at `/docs`
- `@asynccontextmanager lifespan` initializes all planes once at startup (not per-request)
- `@app.post("/query", response_model=QueryResponse)` — Pydantic validates request and response automatically
- `HTTPException(422)` signals compiler rejection; `HTTPException(500)` signals engine failure
- `CORSMiddleware` allows the Streamlit UI (different port) to call the API

```python
# Startup — singletons initialized once
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _audit, _compiler, _metadata, _ontology
    _audit = AuditPlane()
    _compiler = NLToSQLCompiler()
    runtime_session = boto3.Session(...)
    _metadata = MetadataPlane(runtime_session)
    _ontology = OntologyPlane(runtime_session)
    yield
```

**Why singletons matter:** `NLToSQLCompiler` creates a boto3 Bedrock client on init. `MetadataPlane` caches schema summaries. Creating these per-request would add significant latency.

---

### Pydantic v2 + pydantic-settings

**What it is:** Pydantic is a data validation library using Python type annotations. `pydantic-settings` extends it to load from `.env` files and environment variables.

**How it's used:**

`ConnectorSettings` (settings.py) loads config from two sources:
- `.env` file: `BEDROCK_MODEL_ID`, `AWS_REGION`, `CONNECTOR_PORT`, `LOG_LEVEL`
- `config/settings.yaml`: account IDs, table names, IAM role names, Athena workgroup

```python
class ConnectorSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    bedrock_model_id: str = Field(default="...")
    connector_port: int = Field(default=8000)
    # YAML values via @property (not overridable via env for safety)
    @property
    def silver_db(self) -> str:
        return _YAML["athena"]["silver_database"]
```

`@lru_cache(maxsize=1)` on `get_settings()` ensures the YAML is parsed once and the same `ConnectorSettings` instance is reused across all modules.

Pydantic also validates API request/response shapes:
```python
class QueryRequest(BaseModel):
    question: str
    persona: Literal["analyst", "admin"] = "analyst"
    max_rows: int = Field(default=20, ge=1, le=1000)

class QueryResponse(BaseModel):
    request_id: str
    compiled_sql: str
    rows: list[dict[str, Any]]
    row_count: int
    duration_ms: int
```

---

### boto3 (AWS SDK for Python)

**What it is:** The official AWS SDK. Every AWS service call in the connector goes through boto3.

**How it's used across planes:**

| Module | boto3 client | Operation |
|--------|-------------|-----------|
| `identity.py` | `sts` | `assume_role` → persona session |
| `engines/athena.py` | `athena` | `start_query_execution`, `get_query_execution`, `get_query_results` (paginator) |
| `compiler.py` | `bedrock-runtime` | `invoke_model` (Bedrock Messages API) |
| `audit.py` | `dynamodb` | `put_item` |
| `metadata.py` | (via AthenaEngine) | Athena DESCRIBE queries |
| `ontology.py` | (via AthenaEngine) | Athena SELECT from semantic tables |

**Session vs client:**
- The connector-runtime uses `boto3.Session(region_name=...)` — inherits IAM role from EC2/ECS instance profile or environment credentials
- Persona queries use a **derived session** from STS AssumeRole temporary credentials — this is the session passed to `AthenaEngine`
- Audit uses the connector-runtime's default credentials — it always writes to DynamoDB as the connector, not the persona

---

### sqlglot

**What it is:** A pure-Python SQL parser and transpiler that understands 20+ SQL dialects including Trino, Spark, BigQuery, and standard SQL. It builds a full AST (Abstract Syntax Tree) from SQL text.

**How it's used in SQLVerifier:**

```python
import sqlglot
import sqlglot.expressions as exp

# 1. Parse to AST — fails on syntactically invalid SQL
parsed = sqlglot.parse_one(sql, dialect="trino")

# 2. Inspect AST node type
if not isinstance(parsed, exp.Select):
    raise CompilerError("Not a SELECT")

# 3. Walk AST to find all table references
for table in parsed.find_all(exp.Table):
    if table.name.lower() not in self._allowed_tables:
        raise CompilerError(f"Table not in allowlist: {table.name}")

# 4. Check for LIMIT node
needs_limit = not parsed.find(exp.Limit)

# 5. Regenerate SQL with correct dialect quoting
sql = parsed.sql(dialect="trino")
# 'order' (reserved word) → "order" (double-quoted) automatically
```

**Why sqlglot instead of regex:**
- Regex on SQL text is bypassed by encoding tricks, comments, whitespace variants
- AST parsing cannot be fooled — `SELECT * FROM order; DROP TABLE supplier` is two statements; `parse_one` returns only the first and the second statement is simply never seen or executed
- `parsed.sql(dialect="trino")` regenerates canonical SQL — LLM formatting quirks, odd spacing, mixed case are all normalized before execution
- Reserved word quoting is automatic — `order` (a SQL reserved word) becomes `"order"` without fragile manual regex

---

### Amazon Bedrock + Claude Haiku

**What it is:** AWS's managed LLM service. The connector uses it to call **Claude Haiku** (`us.anthropic.claude-haiku-4-5-20251001-v1:0`) for NL→SQL compilation.

**How the prompt is structured:**

```
System prompt (constant):
  "You are a SQL query generator for YumBurger restaurant analytics.
   Generate ONLY a single SELECT query. No explanations, no markdown.
   Rules: use only provided tables/columns, no DDL/DML,
          always use table aliases, LIMIT 1000 max,
          use LOWER() for string comparisons."

User message (per-request):
  Schema context (table -> columns):
  {
    "supplier": [{"col_name": "supplier_id", "data_type": "varchar"}, ...],
    "menu_item": [...],
    ...
  }

  Ontology hints (natural language -> table/column mappings):
  [
    {"nl_term": "active supplier", "table_name": "supplier", "column_name": "active"},
    {"nl_term": "loyalty tier", "table_name": "customer", "column_name": "tier"},
    ...
  ]

  Question: How many active suppliers do we have?

  Generate a single SELECT SQL query to answer this question.
  Database: yumburger_silver
  Return ONLY the SQL query, nothing else.
```

**Why Haiku:** Fast and cheap for structured output tasks like SQL generation. The schema context + ontology hints constrain the output space significantly, so the model doesn't need to reason extensively — just pattern-match from hints to SQL.

---

### Apache Iceberg (via Athena Engine v3)

**What it is:** An open table format for large analytic datasets on object storage. Iceberg provides ACID transactions, schema evolution, time travel (snapshots), and partition evolution on top of S3 Parquet files.

**How the connector sees Iceberg:**
- Never reads S3 directly (the connector-runtime role has an explicit **Deny** on `s3:GetObject` for silver paths)
- Athena Engine v3 understands Iceberg natively — `SELECT` on `yumburger_silver.supplier` resolves to current snapshot
- Snapshot queries: `SELECT * FROM "yumburger_silver"."supplier$snapshots"` — Iceberg metadata table suffix
- Lake Formation vends temporary S3 credentials to Athena — the connector never touches S3

**Iceberg tables in silver zone:**
| Table | Rows | Partition |
|-------|------|-----------|
| `supplier` | 50 | none |
| `menu_item` | 30 | none |
| `customer` | 500 | none |
| `order` | 2,000 | `month(order_ts)` |
| `order_line` | 5,048 | none |

---

## 5. Step-by-Step Query Flow: `POST /query`

Here is the complete trace for the question: **"How many active suppliers do we have?"** with `persona = "analyst"`.

```
Client (Streamlit app.py)
│
│  POST http://localhost:8000/query
│  { "question": "How many active suppliers do we have?",
│    "persona": "analyst", "max_rows": 20 }
│
└─► connector/main.py  query()
    │
    │  request_id = uuid4()          # e.g. "a3f7-..."
    │  start = time.monotonic()
    │
    ├─► STEP 1: Get schema context
    │   connector/metadata.py  MetadataPlane.get_schema_summary()
    │   │
    │   │  For each of [supplier, menu_item, customer, order, order_line]:
    │   │    AthenaEngine.execute("DESCRIBE yumburger_silver.<table>")
    │   │      → Athena start_query_execution (connector-runtime role)
    │   │      → poll until SUCCEEDED (~1-2s each)
    │   │      → fetch results (col_name, data_type rows)
    │   │
    │   └─► schema_context = {
    │         "supplier": [{"col_name":"supplier_id",...}, {"col_name":"active",...}],
    │         "customer": [...],
    │         ...
    │       }
    │
    ├─► STEP 2: Get ontology hints
    │   connector/ontology.py  OntologyPlane.get_all_mappings()
    │   │
    │   │  AthenaEngine.execute(
    │   │    "SELECT * FROM ontology_mapping ORDER BY nl_term",
    │   │    database="yumburger_semantic"
    │   │  )
    │   │
    │   └─► ontology_hints = [
    │         {"nl_term": "active supplier", "table_name": "supplier",
    │          "column_name": "active", ...},
    │         ... 74 mappings total
    │       ]
    │
    ├─► STEP 3: Compile NL → SQL
    │   connector/compiler.py  NLToSQLCompiler.compile()
    │   │
    │   ├─► _build_prompt()
    │   │   Assembles system prompt + schema JSON + ontology hints + question
    │   │
    │   ├─► _call_bedrock()
    │   │   boto3 bedrock-runtime.invoke_model(
    │   │     modelId="us.anthropic.claude-haiku-4-5-20251001-v1:0",
    │   │     body={"messages": [{"role":"user","content": prompt}], ...}
    │   │   )
    │   │   → raw_sql = "SELECT COUNT(*) AS active_count FROM supplier WHERE active = true"
    │   │                             ^^^ LLM output — NOT yet executed
    │   │
    │   ├─► Strip markdown (```sql ... ```)  → clean SQL string
    │   │
    │   └─► SQLVerifier.verify(raw_sql)
    │       │
    │       ├─► Check 1: No forbidden keywords  PASS
    │       ├─► Check 2: sqlglot.parse_one()    PASS → AST
    │       ├─► Check 3: isinstance(exp.Select) PASS
    │       ├─► Check 4: table "supplier" in allowlist  PASS
    │       ├─► needs_limit = True (no LIMIT node found)
    │       ├─► sql = parsed.sql(dialect="trino")
    │       │         → 'SELECT COUNT(*) AS active_count FROM supplier WHERE active = TRUE'
    │       └─► sql += " LIMIT 1000"
    │           → compiled_sql = 'SELECT COUNT(*) AS active_count FROM supplier
    │                             WHERE active = TRUE LIMIT 1000'
    │
    ├─► STEP 4: Extract tables accessed (for audit)
    │   sqlglot.parse_one(compiled_sql).find_all(exp.Table)
    │   → tables_accessed = ["supplier"]
    │
    ├─► STEP 5: Pre-audit
    │   connector/audit.py  AuditPlane.pre_audit()
    │   │
    │   │  DynamoDB put_item({
    │   │    request_id: "a3f7-...",
    │   │    event_type: "PRE_QUERY",
    │   │    persona: "analyst",
    │   │    question_hash: sha256("How many active...")[:16],
    │   │    query_hash: sha256(compiled_sql)[:16],
    │   │    tables: ["supplier"],
    │   │    ttl: now + 90 days
    │   │  })
    │   │  (uses connector-runtime credentials — not persona)
    │   │
    │   └─► Fire-and-forget — failure does not block execution
    │
    ├─► STEP 6: Assume persona role
    │   connector/identity.py  assume_persona_role("analyst")
    │   │
    │   │  boto3 sts.assume_role(
    │   │    RoleArn="arn:aws:iam::442042510197:role/yumBurger-analyst-persona",
    │   │    RoleSessionName="yumBurger-connector-analyst",
    │   │    DurationSeconds=900
    │   │  )
    │   │
    │   └─► persona_session = boto3.Session(
    │         aws_access_key_id=temp_key,
    │         aws_secret_access_key=temp_secret,
    │         aws_session_token=temp_token,
    │       )
    │
    ├─► STEP 7: Execute verified SQL via Athena
    │   connector/engines/athena.py  AthenaEngine.execute(compiled_sql)
    │   │  (using persona_session — Lake Formation sees analyst persona)
    │   │
    │   ├─► athena.start_query_execution(
    │   │     QueryString=compiled_sql,
    │   │     WorkGroup="yumBurger-workgroup",
    │   │     QueryExecutionContext={"Database": "yumburger_silver"},
    │   │     ResultConfiguration={"OutputLocation": "s3://yumBurger-athena-results/..."}
    │   │   )
    │   │   → execution_id = "7b9c-..."
    │   │
    │   ├─► Lake Formation vends temporary S3 credentials to Athena
    │   │   (the analyst role has LF SELECT grant on supplier table)
    │   │   Athena reads Parquet files from S3 silver zone
    │   │
    │   ├─► _poll(execution_id, timeout=120s)
    │   │   Loop: get_query_execution() every 1 second
    │   │   State: RUNNING → RUNNING → SUCCEEDED
    │   │
    │   └─► _fetch_results(execution_id)
    │       paginator.paginate("get_query_results")
    │       First row = column headers: ["active_count"]
    │       Data rows:  [{"VarCharValue": "47"}]
    │       → rows = [{"active_count": "47"}]
    │
    ├─► STEP 8: Post-audit
    │   AuditPlane.post_audit(
    │     request_id, persona="analyst", row_count=1,
    │     execution_id="7b9c-...", duration_ms=3240, success=True
    │   )
    │   → DynamoDB put_item with event_type="POST_QUERY"
    │
    └─► STEP 9: Return response
        QueryResponse(
          request_id  = "a3f7-...",
          question    = "How many active suppliers do we have?",
          persona     = "analyst",
          compiled_sql= 'SELECT COUNT(*) AS active_count FROM supplier
                         WHERE active = TRUE LIMIT 1000',
          rows        = [{"active_count": "47"}],
          row_count   = 1,
          duration_ms = 3240
        )
        HTTP 200
```

---

## 6. Security Model

### Defense in depth — four layers

```
Layer 1: LLM instruction   System prompt forbids DDL/DML
         (advisory only — not a security boundary)

Layer 2: SQLVerifier       AST parse + forbidden keyword scan
         (hard block — CompilerError → HTTP 422, never reaches Athena)

Layer 3: Identity          STS AssumeRole → persona credentials
         (analyst role cannot do DDL regardless of SQL)

Layer 4: Lake Formation    Column/row-level policies enforced at Athena
         (analyst cannot see certain columns even if SQL requests them)
```

### S3 isolation

The connector-runtime IAM role has an explicit **Deny** on `s3:GetObject` for the silver bucket path. This means:
- Even if the verifier had a bug and allowed a malicious query through, the connector cannot read raw Parquet files
- Athena reads S3 on behalf of the caller using **LF-vended temporary credentials** — the persona role, not the connector

### Audit integrity

Every query generates two DynamoDB records (PRE + POST). The question text is hashed — raw questions are never persisted. TTL ensures records auto-expire after 90 days.

### SQL injection in question text

The question text goes to Bedrock as a user prompt, not to Athena. Even if a user submits:
```
"Show customers; DROP TABLE customer; --"
```
The LLM ignores the injection attempt and generates a plain SELECT. If by any chance the LLM were to generate DDL, the SQLVerifier catches it at Check 1 (keyword scan) or Check 3 (non-SELECT AST node). The verifier is a hard boundary.

---

## 7. Configuration

### File layout

```
.env                      # secret/env-specific values (not committed)
config/settings.yaml      # project-wide static config (committed)
```

### `.env` keys

```ini
BEDROCK_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0
AWS_REGION=us-east-1
AWS_PROFILE=default
CONNECTOR_HOST=0.0.0.0
CONNECTOR_PORT=8000
LOG_LEVEL=INFO
```

### `config/settings.yaml` structure (excerpt)

```yaml
project:
  prefix: yumBurger
  account_id: "442042510197"
  region: us-east-1

athena:
  silver_database: yumburger_silver
  semantic_database: yumburger_semantic
  workgroup: yumBurger-workgroup
  query_timeout_seconds: 120

s3:
  athena_results_bucket: yumburger-athena-results

dynamodb:
  audit_table: yumBurger-audit

iam:
  connector_runtime_role: yumBurger-connector-runtime
  persona_analyst_role: yumBurger-analyst-persona
  persona_admin_role: yumBurger-admin-persona

allowed_query_tables:
  - supplier
  - menu_item
  - customer
  - order
  - order_line
```

### Settings loading order (pydantic-settings priority)

```
1. Environment variables (highest priority)
2. .env file values
3. Field defaults from YAML (lowest priority)
```

YAML values are exposed as `@property` on `ConnectorSettings` — they are **not** overridable via environment variables intentionally, to prevent accidental misconfiguration of table names and role ARNs in production.

---

## 8. API Reference

### `GET /health`
Returns connector status.
```json
{"status": "ok", "checks": {"connector": "ok"}}
```

### `POST /query`
Main NL→SQL endpoint.

Request:
```json
{
  "question": "What are the top 5 most expensive menu items?",
  "persona": "analyst",
  "max_rows": 20
}
```

Response:
```json
{
  "request_id": "a3f7c2b1-...",
  "question": "What are the top 5 most expensive menu items?",
  "persona": "analyst",
  "compiled_sql": "SELECT name, price_usd FROM menu_item ORDER BY price_usd DESC LIMIT 5",
  "rows": [
    {"name": "Truffle Burger Deluxe", "price_usd": "18.99"},
    ...
  ],
  "row_count": 5,
  "duration_ms": 2840
}
```

Error responses:
- `422` — SQLVerifier rejected the generated SQL
- `500` — Athena execution failed

### `GET /metadata/{table}`
Returns Iceberg table schema (from Athena DESCRIBE).
```json
{"table": "supplier", "columns": [{"col_name": "supplier_id", "data_type": "varchar"}, ...]}
```

### `GET /snapshots/{table}`
Returns Iceberg snapshot history.
```json
{"table": "order", "snapshots": [{"snapshot_id": "...", "committed_at": "...", "operation": "append"}]}
```

### `GET /ontology/classes`
Returns all 7 OWL classes from `yumburger_semantic`.

### `GET /ontology/properties`
Returns all 12 OWL properties from `yumburger_semantic`.

### `GET /tables`
Returns the allowed query table list.
```json
{"tables": ["supplier", "menu_item", "customer", "order", "order_line"]}
```

---

## 9. Running the Connector

```bash
# Start the connector (FastAPI + uvicorn on port 8000)
make serve
# or directly:
python -m connector.main

# Start the Streamlit UI (port 8501)
streamlit run app.py

# Run all tests (65 tests, ~3 min)
make golden
# or:
pytest

# Run only unit tests (fast, no AWS needed)
pytest tests/unit tests/security

# Run golden end-to-end tests (requires live connector + AWS)
pytest tests/golden -m live
```

**Startup sequence:**
1. uvicorn starts, calls `lifespan()` context manager
2. `AuditPlane()` — creates DynamoDB client
3. `NLToSQLCompiler()` — creates Bedrock client, `SQLVerifier` with allowlist
4. `MetadataPlane(session)` — ready (lazy — Athena calls happen per-request)
5. `OntologyPlane(session)` — ready (lazy)
6. Server accepts connections at `0.0.0.0:8000`

**OpenAPI docs:** http://localhost:8000/docs (auto-generated by FastAPI)
