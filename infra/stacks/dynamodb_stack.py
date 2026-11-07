"""DynamoDBStack — Audit log table."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_dynamodb as dynamodb
from constructs import Construct

from infra.config import COMMON_TAGS, DYNAMODB


class DynamoDBStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        for key, value in COMMON_TAGS.items():
            cdk.Tags.of(self).add(key, value)

        self.audit_table = dynamodb.Table(
            self,
            "AuditTable",
            table_name=DYNAMODB["audit_table"],
            partition_key=dynamodb.Attribute(name="request_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="ts", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.RETAIN,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(point_in_time_recovery_enabled=False),
            time_to_live_attribute="ttl",  # auto-expire audit rows after 90 days
        )

        # GSI: query by persona
        self.audit_table.add_global_secondary_index(
            index_name="persona-ts-index",
            partition_key=dynamodb.Attribute(name="persona", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="ts", type=dynamodb.AttributeType.STRING),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        cdk.CfnOutput(self, "AuditTableName", value=self.audit_table.table_name)
        cdk.CfnOutput(self, "AuditTableArn", value=self.audit_table.table_arn)
