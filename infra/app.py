#!/usr/bin/env python3
"""YumBurger CDK app — 7 stacks deployed in dependency order."""

import sys
from pathlib import Path

# Add project root to path so `infra.*` imports resolve when CDK runs from infra/
sys.path.insert(0, str(Path(__file__).parent.parent))

import aws_cdk as cdk

from infra.config import CDK_ENV
from infra.stacks.athena_stack import AthenaStack
from infra.stacks.budget_stack import BudgetStack
from infra.stacks.dynamodb_stack import DynamoDBStack
from infra.stacks.iam_stack import IAMStack
from infra.stacks.lakeformation_stack import LakeFormationStack
from infra.stacks.observability_stack import ObservabilityStack
from infra.stacks.service_stack import ServiceStack
from infra.stacks.storage_stack import StorageStack

app = cdk.App()

# 1 — Storage (no dependencies)
storage = StorageStack(app, "StorageStack", env=CDK_ENV)

# 2 — IAM (depends on storage for bucket ARNs)
iam = IAMStack(
    app,
    "IAMStack",
    silver_bucket_arn=storage.silver_bucket.bucket_arn,
    semantic_bucket_arn=storage.semantic_bucket.bucket_arn,
    athena_results_bucket_arn=storage.athena_results_bucket.bucket_arn,
    audit_bucket_arn=storage.audit_bucket.bucket_arn,
    env=CDK_ENV,
)
iam.add_stack_dependency(storage)

# 3 — Lake Formation (depends on storage + IAM)
lf = LakeFormationStack(
    app,
    "LakeFormationStack",
    silver_bucket_name=storage.silver_bucket.bucket_name,
    semantic_bucket_name=storage.semantic_bucket.bucket_name,
    connector_runtime_role_arn=iam.connector_runtime_role.role_arn,
    persona_analyst_role_arn=iam.persona_analyst_role.role_arn,
    persona_admin_role_arn=iam.persona_admin_role.role_arn,
    env=CDK_ENV,
)
lf.add_stack_dependency(iam)

# 4 — Athena (depends on storage for results bucket)
athena = AthenaStack(
    app,
    "AthenaStack",
    athena_results_bucket_name=storage.athena_results_bucket.bucket_name,
    env=CDK_ENV,
)
athena.add_stack_dependency(storage)

# 5 — DynamoDB (no dependencies)
dynamodb = DynamoDBStack(app, "DynamoDBStack", env=CDK_ENV)

# 6 — Observability (no hard dependencies, but deploy after core stacks)
observability = ObservabilityStack(app, "ObservabilityStack", env=CDK_ENV)
observability.add_stack_dependency(athena)

# 7 — Budget (no dependencies)
budget = BudgetStack(app, "BudgetStack", env=CDK_ENV)

# 8 — Service: ECR + App Runner (depends on IAM for connector-runtime role)
service = ServiceStack(
    app,
    "ServiceStack",
    connector_runtime_role=iam.connector_runtime_role,
    env=CDK_ENV,
)
service.add_stack_dependency(iam)

app.synth()
