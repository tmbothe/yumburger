# YumBurger — Operations Runbook (Deploy & Destroy)

Concise, copy-paste-ready guide for standing the stack up and tearing it down.
See `DEPLOY.md` for the full first-time setup walkthrough.

---

## Deploy

### Full deploy (first time or after destroy)

```bash
# 1. Install dependencies
pip install -e ".[dev]"

# 2. Bootstrap CDK (only needed once per account/region)
cd infra && cdk bootstrap aws://442042510197/us-east-1 && cd ..

# 3. Deploy all 8 stacks
cd infra && cdk deploy --all --require-approval never && cd ..

# 4. Generate and load data
python datagen/generator.py          # writes CSV files to data/
python lakehouse/load.py             # creates Iceberg tables + loads rows

# 5. Publish ontology
python ontology/publisher.py

# 6. Start connector locally
uvicorn connector.main:app --host 0.0.0.0 --port 8000
```

### Deploy a single stack (e.g. after changing DynamoDB)

```bash
cd infra && cdk deploy DynamoDBStack --require-approval never && cd ..
```

### Stacks and what they create

| Stack | Key resources |
|---|---|
| `StorageStack` | S3 buckets: silver, semantic, Athena results, audit logs |
| `IAMStack` | Connector runtime role, analyst + admin persona roles |
| `LakeFormationStack` | LF registrations + table/column permissions |
| `AthenaStack` | Athena workgroup `yumBurger-wg` |
| `DynamoDBStack` | `yumBurger-audit` (90-day TTL) + `yumBurger-conversation` (30-day TTL) |
| `ObservabilityStack` | CloudWatch dashboards and alarms |
| `BudgetStack` | $50/month budget alert |
| `ServiceStack` | ECR repos, ECS Fargate cluster, ALB |

### Manual grants required after deploy

LakeFormation grants that CDK cannot fully automate (applied once after `cdk deploy`):

```bash
# 1. Register silver + semantic buckets with the custom LF role
aws lakeformation register-resource \
  --resource-arn arn:aws:s3:::yumburger-silver-442042510197 \
  --role-arn arn:aws:iam::442042510197:role/yumBurger-lf-s3-role \
  --region us-east-1

aws lakeformation register-resource \
  --resource-arn arn:aws:s3:::yumburger-semantic-442042510197 \
  --role-arn arn:aws:iam::442042510197:role/yumBurger-lf-s3-role \
  --region us-east-1

# 2. Grant bedrock-user ALL on yumburger_silver
aws lakeformation grant-permissions \
  --principal DataLakePrincipalIdentifier=arn:aws:iam::442042510197:user/bedrock-user \
  --permissions ALL \
  --resource '{"Database": {"Name": "yumburger_silver"}}' \
  --region us-east-1

# 3. Grant bedrock-user ALL on yumburger_semantic
aws lakeformation grant-permissions \
  --principal DataLakePrincipalIdentifier=arn:aws:iam::442042510197:user/bedrock-user \
  --permissions ALL \
  --resource '{"Database": {"Name": "yumburger_semantic"}}' \
  --region us-east-1
```

---

## Destroy

### Standard destroy

```bash
cd infra && cdk destroy --all --force && cd ..
```

> `--force` skips the interactive confirmation prompt.

### Known issues and workarounds

#### 1. LakeFormationStack stuck with DELETE_FAILED

**Symptom:**
```
LakeFormationStack | DELETE_FAILED | AWS::LakeFormation::Permissions | AdminSilverAllTables
  Resource does not exist or requester is not authorized
```

**Cause:** LF permission resources were manually patched outside CDK during setup.
CloudFormation can no longer find them to delete.

**Fix:** Force-delete the stack while retaining the 4 stuck resources:

```bash
aws cloudformation delete-stack \
  --stack-name LakeFormationStack \
  --retain-resources AdminSilverAllTables AnalystSilverAllTables \
                     AnalystSemanticAllTables AdminSemanticAllTables \
  --region us-east-1

aws cloudformation wait stack-delete-complete \
  --stack-name LakeFormationStack \
  --region us-east-1
```

Then re-run `cdk destroy --all --force` — the LF stack will show as already gone
and the remaining stacks will delete cleanly.

#### 2. StorageStack stuck — Athena results bucket not empty

**Symptom:**
```
StorageStack | DELETE_FAILED | AWS::S3::Bucket | AthenaResultsBucket
  The bucket you tried to delete is not empty
```

