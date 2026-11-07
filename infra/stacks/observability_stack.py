"""ObservabilityStack — CloudWatch dashboard + alarms."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_sns as sns
from constructs import Construct

from infra.config import COMMON_TAGS, OWNER, PREFIX


class ObservabilityStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        for key, value in COMMON_TAGS.items():
            cdk.Tags.of(self).add(key, value)

        # SNS topic for alerts
        self.alert_topic = sns.Topic(
            self,
            "AlertTopic",
            topic_name=f"{PREFIX}-alerts",
            display_name=f"YumBurger Alerts",
        )

        # Email subscription
        sns.Subscription(
            self,
            "AlertEmailSubscription",
            topic=self.alert_topic,
            protocol=sns.SubscriptionProtocol.EMAIL,
            endpoint=OWNER,
        )

        # ── CloudWatch Dashboard ───────────────────────────────────────────────
        dashboard = cw.Dashboard(
            self,
            "YumBurgerDashboard",
            dashboard_name=f"{PREFIX}-dashboard",
        )

        # Athena bytes scanned metric
        athena_bytes_scanned = cw.Metric(
            namespace="AWS/Athena",
            metric_name="DataScannedInBytes",
            dimensions_map={"WorkGroupName": "yumBurger-wg"},
            statistic="Sum",
            period=cdk.Duration.hours(1),
        )

        # Athena query count
        athena_query_count = cw.Metric(
            namespace="AWS/Athena",
            metric_name="TotalExecutionTime",
            dimensions_map={"WorkGroupName": "yumBurger-wg"},
            statistic="SampleCount",
            period=cdk.Duration.hours(1),
        )

        dashboard.add_widgets(
            cw.GraphWidget(
                title="Athena — Data Scanned (Bytes)",
                left=[athena_bytes_scanned],
                width=12,
            ),
            cw.GraphWidget(
                title="Athena — Query Count",
                left=[athena_query_count],
                width=12,
            ),
        )

        # ── Athena High Scan Alarm ─────────────────────────────────────────────
        # Alert if any single query scans > 500 MB
        athena_scan_alarm = cw.Alarm(
            self,
            "AthenaHighScanAlarm",
            alarm_name=f"{PREFIX}-athena-high-scan",
            metric=cw.Metric(
                namespace="AWS/Athena",
                metric_name="DataScannedInBytes",
                dimensions_map={"WorkGroupName": "yumBurger-wg"},
                statistic="Maximum",
                period=cdk.Duration.minutes(5),
            ),
            threshold=500 * 1024 * 1024,  # 500 MB
            evaluation_periods=1,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="Athena query scanned more than 500 MB",
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
        )
        athena_scan_alarm.add_alarm_action(cw_actions.SnsAction(self.alert_topic))

        cdk.CfnOutput(self, "DashboardUrl", value=f"https://console.aws.amazon.com/cloudwatch/home#dashboards:name={PREFIX}-dashboard")
        cdk.CfnOutput(self, "AlertTopicArn", value=self.alert_topic.topic_arn)
