"""IAMStack — IAM roles for connector-runtime and personas."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_iam as iam
from constructs import Construct

from infra.config import ACCOUNT_ID, COMMON_TAGS, IAM_CFG, PREFIX, REGION, S3


class IAMStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        silver_bucket_arn: str,
        semantic_bucket_arn: str,
        athena_results_bucket_arn: str,
        audit_bucket_arn: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        for key, value in COMMON_TAGS.items():
            cdk.Tags.of(self).add(key, value)

        # ── Connector Runtime Role ────────────────────────────────────────────
        # This role is assumed by the connector service (FastAPI/MCP).
        # Explicitly DENIED s3:GetObject on silver/* to enforce Athena-only access.
        self.connector_runtime_role = iam.Role(
            self,
            "ConnectorRuntimeRole",
            role_name=IAM_CFG["connector_runtime_role"],
            assumed_by=iam.CompositePrincipal(
                iam.AccountPrincipal(ACCOUNT_ID),                       # local dev / bedrock-user
                iam.ServicePrincipal("ecs-tasks.amazonaws.com"),         # ECS Fargate (kept for compat)
                iam.ServicePrincipal("tasks.apprunner.amazonaws.com"),   # App Runner
            ),
            description="YumBurger connector service runtime role",
        )

        # Allow Athena actions
        self.connector_runtime_role.add_to_policy(
            iam.PolicyStatement(
                sid="AllowAthena",
                effect=iam.Effect.ALLOW,
                actions=[
                    "athena:StartQueryExecution",
                    "athena:GetQueryExecution",
                    "athena:GetQueryResults",
                    "athena:StopQueryExecution",
                    "athena:ListQueryExecutions",
                    "athena:GetWorkGroup",
                ],
                resources=[
                    f"arn:aws:athena:{REGION}:{ACCOUNT_ID}:workgroup/yumBurger-wg",
                ],
            )
        )

        # Allow Athena results bucket access
        self.connector_runtime_role.add_to_policy(
            iam.PolicyStatement(
                sid="AllowAthenaResults",
                effect=iam.Effect.ALLOW,
                actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:GetBucketLocation"],
                resources=[
                    athena_results_bucket_arn,
                    f"{athena_results_bucket_arn}/*",
                ],
            )
        )

        # Allow Glue Catalog reads (for Athena metadata)
        self.connector_runtime_role.add_to_policy(
            iam.PolicyStatement(
                sid="AllowGlueCatalog",
                effect=iam.Effect.ALLOW,
                actions=[
                    "glue:GetDatabase",
                    "glue:GetDatabases",
                    "glue:GetTable",
                    "glue:GetTables",
                    "glue:GetPartition",
                    "glue:GetPartitions",
                ],
                resources=["*"],
            )
        )

        # Allow DynamoDB audit writes + conversation memory reads/writes
        self.connector_runtime_role.add_to_policy(
            iam.PolicyStatement(
                sid="AllowDynamoDBAudit",
                effect=iam.Effect.ALLOW,
                actions=["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:Query", "dynamodb:DeleteItem"],
                resources=[
                    f"arn:aws:dynamodb:{REGION}:{ACCOUNT_ID}:table/yumBurger-audit",
                    f"arn:aws:dynamodb:{REGION}:{ACCOUNT_ID}:table/yumBurger-audit/index/*",
                    f"arn:aws:dynamodb:{REGION}:{ACCOUNT_ID}:table/yumBurger-conversation",
                    f"arn:aws:dynamodb:{REGION}:{ACCOUNT_ID}:table/yumBurger-conversation/index/*",
                ],
            )
        )

        # Allow Bedrock for NL→SQL compilation
        self.connector_runtime_role.add_to_policy(
            iam.PolicyStatement(
                sid="AllowBedrock",
                effect=iam.Effect.ALLOW,
                actions=["bedrock:InvokeModel"],
                resources=["*"],
            )
        )

        # Required for Athena to get LF-vended S3 credentials for Iceberg tables
        self.connector_runtime_role.add_to_policy(
            iam.PolicyStatement(
                sid="LFDataAccess",
                effect=iam.Effect.ALLOW,
                actions=["lakeformation:GetDataAccess"],
                resources=["*"],
            )
        )

        # Allow STS AssumeRole to persona roles
        self.connector_runtime_role.add_to_policy(
            iam.PolicyStatement(
                sid="AllowAssumePersonaRoles",
                effect=iam.Effect.ALLOW,
                actions=["sts:AssumeRole"],
                resources=[
                    f"arn:aws:iam::{ACCOUNT_ID}:role/{IAM_CFG['persona_analyst_role']}",
                    f"arn:aws:iam::{ACCOUNT_ID}:role/{IAM_CFG['persona_admin_role']}",
                ],
            )
        )

        # EXPLICIT DENY: connector-runtime cannot read silver data directly from S3
        self.connector_runtime_role.add_to_policy(
            iam.PolicyStatement(
                sid="DenyDirectSilverS3Access",
                effect=iam.Effect.DENY,
                actions=["s3:GetObject"],
                resources=[f"{silver_bucket_arn}/silver/*"],
            )
        )

        # ── Persona Analyst Role ──────────────────────────────────────────────
        self.persona_analyst_role = iam.Role(
            self,
            "PersonaAnalystRole",
            role_name=IAM_CFG["persona_analyst_role"],
            assumed_by=iam.ArnPrincipal(self.connector_runtime_role.role_arn),
            description="YumBurger analyst persona - region-scoped query access",
        )

        self.persona_analyst_role.add_to_policy(
            iam.PolicyStatement(
                sid="AllowAthenaQuery",
                effect=iam.Effect.ALLOW,
                actions=[
                    "athena:StartQueryExecution",
                    "athena:GetQueryExecution",
                    "athena:GetQueryResults",
                    "athena:GetWorkGroup",
                ],
                resources=[
                    f"arn:aws:athena:{REGION}:{ACCOUNT_ID}:workgroup/yumBurger-wg",
                ],
            )
        )

        self.persona_analyst_role.add_to_policy(
            iam.PolicyStatement(
                sid="AllowS3ResultsReadWrite",
                effect=iam.Effect.ALLOW,
                actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:GetBucketLocation"],
                resources=[
                    athena_results_bucket_arn,
                    f"{athena_results_bucket_arn}/*",
                ],
            )
        )

        self.persona_analyst_role.add_to_policy(
            iam.PolicyStatement(
                sid="AllowGlueCatalogRead",
                effect=iam.Effect.ALLOW,
                actions=["glue:GetDatabase", "glue:GetTable", "glue:GetTables", "glue:GetPartitions"],
                resources=["*"],
            )
        )

        # ── Persona Admin Role ────────────────────────────────────────────────
        self.persona_admin_role = iam.Role(
            self,
            "PersonaAdminRole",
            role_name=IAM_CFG["persona_admin_role"],
            assumed_by=iam.ArnPrincipal(self.connector_runtime_role.role_arn),
            description="YumBurger admin persona - full query access",
        )

        # Admin gets same permissions but LF will grant access to all columns/rows
        self.persona_admin_role.add_to_policy(
            iam.PolicyStatement(
                sid="AllowAthenaAndGlue",
                effect=iam.Effect.ALLOW,
                actions=[
                    "athena:StartQueryExecution",
                    "athena:GetQueryExecution",
                    "athena:GetQueryResults",
                    "athena:GetWorkGroup",
                    "glue:GetDatabase",
                    "glue:GetTable",
                    "glue:GetTables",
                    "glue:GetPartitions",
                ],
                resources=["*"],
            )
        )

        self.persona_admin_role.add_to_policy(
            iam.PolicyStatement(
                sid="AllowS3Results",
                effect=iam.Effect.ALLOW,
                actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:GetBucketLocation"],
                resources=[
                    athena_results_bucket_arn,
                    f"{athena_results_bucket_arn}/*",
                ],
            )
        )

        # Outputs
        cdk.CfnOutput(self, "ConnectorRuntimeRoleArn", value=self.connector_runtime_role.role_arn)
        cdk.CfnOutput(self, "PersonaAnalystRoleArn", value=self.persona_analyst_role.role_arn)
        cdk.CfnOutput(self, "PersonaAdminRoleArn", value=self.persona_admin_role.role_arn)
