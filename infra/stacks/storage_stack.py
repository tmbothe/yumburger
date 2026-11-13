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

        # Reference existing buckets (created outside CDK before initial deploy)
        self.raw_bucket = s3.Bucket.from_bucket_name(
            self, "RawBucket", S3["raw_bucket"]
        )
        self.silver_bucket = s3.Bucket.from_bucket_name(
            self, "SilverBucket", S3["silver_bucket"]
        )
        self.semantic_bucket = s3.Bucket.from_bucket_name(
            self, "SemanticBucket", S3["semantic_bucket"]
        )
        self.audit_bucket = s3.Bucket.from_bucket_name(
            self, "AuditBucket", S3["audit_bucket"]
        )

        # Athena query results — create if it doesn't exist
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

        # Outputs
        for name, bucket in [
            ("RawBucketName", self.raw_bucket),
            ("SilverBucketName", self.silver_bucket),
            ("SemanticBucketName", self.semantic_bucket),
            ("AthenaResultsBucketName", self.athena_results_bucket),
            ("AuditBucketName", self.audit_bucket),
        ]:
            cdk.CfnOutput(self, name, value=bucket.bucket_name)
