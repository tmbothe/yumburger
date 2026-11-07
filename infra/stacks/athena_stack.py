"""AthenaStack — Workgroup + result location configuration."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_athena as athena
from constructs import Construct

from infra.config import COMMON_TAGS, S3


class AthenaStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        athena_results_bucket_name: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        for key, value in COMMON_TAGS.items():
            cdk.Tags.of(self).add(key, value)

        self.workgroup = athena.CfnWorkGroup(
            self,
            "YumBurgerWorkgroup",
            name="yumBurger-wg",
            description="YumBurger Athena workgroup — Iceberg + Federated queries",
            state="ENABLED",
            work_group_configuration=athena.CfnWorkGroup.WorkGroupConfigurationProperty(
                result_configuration=athena.CfnWorkGroup.ResultConfigurationProperty(
                    output_location=f"s3://{athena_results_bucket_name}/results/",
                    encryption_configuration=athena.CfnWorkGroup.EncryptionConfigurationProperty(
                        encryption_option="SSE_S3",
                    ),
                ),
                enforce_work_group_configuration=True,
                engine_version=athena.CfnWorkGroup.EngineVersionProperty(
                    selected_engine_version="Athena engine version 3",
                ),
                bytes_scanned_cutoff_per_query=1_073_741_824,  # 1 GB scan limit per query
                publish_cloud_watch_metrics_enabled=True,
            ),
            recursive_delete_option=True,
        )

        cdk.CfnOutput(self, "WorkgroupName", value=self.workgroup.name)
        cdk.CfnOutput(
            self,
            "ResultLocation",
            value=f"s3://{athena_results_bucket_name}/results/",
        )