**Cause:** Athena writes query results to S3; the bucket accumulates files over time.
CDK does not empty buckets before deleting them.

**Fix:**

```bash
# Step 1: Empty the bucket
aws s3 rm s3://yumburger-athena-results-442042510197 --recursive --region us-east-1

# Step 2: Force-delete the StorageStack, retaining the now-empty bucket resource
aws cloudformation delete-stack \
  --stack-name StorageStack \
  --retain-resources AthenaResultsBucket879938FA \
  --region us-east-1

aws cloudformation wait stack-delete-complete \
  --stack-name StorageStack \
  --region us-east-1

# Step 3: Delete the now-empty bucket manually
aws s3 rb s3://yumburger-athena-results-442042510197 --region us-east-1
```

### Full destroy sequence (with all workarounds)

Run this sequence when both issues occur together:

```bash
# 1. Fix LakeFormation stack
aws cloudformation delete-stack \
  --stack-name LakeFormationStack \
  --retain-resources AdminSilverAllTables AnalystSilverAllTables \
                     AnalystSemanticAllTables AdminSemanticAllTables \
  --region us-east-1

aws cloudformation wait stack-delete-complete \
  --stack-name LakeFormationStack --region us-east-1

# 2. Destroy the remaining 7 stacks
cd infra && cdk destroy --all --force && cd ..

# 3. If StorageStack fails on the Athena bucket (see above):
aws s3 rm s3://yumburger-athena-results-442042510197 --recursive --region us-east-1

aws cloudformation delete-stack \
  --stack-name StorageStack \
  --retain-resources AthenaResultsBucket879938FA \
  --region us-east-1

aws cloudformation wait stack-delete-complete \
  --stack-name StorageStack --region us-east-1

aws s3 rb s3://yumburger-athena-results-442042510197 --region us-east-1
```

### Verify everything is gone

```bash
aws cloudformation list-stacks \
  --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE \
  --region us-east-1 \
  --query "StackSummaries[?contains(StackName,'yumBurger') || contains(StackName,'Stack')].StackName"
```

Expected output: `[]`

### What survives destroy (by design)

| Resource | Why retained |
|---|---|
| `yumburger-silver-442042510197` S3 bucket | `RemovalPolicy.RETAIN` — Iceberg data preserved |
| `yumburger-semantic-442042510197` S3 bucket | `RemovalPolicy.RETAIN` — ontology data preserved |
| `yumBurger-audit` DynamoDB table | `RemovalPolicy.RETAIN` — audit log preserved |

The `yumBurger-conversation` memory table uses `RemovalPolicy.DESTROY` — sessions are
ephemeral and not worth preserving across teardowns.

To manually delete retained resources after a destroy:

```bash
# Delete retained S3 buckets (only if you want a full clean slate)
aws s3 rm s3://yumburger-silver-442042510197 --recursive --region us-east-1
aws s3 rb s3://yumburger-silver-442042510197 --region us-east-1

aws s3 rm s3://yumburger-semantic-442042510197 --recursive --region us-east-1
aws s3 rb s3://yumburger-semantic-442042510197 --region us-east-1

# Delete retained audit DynamoDB table
aws dynamodb delete-table --table-name yumBurger-audit --region us-east-1
```

---

## Redeploy after destroy

Data in the silver + semantic buckets survives destroy. After redeploying CDK,
skip datagen and load — just re-apply the manual LF grants:

```bash
# 1. Redeploy stacks
cd infra && cdk deploy --all --require-approval never && cd ..

# 2. Re-apply manual LF grants (see Deploy section above)

# 3. Restart connector
uvicorn connector.main:app --host 0.0.0.0 --port 8000
```

If you also deleted the S3 buckets, run the full first-time sequence from `DEPLOY.md`.

---

## Cost summary

| Resource | Idle cost |
|---|---|
| DynamoDB (audit + memory) | $0 — pay-per-request, no reads = no charge |
| S3 (silver + semantic buckets) | ~$0.023/GB/month — data at rest |
| Athena | $0 — no queries = no charge |
| Bedrock | $0 — no invocations = no charge |
| ECS Fargate | $0 when scaled to zero or destroyed |
| Budget alarm | $0 |

The only ongoing cost after destroy is the retained S3 data (~$0.02/month for this
small POC dataset).
