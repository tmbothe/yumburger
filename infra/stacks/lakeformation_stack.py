"""LakeFormationStack — LF databases + permissions + column/row policies."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_glue as glue
from aws_cdk import aws_lakeformation as lakeformation
from constructs import Construct

from infra.config import ACCOUNT_ID, COMMON_TAGS, IAM_CFG, PREFIX, REGION, S3


class LakeFormationStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        silver_bucket_name: str,
        semantic_bucket_name: str,
        connector_runtime_role_arn: str,
        persona_analyst_role_arn: str,
        persona_admin_role_arn: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        for key, value in COMMON_TAGS.items():
            cdk.Tags.of(self).add(key, value)

        # ── Glue Databases ─────────────────────────────────────────────────────
        # location_uri omitted — Iceberg tables define their own S3 location.
        # S3 locations are pre-registered with LF manually using yumBurger-lf-s3-role.
        self.silver_db = glue.CfnDatabase(
            self,
            "SilverDatabase",
            catalog_id=ACCOUNT_ID,
            database_input=glue.CfnDatabase.DatabaseInputProperty(
                name="yumburger_silver",
                description="YumBurger Iceberg silver zone",
            ),
        )

        self.semantic_db = glue.CfnDatabase(
            self,
            "SemanticDatabase",
            catalog_id=ACCOUNT_ID,
            database_input=glue.CfnDatabase.DatabaseInputProperty(
                name="yumburger_semantic",
                description="YumBurger semantic ontology zone",
            ),
        )

        # NOTE: S3 locations registered manually with yumBurger-lf-s3-role (not SLR).
        # SLR lacks S3 write credentials needed for Iceberg operations.

        # ── LF Permissions — connector-runtime: metadata only ─────────────────
        # connector-runtime can DESCRIBE tables (metadata plane) but not SELECT data
        cr_silver = lakeformation.CfnPermissions(
            self,
            "ConnectorRuntimeSilverDbDescribe",
            data_lake_principal=lakeformation.CfnPermissions.DataLakePrincipalProperty(
                data_lake_principal_identifier=connector_runtime_role_arn
            ),
            resource=lakeformation.CfnPermissions.ResourceProperty(
                database_resource=lakeformation.CfnPermissions.DatabaseResourceProperty(
                    catalog_id=ACCOUNT_ID,
                    name="yumburger_silver",
                )
            ),
            permissions=["DESCRIBE"],
        )
        cr_silver.add_dependency(self.silver_db)

        cr_semantic = lakeformation.CfnPermissions(
            self,
            "ConnectorRuntimeSemanticSelect",
            data_lake_principal=lakeformation.CfnPermissions.DataLakePrincipalProperty(
                data_lake_principal_identifier=connector_runtime_role_arn
            ),
            resource=lakeformation.CfnPermissions.ResourceProperty(
                database_resource=lakeformation.CfnPermissions.DatabaseResourceProperty(
                    catalog_id=ACCOUNT_ID,
                    name="yumburger_semantic",
                )
            ),
            permissions=["DESCRIBE", "CREATE_TABLE"],
        )
        cr_semantic.add_dependency(self.semantic_db)

        # ── LF Permissions — persona-analyst: SELECT on all silver tables (wildcard) ─
        # Using table wildcard so this works before Iceberg tables are created in Phase 4.
        # Per-table / column-level filters are applied after `make load` via scripts/lf_post_load.py.
        analyst_silver_perm = lakeformation.CfnPermissions(
            self,
            "AnalystSilverAllTables",
            data_lake_principal=lakeformation.CfnPermissions.DataLakePrincipalProperty(
                data_lake_principal_identifier=persona_analyst_role_arn
            ),
            resource=lakeformation.CfnPermissions.ResourceProperty(
                table_resource=lakeformation.CfnPermissions.TableResourceProperty(
                    catalog_id=ACCOUNT_ID,
                    database_name="yumburger_silver",
                    table_wildcard={},  # all current and future tables
                )
            ),
            permissions=["SELECT", "DESCRIBE"],
        )
        analyst_silver_perm.add_dependency(self.silver_db)

        # ── LF Permissions — persona-admin: full SELECT on all silver tables ─────────
        admin_silver_perm = lakeformation.CfnPermissions(
            self,
            "AdminSilverAllTables",
            data_lake_principal=lakeformation.CfnPermissions.DataLakePrincipalProperty(
                data_lake_principal_identifier=persona_admin_role_arn
            ),
            resource=lakeformation.CfnPermissions.ResourceProperty(
                table_resource=lakeformation.CfnPermissions.TableResourceProperty(
                    catalog_id=ACCOUNT_ID,
                    database_name="yumburger_silver",
                    table_wildcard={},
                )
            ),
            permissions=["SELECT", "DESCRIBE", "ALTER"],
        )
        admin_silver_perm.add_dependency(self.silver_db)

        # ── LF Permissions — personas: SELECT on semantic tables ──────────────
        for role_arn, construct_id in [
            (persona_analyst_role_arn, "AnalystSemanticAllTables"),
            (persona_admin_role_arn,   "AdminSemanticAllTables"),
        ]:
            perm = lakeformation.CfnPermissions(
                self,
                construct_id,
                data_lake_principal=lakeformation.CfnPermissions.DataLakePrincipalProperty(
                    data_lake_principal_identifier=role_arn
                ),
                resource=lakeformation.CfnPermissions.ResourceProperty(
                    table_resource=lakeformation.CfnPermissions.TableResourceProperty(
                        catalog_id=ACCOUNT_ID,
                        database_name="yumburger_semantic",
                        table_wildcard={},
                    )
                ),
                permissions=["SELECT", "DESCRIBE"],
            )
            perm.add_dependency(self.semantic_db)

        # NOTE: Column-level PII masking (CfnDataCellsFilter) for the customer table
        # is applied after Phase 4 (make load) once the Iceberg table exists in Glue Catalog.
        # See: scripts/lf_post_load.py

        cdk.CfnOutput(self, "SilverDatabaseName", value="yumburger_silver")
        cdk.CfnOutput(self, "SemanticDatabaseName", value="yumburger_semantic")
