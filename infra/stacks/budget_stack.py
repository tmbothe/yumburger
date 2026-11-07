"""BudgetStack — AWS Budgets $50/month alert."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_budgets as budgets
from constructs import Construct

from infra.config import BUDGET, COMMON_TAGS, OWNER, PREFIX


class BudgetStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        for key, value in COMMON_TAGS.items():
            cdk.Tags.of(self).add(key, value)

        budgets.CfnBudget(
            self,
            "MonthlyBudget",
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_name=f"{PREFIX}-monthly-budget",
                budget_type="COST",
                time_unit="MONTHLY",
                budget_limit=budgets.CfnBudget.SpendProperty(
                    amount=BUDGET["monthly_limit_usd"],
                    unit="USD",
                ),
                cost_filters={
                    "TagKeyValue": [f"user:project${PREFIX}"],
                },
            ),
            notifications_with_subscribers=[
                # Alert at 50%
                budgets.CfnBudget.NotificationWithSubscribersProperty(
                    notification=budgets.CfnBudget.NotificationProperty(
                        notification_type="ACTUAL",
                        comparison_operator="GREATER_THAN",
                        threshold=50,
                        threshold_type="PERCENTAGE",
                    ),
                    subscribers=[
                        budgets.CfnBudget.SubscriberProperty(
                            subscription_type="EMAIL",
                            address=OWNER,
                        )
                    ],
                ),
                # Alert at 80%
                budgets.CfnBudget.NotificationWithSubscribersProperty(
                    notification=budgets.CfnBudget.NotificationProperty(
                        notification_type="ACTUAL",
                        comparison_operator="GREATER_THAN",
                        threshold=80,
                        threshold_type="PERCENTAGE",
                    ),
                    subscribers=[
                        budgets.CfnBudget.SubscriberProperty(
                            subscription_type="EMAIL",
                            address=OWNER,
                        )
                    ],
                ),
                # Alert at 100%
                budgets.CfnBudget.NotificationWithSubscribersProperty(
                    notification=budgets.CfnBudget.NotificationProperty(
                        notification_type="FORECASTED",
                        comparison_operator="GREATER_THAN",
                        threshold=100,
                        threshold_type="PERCENTAGE",
                    ),
                    subscribers=[
                        budgets.CfnBudget.SubscriberProperty(
                            subscription_type="EMAIL",
                            address=OWNER,
                        )
                    ],
                ),
            ],
        )
