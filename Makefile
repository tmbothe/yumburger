# YumBurger — Makefile
# All commands run from project root.
# Requires: Python 3.11+, AWS CLI, CDK v2 installed.

PYTHON     := python
PIP        := pip
CDK        := cdk
PYTEST     := pytest
RUFF       := ruff

.PHONY: setup lint test datagen deploy verify-infra load dq \
        ontology-publish ontology-export sync serve demo golden \
        pause-redshift resume-redshift destroy help

## ── Setup ────────────────────────────────────────────────────────────────────

setup:
	@echo "==> Installing dependencies..."
	$(PIP) install -e ".[dev]"
	@echo "==> Bootstrapping CDK..."
	cd infra && $(CDK) bootstrap
	@echo "==> Setup complete."

## ── Code Quality ─────────────────────────────────────────────────────────────

lint:
	@echo "==> Linting with ruff..."
	$(RUFF) check .
	$(RUFF) format --check .

lint-fix:
	$(RUFF) check --fix .
	$(RUFF) format .

## ── Tests ────────────────────────────────────────────────────────────────────

test:
	@echo "==> Running unit tests..."
	$(PYTEST) tests/unit -v --tb=short

test-integration:
	@echo "==> Running integration tests..."
	$(PYTEST) tests/integration -v --tb=short

test-security:
	@echo "==> Running security tests..."
	$(PYTEST) tests/security -v --tb=short

golden:
	@echo "==> Running golden question set..."
	$(PYTEST) tests/golden -v --tb=short

test-all:
	$(PYTEST) tests/ -v --tb=short --cov=connector --cov=datagen --cov=ontology

## ── Data Generation ──────────────────────────────────────────────────────────

datagen:
	@echo "==> Generating synthetic data (scale=small)..."
	$(PYTHON) -m datagen.cli generate --scale small --output-dir data/raw
	@echo "==> Done. Check data/raw/ for Parquet files."

datagen-verify:
	@echo "==> Verifying generated data..."
	$(PYTHON) -m datagen.cli verify --data-dir data/raw

## ── Infrastructure (CDK) ─────────────────────────────────────────────────────

deploy:
	@echo "==> Deploying all CDK stacks..."
	cd infra && $(CDK) deploy --all --require-approval never

deploy-storage:
	cd infra && $(CDK) deploy StorageStack --require-approval never

deploy-iam:
	cd infra && $(CDK) deploy IAMStack --require-approval never

deploy-lakeformation:
	cd infra && $(CDK) deploy LakeFormationStack --require-approval never

deploy-athena:
	cd infra && $(CDK) deploy AthenaStack --require-approval never

deploy-dynamodb:
	cd infra && $(CDK) deploy DynamoDBStack --require-approval never

deploy-observability:
	cd infra && $(CDK) deploy ObservabilityStack --require-approval never

deploy-budget:
	cd infra && $(CDK) deploy BudgetStack --require-approval never

verify-infra:
	@echo "==> Verifying infrastructure tags and existence..."
	$(PYTHON) scripts/verify_infra.py

diff:
	cd infra && $(CDK) diff --all

## ── Lakehouse ────────────────────────────────────────────────────────────────

load:
	@echo "==> Uploading Parquet files and loading Iceberg tables..."
	$(PYTHON) -m lakehouse.load

dq:
	@echo "==> Running data quality checks..."
	$(PYTHON) scripts/dq_check.py

## ── Ontology ─────────────────────────────────────────────────────────────────

ontology-publish:
	@echo "==> Validating and publishing ontology..."
	$(PYTHON) -m ontology.publisher publish

ontology-export:
	@echo "==> Exporting ontology to JSON-LD and SKOS..."
	$(PYTHON) -m ontology.publisher export --format jsonld --output ontology/export/yumburger.jsonld
	$(PYTHON) -m ontology.publisher export --format skos   --output ontology/export/yumburger.skos.ttl

ontology-validate:
	$(PYTHON) -m ontology.validator validate ontology/yumburger.yaml

## ── Metadata Sync ────────────────────────────────────────────────────────────

sync:
	@echo "==> Syncing metadata + ontology to Redshift..."
	$(PYTHON) scripts/sync_redshift.py

## ── Connector Service ────────────────────────────────────────────────────────

serve:
	@echo "==> Starting YumBurger connector service..."
	$(PYTHON) -m connector.main

## ── Demo & Golden Questions ──────────────────────────────────────────────────

demo:
	@echo "==> Running demo sequence..."
	$(PYTHON) scripts/run_demo.py

## ── Redshift ─────────────────────────────────────────────────────────────────

pause-redshift:
	aws redshift-serverless update-workgroup \
	    --workgroup-name yumBurger-wg \
	    --config-parameters parameterKey=max_query_cpu_time,parameterValue=0 \
	    --region us-east-1
	@echo "Redshift Serverless workgroup pause requested."

resume-redshift:
	@echo "Resume Redshift Serverless workgroup (manual step in console or via API)"

## ── Teardown ─────────────────────────────────────────────────────────────────

destroy:
	@echo "WARNING: This will destroy ALL yumBurger AWS resources."
	@read -p "Type 'destroy-yumburger' to confirm: " confirm && \
	    [ "$$confirm" = "destroy-yumburger" ] || (echo "Aborted." && exit 1)
	cd infra && $(CDK) destroy --all --force

## ── Help ─────────────────────────────────────────────────────────────────────

help:
	@echo "YumBurger Make Targets:"
	@echo "  setup              Install deps + bootstrap CDK"
	@echo "  lint               Ruff check + format"
	@echo "  test               Unit tests"
	@echo "  datagen            Generate synthetic data"
	@echo "  deploy             Deploy all CDK stacks"
	@echo "  verify-infra       Verify resources + tags"
	@echo "  load               Upload + load Iceberg tables"
	@echo "  dq                 Data quality checks"
	@echo "  ontology-publish   Publish ontology to semantic zone"
	@echo "  ontology-export    Export JSON-LD + SKOS"
	@echo "  sync               Sync metadata to Redshift"
	@echo "  serve              Start connector service"
	@echo "  demo               Run demo sequence"
	@echo "  golden             Run golden question set"
	@echo "  pause-redshift     Pause RS workgroup"
	@echo "  destroy            Destroy all AWS resources"
