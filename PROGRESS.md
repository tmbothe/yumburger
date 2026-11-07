# YumBurger — Project Progress

![YumBurger Logo](assets/logo_yumburger.png)

## Current Phase: Phase 3 — AWS Deploy (CDK)

---

## Phase Checklist

### Phase 1: Foundation & Architecture
- [x] Directory structure created
- [x] PROGRESS.md created
- [x] docs/PLAN.md created
- [x] docs/DECISIONS.md created
- [x] pyproject.toml created
- [x] Makefile created
- [x] config/settings.yaml created
- [x] .env.example created
- [ ] CDK bootstrap verified
- [x] Python venv + deps installed (`pip install -e ".[dev]"` — 52 tests pass)

### Phase 2: Data Generation
- [x] datagen/models.py — Pydantic data models
- [x] datagen/dictionary.py — domain vocabulary
- [x] datagen/generator.py — Faker-based generator
- [x] datagen/cli.py — CLI entry point
- [x] `make datagen` runs and produces Parquet files in `data/raw/`
- [x] Verify row counts match DATA_SCALE=small targets (50/30/500/2000/5048 rows)

### Phase 3: Infrastructure (CDK — 7 stacks)
- [ ] infra/app.py — CDK app entry
- [ ] StorageStack — S3 buckets (raw, silver, semantic, audit)
- [ ] IAMStack — roles (connector-runtime, persona-analyst, persona-admin)
- [ ] LakeFormationStack — database + column/row policies
- [ ] AthenaStack — workgroup + result bucket
- [ ] DynamoDBStack — audit log table
- [ ] ObservabilityStack — CloudWatch dashboard + alarms
- [ ] BudgetStack — $50/month budget alert
- [ ] `make deploy` succeeds
- [ ] `make verify-infra` all green

### Phase 4: Lakehouse (Iceberg)
- [ ] lakehouse/ddl/create_databases.sql
- [ ] lakehouse/ddl/supplier.sql
- [ ] lakehouse/ddl/menu_item.sql
- [ ] lakehouse/ddl/customer.sql
- [ ] lakehouse/ddl/order.sql
- [ ] lakehouse/ddl/order_line.sql
- [ ] lakehouse/load.py — upload Parquet + run CTAS/INSERT
- [ ] `make load` succeeds
- [ ] Iceberg snapshots verifiable via Athena

### Phase 5: Ontology
- [ ] ontology/yumburger.yaml — OWL/SKOS classes + properties
- [ ] ontology/validator.py — YAML schema validation
- [ ] ontology/publisher.py — write to yumburger_semantic Iceberg tables
- [ ] `make ontology-publish` succeeds
- [ ] `make ontology-export` produces JSON-LD + SKOS

### Phase 6: Connector (FastAPI + MCP)
- [ ] connector/identity.py — STS AssumeRole
- [ ] connector/metadata.py — Athena DESCRIBE/SHOW
- [ ] connector/ontology.py — query yumburger_semantic
- [ ] connector/compiler.py — NL → SQL compiler
- [ ] connector/engines/athena.py — execute compiled SQL
- [ ] connector/audit.py — DynamoDB audit trail
- [ ] connector/main.py — FastAPI + MCP server
- [ ] `make serve` starts without errors

### Phase 7: Bodhi Simulator & Tests
- [ ] bodhi_sim/agent.py — Bedrock agent simulator
- [ ] tests/unit/* — unit tests for all planes
- [ ] tests/integration/* — end-to-end query tests
- [ ] tests/security/* — deny policy tests
- [ ] tests/golden/* — golden question set
- [ ] `make test` all green
- [ ] `make golden` all pass

### Phase 8: Demo & Runbook
- [ ] docs/RUNBOOK.md complete
- [ ] docs/DEMO.md complete
- [ ] `make demo` runs full sequence
- [ ] Cost verified < $50/month

---

## Verified AWS Capabilities
See `docs/DECISIONS.md`

## Notes
- All changes tracked here before moving to next phase
- Each phase must be verified before proceeding
