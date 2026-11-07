"""StorageStack — S3 buckets for YumBurger data zones."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_s3 as s3
from constructs import Construct

from infra.config import ACCOUNT_ID, COMMON_TAGS, PREFIX, S3


class StorageStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Apply common tags to all resources in this stack
        for key, value in COMMON_TAGS.items():
            cdk.Tags.of(self).add(key, value)

        lifecycle_rule = s3.LifecycleRule(
            id="glacier-after-90-days",
            transitions=[
                s3.Transition(
                    storage_class=s3.StorageClass.GLACIER,
                    transition_after=cdk.Duration.days(90),
                )
            ],
        )

        # Raw zone — incoming data before Iceberg conversion
        self.raw_bucket = s3.Bucket(
            self,
            "RawBucket",
            bucket_name=S3["raw_bucket"],
            versioned=False,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=cdk.RemovalPolicy.RETAIN,
            lifecycle_rules=[lifecycle_rule],
        )

        # Silver zone — Iceberg tables (source of truth)
        self.silver_bucket = s3.Bucket(
            self,
            "SilverBucket",
            bucket_name=S3["silver_bucket"],
            versioned=True,  # Iceberg needs consistent reads
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        # Semantic zone — ontology Iceberg tables
        self.semantic_bucket = s3.Bucket(
            self,
            "SemanticBucket",
            bucket_name=S3["semantic_bucket"],
            versioned=False,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        # Athena query results
        self.athena_results_bucket = s3.Bucket(
            self,
            "AthenaResultsBucket",
            bucket_name=S3["athena_results_bucket"],
            versioned=False,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="expire-results-30-days",
                    expiration=cdk.Duration.days(30),
                )
            ],
        )

        # Audit logs
        self.audit_bucket = s3.Bucket(
            self,
            "AuditBucket",
            bucket_name=S3["audit_bucket"],
            versioned=False,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        # Outputs
        for name, bucket in [
            ("RawBucketName", self.raw_bucket),
            ("SilverBucketName", self.silver_bucket),
            ("SemanticBucketName", self.semantic_bucket),
            ("AthenaResultsBucketName", self.athena_results_bucket),
            ("AuditBucketName", self.audit_bucket),
        ]:
            cdk.CfnOutput(self, name, value=bucket.bucket_name)
