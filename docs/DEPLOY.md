# YumBurger — Deployment Runbook

Step-by-step guide to build, deploy, and verify the full YumBurger stack on AWS.

---

## Prerequisites

Before you start, confirm all of the following are installed and configured.

| Tool | Minimum version | Check |
|---|---|---|
| Python | 3.11 | `python --version` |
| AWS CLI | v2 | `aws --version` |
| AWS CDK | v2 | `cdk --version` |
| Docker Desktop | any recent | `docker version` |
| Node.js | 18+ | `node --version` |
| Git | any | `git --version` |

**AWS account requirements**

- An AWS account in `us-east-1` (or update `config/settings.yaml` for another region)
- AWS CLI configured with a profile that has permissions to deploy CDK stacks, create IAM roles, register Lake Formation resources, and invoke Bedrock
- Access granted to the Bedrock model in your account (`us.anthropic.claude-haiku-4-5-20251001-v1:0` or the model of your choice)

---

## Step 1 — Clone and install

```bash
git clone https://github.com/tmbothe/yumburger.git
cd yumburger

# Install Python project and all dependencies (including dev tools)
pip install -e ".[dev]"
```

Verify:

```bash
python -c "import connector; print('OK')"
```

---

## Step 2 — Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set your values:

```dotenv
BEDROCK_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0
AWS_REGION=us-east-1
AWS_PROFILE=default
CONNECTOR_HOST=0.0.0.0
CONNECTOR_PORT=8000
LOG_LEVEL=INFO
```

If you are using a named AWS profile other than `default`, update `AWS_PROFILE` to match.

Verify your AWS credentials resolve:

```bash
aws sts get-caller-identity
```

---

## Step 3 — Bootstrap CDK

CDK bootstrap provisions the S3 staging bucket and ECR repository that CDK needs to deploy assets. Run this once per account/region.

```bash
cd infra
cdk bootstrap aws://442042510197/us-east-1
cd ..
```

Replace `442042510197` with your own AWS account ID if different.

---

## Step 4 — Deploy infrastructure stacks

Deploy all eight CDK stacks in dependency order:

```bash
cd infra
cdk deploy --all --require-approval never
cd ..
```

Or use the Make shortcut:

```bash
make deploy
```

**What gets deployed:**

| Stack | Resources created |
|---|---|
| `StorageStack` | S3 buckets: silver, semantic, Athena results, audit logs |
| `IAMStack` | Connector runtime role, analyst and admin persona roles |
| `LakeFormationStack` | LF registrations and table/column permissions |
| `AthenaStack` | Athena workgroup `yumBurger-wg` and result location |
| `DynamoDBStack` | Audit events table with 90-day TTL |
| `ObservabilityStack` | CloudWatch dashboards and alarms |
| `BudgetStack` | $50/month AWS Budget alert |
| `ServiceStack` | ECR repos, ECS Fargate cluster, ALB (ports 80 and 8501) |

After deployment, capture the ALB DNS name from the CDK output:

```
Outputs:
ServiceStack.ConnectorURL = http://<alb-dns-name>
```

---

## Step 5 — Generate synthetic data

```bash
make datagen
```

This generates CSV files under `data/` using Faker:

| Table | Rows |
|---|---|
| supplier | 50 |
| menu_item | 30 |
| customer | 500 |
| order | 2,000 |
| order_line | ~5,048 |

---

## Step 6 — Load Iceberg tables

Upload the CSV files to S3 and load them into Athena/Iceberg:

```bash
make load
```

This runs `lakehouse/load.py` which:
1. Creates Iceberg DDL tables in `yumburger_silver` via Athena if they don't exist
2. Uploads CSV files to `s3://yumburger-silver-<account>/silver/`
3. Runs `INSERT INTO ... SELECT` from staging to Iceberg

Verify row counts:

```bash
aws athena start-query-execution \
  --query-string "SELECT COUNT(*) FROM yumburger_silver.customer" \
  --work-group yumBurger-wg \
  --query-execution-context Database=yumburger_silver \
  --result-configuration OutputLocation=s3://yumburger-athena-results-<account>/verify/
```

---

## Step 7 — Publish ontology

Load OWL/SKOS semantic mappings into the `yumburger_semantic` Iceberg tables:

```bash
make ontology-publish
```

This validates `ontology/ontology.yaml` and inserts rows into:
- `ontology_class` (7 rows)
- `ontology_property` (12 rows)
- `ontology_mapping` (74 rows)

---

## Step 8 — Build and push Docker images

### 8a — Authenticate Docker to ECR

```bash
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS \
  --password-stdin 442042510197.dkr.ecr.us-east-1.amazonaws.com
```

### 8b — Build and push the connector (FastAPI) image

```bash
docker build -t yumburger-connector:latest -f Dockerfile .

docker tag yumburger-connector:latest \
  442042510197.dkr.ecr.us-east-1.amazonaws.com/yumburger-connector:latest

docker push \
  442042510197.dkr.ecr.us-east-1.amazonaws.com/yumburger-connector:latest
```

