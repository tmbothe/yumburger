<div align="center">
  <img src="assets/logo_yumburger.png" width="120" alt="YumBurger Logo" />

  # YumBurger Analytics
  ### Federated Semantic Connector · Governed NL→SQL · Apache Iceberg Data Lake

  [![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)](https://python.org)
  [![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
  [![Apache Iceberg](https://img.shields.io/badge/Apache%20Iceberg-v2-orange)](https://iceberg.apache.org)
  [![AWS CDK](https://img.shields.io/badge/AWS%20CDK-v2-FF9900?logo=amazonaws&logoColor=white)](https://aws.amazon.com/cdk)
  [![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)

  > **Ask any business question. Get a governed, audited, accurate answer.**

  [Live Demo](#live-demo) · [Architecture](#architecture) · [Quick Start](#quick-start) · [API Reference](#api-reference) · [Data Model](#data-model)
</div>

---

## What Is This?

**YumBurger Analytics** is a proof-of-concept for a modern, AI-powered data platform built for a fast-food restaurant chain modelled after McDonald's. It demonstrates how a business analyst — with no SQL knowledge — can ask questions like _"Who are our top customers this month?"_ or _"Which menu items contain gluten?"_ and receive accurate, real-time answers drawn directly from a governed data lake.

The project covers the **full data engineering stack**, end-to-end:

- **Synthetic data generation** — 7,600+ realistic rows across 5 business entities (suppliers, menu items, customers, orders, order lines)
- **Apache Iceberg data lake** — ACID-compliant table format on Amazon S3, queryable exclusively through Amazon Athena
- **Semantic ontology** — OWL/SKOS knowledge graph with 74 natural-language-to-SQL term mappings, enabling the AI to understand business intent
- **Governed NL→SQL pipeline** — Natural language questions compiled to SQL by Amazon Bedrock (Claude Haiku), verified by an AST safety engine, then executed as a persona-scoped IAM role under Lake Formation column and row-level policies
- **Audit trail** — Every query is pre- and post-audited in DynamoDB with hashed question text and 90-day TTL
- **REST API + Streamlit UI** — A FastAPI connector service and Streamlit analytics dashboard, deployed on AWS ECS Fargate with a public ALB endpoint

> **Key invariant:** LLM-generated SQL is **never** executed directly. Only AST-verified, allowlist-checked SQL reaches Athena.

---

## Overview

YumBurger Analytics is a production-grade **Federated Semantic Connector** that translates plain-English business questions into governed SQL queries against an Apache Iceberg data lake on AWS. Every query is compiler-verified, persona-scoped, and audit-logged.

```
"Who are our top customers by revenue?"
                    |
                    v
         NL → Bedrock LLM → SQL AST Verification
                    |
                    v
         STS AssumeRole → Athena Engine v3
                    |
         Lake Formation (column/row policies)
                    |
                    v
         Apache Iceberg Silver Zone (S3)
                    |
                    v
         "Jeffrey Anderson | Silver | $250.74"
```

**Key invariant:** LLM-generated SQL is **never** executed. Only AST-verified SQL that passes all safety checks reaches Athena.

---

## Architecture

<div align="center">
  <img src="assets/architecture.png" width="900" alt="YumBurger Architecture Diagram" />
</div>

### Five Connector Planes

| Plane | Module | Responsibility |
|-------|--------|---------------|
| **Identity** | `connector/identity.py` | STS `AssumeRole` → 15-min persona credentials |
| **Metadata** | `connector/metadata.py` | Athena `DESCRIBE` → schema context for LLM |
| **Semantic** | `connector/ontology.py` | OWL ontology → 74 NL-term mappings |
| **Query** | `connector/compiler.py` + `engines/athena.py` | Bedrock → SQLVerifier → Athena execution |
| **Audit** | `connector/audit.py` | DynamoDB PRE/POST events, hashed questions, 90-day TTL |

### AWS Services

| Service | Role |
|---------|------|
| **Amazon Bedrock** | Claude Haiku for NL→SQL compilation |
| **Amazon Athena** | Engine v3, Trino dialect, single data access layer |
| **Apache Iceberg** | ACID table format on S3 (silver zone) |
| **AWS Lake Formation** | Column-level and row-level access control |
| **AWS STS** | Persona role assumption per query |
| **Amazon DynamoDB** | Tamper-evident audit trail |
| **AWS ECS Fargate** | Containerised connector + Streamlit UI |
| **Application Load Balancer** | Public HTTPS endpoint |

---

## Data Model

<div align="center">
  <img src="assets/er_diagram.png" width="900" alt="YumBurger ER Diagram" />
</div>

### Silver Zone Tables (`yumburger_silver`)

| Table | Rows | Description |
|-------|------|-------------|
| `supplier` | 50 | Ingredient and goods suppliers |
| `menu_item` | 30 | Menu items with pricing and allergens |
| `customer` | 500 | Loyalty members with tier and lifetime spend |
| `order` | 2,000 | Transactions partitioned by `month(order_ts)` |
| `order_line` | 5,048 | Line items linking orders to menu items |

### Semantic Zone (`yumburger_semantic`)

| Table | Rows | Description |
|-------|------|-------------|
| `ontology_class` | 7 | OWL classes mapped to silver tables |
| `ontology_property` | 12 | OWL properties mapped to columns |
| `ontology_mapping` | 74 | NL-term → table/column hint mappings |

---

## Quick Start

### Prerequisites

- Python 3.11+
- AWS CLI configured (`aws configure`)
- Docker Desktop
- AWS CDK v2 (`npm install -g aws-cdk`)

### Local Development

```bash
# 1. Clone and install
git clone https://github.com/your-org/yumburger.git
cd yumburger
pip install -e .

# 2. Configure environment
cp .env.example .env
# Edit .env — set BEDROCK_MODEL_ID

# 3. Deploy AWS infrastructure
cd infra && cdk deploy --all

# 4. Generate and load synthetic data
make datagen
make load

# 5. Publish ontology
make ontology-publish

# 6. Start the connector
make serve          # FastAPI on :8000

# 7. Start the UI (new terminal)
python -m streamlit run app.py   # Streamlit on :8501
```

### Environment Variables (`.env`)

```ini
BEDROCK_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0
AWS_REGION=us-east-1
AWS_PROFILE=default
CONNECTOR_HOST=0.0.0.0
CONNECTOR_PORT=8000
LOG_LEVEL=INFO
```

---

## Live Demo

The connector and UI are deployed on AWS ECS Fargate:

| Service | URL |
|---------|-----|
| **Streamlit UI** | `http://yumburger-connector-416434018.us-east-1.elb.amazonaws.com:8501` |
| **REST API** | `http://yumburger-connector-416434018.us-east-1.elb.amazonaws.com` |
| **API Docs** | `http://yumburger-connector-416434018.us-east-1.elb.amazonaws.com/docs` |

**Try it now:**
```bash
curl -X POST http://yumburger-connector-416434018.us-east-1.elb.amazonaws.com/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Who are the top 5 customers by revenue?", "persona": "analyst"}'
```

---

## API Reference

### `POST /ask` — Natural Language Answer _(Recommended)_

Single-call endpoint. Returns a natural language answer, not raw rows. Ideal for Bedrock Agents / Bodhi.

```json
// Request
{
  "question": "What are the top 5 most expensive menu items?",
  "persona": "analyst",
  "max_rows": 20
}

// Response
{
  "request_id": "a3f7c2b1-...",
  "answer": "The top 5 most expensive items are the Truffle Burger Deluxe ($18.99), ...",
  "compiled_sql": "SELECT name, price_usd FROM menu_item ORDER BY price_usd DESC LIMIT 5",
  "row_count": 5,
  "duration_ms": 4820
}
```

### `POST /query` — Raw SQL + Rows

Returns compiled SQL and structured row data. Used by the Streamlit UI.

### Other Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/tables` | List queryable tables |
| `GET` | `/metadata/{table}` | Iceberg table schema |
| `GET` | `/snapshots/{table}` | Iceberg snapshot history |
| `GET` | `/ontology/classes` | OWL class definitions |
| `GET` | `/ontology/properties` | OWL property definitions |
| `GET` | `/docs` | Swagger UI |

---

## Security Model

```
Layer 1: LLM instruction   System prompt forbids DDL/DML  (advisory)
Layer 2: SQLVerifier       Keyword scan + AST parse + SELECT-only + table allowlist (hard block)
Layer 3: Identity          STS AssumeRole → persona credentials expire in 15 min
Layer 4: Lake Formation    Column/row policies enforced at Athena execution layer
```

The connector-runtime IAM role has an **explicit Deny** on `s3:GetObject` for the silver bucket path — data is never accessible except through Athena + Lake Formation.

---

## Project Structure

```
yumburger/
├── connector/              # FastAPI service (5 planes)
│   ├── main.py             # API endpoints + startup cache warm-up
│   ├── compiler.py         # NLToSQLCompiler + SQLVerifier
│   ├── identity.py         # STS AssumeRole
│   ├── metadata.py         # Athena DESCRIBE plane
│   ├── ontology.py         # Semantic ontology plane
│   ├── audit.py            # DynamoDB audit trail
│   ├── engines/athena.py   # Athena query execution
│   ├── models.py           # Pydantic request/response models
│   └── settings.py         # pydantic-settings + YAML config
├── infra/                  # AWS CDK v2 (8 stacks)
│   └── stacks/
│       ├── storage_stack.py
│       ├── iam_stack.py
│       ├── lakeformation_stack.py
│       ├── athena_stack.py
│       ├── dynamodb_stack.py
│       ├── observability_stack.py
│       ├── budget_stack.py
│       └── service_stack.py    # ECS Fargate + ALB
├── lakehouse/              # Iceberg DDL + load scripts
├── ontology/               # OWL YAML + publisher
├── datagen/                # Synthetic data generator
├── bodhi_sim/              # Bedrock agent simulator
├── tests/                  # unit | security | golden (65 tests)
├── app.py                  # Streamlit UI
├── Dockerfile              # Connector image
├── Dockerfile.streamlit    # Streamlit image
└── assets/                 # Logo + diagrams
```

---

## Infrastructure (CDK Stacks)

| Stack | Resources |
|-------|-----------|
| `StorageStack` | S3 buckets: silver, semantic, athena-results, audit-logs |
| `IAMStack` | connector-runtime role, analyst persona, admin persona |
| `LakeFormationStack` | LF registrations + column/row grants |
| `AthenaStack` | Workgroup + result configuration |
| `DynamoDBStack` | Audit table with TTL |
| `ObservabilityStack` | CloudWatch dashboards + alarms |
| `BudgetStack` | $50/month budget alert |
| `ServiceStack` | ECR repos + ECS cluster + Fargate services + ALB |

```bash
# Deploy everything
cd infra && cdk deploy --all

# Deploy only the connector service
cdk deploy ServiceStack
```

---

## Make Targets

```bash
make setup              # Install deps, bootstrap CDK
make lint               # ruff check + format
make test               # pytest (65 tests, ~3 min)
make datagen            # Generate synthetic data
make deploy             # CDK deploy all stacks
make load               # Upload + load Iceberg tables
make ontology-publish   # Validate + publish ontology
make serve              # Start connector :8000
make golden             # Run golden question tests
make destroy            # Tear down all AWS resources
```

---

## Testing

```bash
# All 65 tests
pytest

# Unit only (no AWS required)
pytest tests/unit tests/security

# Golden questions (requires live connector)
pytest tests/golden -m live

# Example golden questions validated:
# G001: How many active suppliers do we have?
# G002: What are the top 5 most expensive menu items?
# G005: What is the total revenue by region?
# G008: Show me the top 10 customers by lifetime spend
# G010: Which menu items contain gluten?
```

---

## Cost Estimate

Deployed on AWS us-east-1, estimated at **< $20/month** for POC traffic:

| Resource | Est. Cost/Month |
|----------|-----------------|
| ECS Fargate (connector + UI) | ~$10–15 |
| Amazon Athena ($5/TB, tiny data) | ~$1–2 |
| Amazon Bedrock Haiku | ~$1–3 |
| ALB + ECR + DynamoDB + S3 | ~$2 |
| **Total** | **~$14–22** |

---

## Tech Stack

| Category | Technology |
|----------|-----------|
| Language | Python 3.11 |
| API Framework | FastAPI + Uvicorn |
| UI | Streamlit 1.59 |
| Data Format | Apache Iceberg v2 + Apache Parquet |
| Query Engine | Amazon Athena Engine v3 (Trino dialect) |
| LLM | Amazon Bedrock — Claude Haiku |
| SQL Parsing | sqlglot |
| Config | pydantic-settings v2 |
| IaC | AWS CDK v2 (Python) |
| Containers | Docker + Amazon ECS Fargate |
| Ontology | OWL / SKOS via rdflib |
| Testing | pytest + moto |
| Linting | ruff |

---

## License

MIT — see [LICENSE](LICENSE)

---

<div align="center">
  <sub>Built with passion for data engineering · YumBurger Analytics POC · 2026</sub>
</div>