### 8c — Build and push the Streamlit image

```bash
docker build -t yumburger-streamlit:latest -f Dockerfile.streamlit .

docker tag yumburger-streamlit:latest \
  442042510197.dkr.ecr.us-east-1.amazonaws.com/yumburger-streamlit:latest

docker push \
  442042510197.dkr.ecr.us-east-1.amazonaws.com/yumburger-streamlit:latest
```

> The ECR repository names (`yumburger-connector` and `yumburger-streamlit`) are created by `ServiceStack`. Run `cdk deploy ServiceStack` first if you skipped the full deploy.

---

## Step 9 — Force ECS service update

After pushing new images, force ECS to pull the latest tag:

```bash
# Connector service
aws ecs update-service \
  --cluster yumburger-connector \
  --service yumburger-connector \
  --force-new-deployment \
  --region us-east-1

# Streamlit service
aws ecs update-service \
  --cluster yumburger-connector \
  --service yumburger-streamlit \
  --force-new-deployment \
  --region us-east-1
```

Watch the deployment stabilise:

```bash
aws ecs wait services-stable \
  --cluster yumburger-connector \
  --services yumburger-connector yumburger-streamlit \
  --region us-east-1
```

This typically takes 2–3 minutes.

---

## Step 10 — Verify deployment

### Health check

```bash
# Replace <alb-dns> with the value from the CDK output
curl http://<alb-dns>/health
```

Expected response:

```json
{"status": "ok"}
```

### Ask a question

```bash
curl -X POST http://<alb-dns>/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Who are the top 5 customers by revenue?", "persona": "analyst"}'
```

### Streamlit UI

Open a browser and navigate to:

```
http://<alb-dns>:8501
```

### Run golden-question tests against the live deployment

```bash
CONNECTOR_URL=http://<alb-dns> pytest tests/golden -m live -v
```

---

## Step 11 — Run the Bodhi sync (optional)

Export schema metadata and ontology to S3 as Bodhi-ready JSON:

```bash
# Incremental (only changed data)
make sync-bodhi

# Dry run — see what would change without writing
make sync-bodhi-dry

# Force full re-export
make sync-bodhi-force
```

Output lands in:

```
s3://yumburger-athena-results-<account>/bodhi-sync/
  manifest.json
  metadata/schema_latest.json
  ontology/ontology_latest.json
```

---

## Redeployment — updating the application

When you change connector or UI code, only Steps 8 and 9 are needed:

```bash
# 1. Rebuild and push images
docker build -t yumburger-connector:latest -f Dockerfile . && \
  docker tag yumburger-connector:latest \
    442042510197.dkr.ecr.us-east-1.amazonaws.com/yumburger-connector:latest && \
  docker push 442042510197.dkr.ecr.us-east-1.amazonaws.com/yumburger-connector:latest

# 2. Force ECS to pick up the new image
aws ecs update-service \
  --cluster yumburger-connector \
  --service yumburger-connector \
  --force-new-deployment \
  --region us-east-1
```

When you change infrastructure (CDK stacks):

```bash
cd infra && cdk deploy --all && cd ..
```

---

## Teardown

To destroy all AWS resources and avoid ongoing charges:

```bash
make destroy
```

This runs `cdk destroy --all` after a confirmation prompt. S3 buckets with data are set to `RETAIN` by default — delete them manually from the AWS console if needed.

---

## Troubleshooting

### ECS task fails to start

Check CloudWatch logs:

```bash
aws logs tail /ecs/yumburger-connector --follow --region us-east-1
```

Common causes:
- ECR image not pushed yet — run Steps 8 and 9
- Missing environment variable — check task definition in ECS console
- `lakeformation:GetDataAccess` denied — confirm the connector runtime role has this permission

### Athena query fails with `PERMISSION_DENIED`

The connector runtime role or persona role is missing a Lake Formation grant. Grant permissions:

```bash
aws lakeformation grant-permissions \
  --principal DataLakePrincipalIdentifier=arn:aws:iam::442042510197:role/yumBurger-connector-runtime \
  --permissions SELECT \
  --resource '{"Table": {"DatabaseName": "yumburger_silver", "TableWildcard": {}}}' \
  --region us-east-1
```

### Docker build fails on Windows

Ensure Docker Desktop is running and Linux containers are selected (not Windows containers).

### CDK bootstrap error — already bootstrapped

Safe to ignore. CDK bootstrap is idempotent.

### ALB returns 404 on `/`

The connector does not expose a root route. Use `/health` to confirm the service is running. The Swagger UI is at `/docs`.

---

## Quick reference

```bash
make setup            # install deps + bootstrap CDK
make deploy           # deploy all CDK stacks
make datagen          # generate synthetic data
make load             # load Iceberg tables
make ontology-publish # publish semantic mappings
make serve            # run FastAPI locally (port 8000)
make golden           # run golden-question tests
make sync-bodhi       # incremental Bodhi metadata sync
make destroy          # tear down all AWS resources
```

---

*YumBurger Analytics · AWS Lakehouse POC · us-east-1*
