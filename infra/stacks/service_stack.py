"""ServiceStack — ECR + ECS Fargate + ALB for the YumBurger connector."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from constructs import Construct

from infra.config import ACCOUNT_ID, COMMON_TAGS, REGION, PREFIX


class ServiceStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        connector_runtime_role: iam.Role,
        bedrock_model_id: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        for key, value in COMMON_TAGS.items():
            cdk.Tags.of(self).add(key, value)

        # ── Use default VPC ───────────────────────────────────────────────────
        vpc = ec2.Vpc.from_lookup(self, "DefaultVpc", is_default=True)

        # ── ECR Repository (import existing — created by prior deploy attempt) ─
        self.ecr_repo = ecr.Repository.from_repository_name(
            self,
            "ConnectorRepo",
            repository_name=f"{PREFIX.lower()}-connector",
        )

        # ── ECS Cluster ───────────────────────────────────────────────────────
        cluster = ecs.Cluster(
            self,
            "ConnectorCluster",
            cluster_name=f"{PREFIX.lower()}-connector",
            vpc=vpc,
        )

        # ── CloudWatch Log Group ──────────────────────────────────────────────
        log_group = logs.LogGroup(
            self,
            "ConnectorLogs",
            log_group_name=f"/ecs/{PREFIX.lower()}-connector",
            removal_policy=cdk.RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.ONE_MONTH,
        )

        # ── Task Execution Role (allows ECS to pull ECR image + write logs) ───
        exec_role = iam.Role(
            self,
            "TaskExecRole",
            role_name=f"{PREFIX}-ecs-exec",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                )
            ],
        )

        # ── Fargate Task Definition ───────────────────────────────────────────
        task_def = ecs.FargateTaskDefinition(
            self,
            "ConnectorTask",
            family=f"{PREFIX.lower()}-connector",
            cpu=1024,       # 1 vCPU
            memory_limit_mib=2048,
            task_role=connector_runtime_role,
            execution_role=exec_role,
        )

        task_def.add_container(
            "ConnectorContainer",
            container_name="connector",
            image=ecs.ContainerImage.from_ecr_repository(self.ecr_repo, tag="latest"),
            port_mappings=[ecs.PortMapping(container_port=8000)],
            environment={
                "BEDROCK_MODEL_ID": bedrock_model_id,
                "AWS_REGION": REGION,
                "CONNECTOR_HOST": "0.0.0.0",
                "CONNECTOR_PORT": "8000",
                "LOG_LEVEL": "INFO",
            },
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/health')\" || exit 1"],
                interval=cdk.Duration.seconds(30),
                timeout=cdk.Duration.seconds(10),
                start_period=cdk.Duration.seconds(90),
                retries=3,
            ),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="connector",
                log_group=log_group,
            ),
        )

        # ── Security Groups ───────────────────────────────────────────────────
        alb_sg = ec2.SecurityGroup(
            self, "AlbSg",
            vpc=vpc,
            description="YumBurger ALB allow 80 from anywhere",
            allow_all_outbound=True,
        )
        alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80))

        task_sg = ec2.SecurityGroup(
            self, "TaskSg",
            vpc=vpc,
            description="YumBurger connector task allow 8000 from ALB only",
            allow_all_outbound=True,
        )
        task_sg.add_ingress_rule(alb_sg, ec2.Port.tcp(8000))

        streamlit_sg = ec2.SecurityGroup(
            self, "StreamlitSg",
            vpc=vpc,
            description="YumBurger Streamlit task allow 8501 from ALB only",
            allow_all_outbound=True,
        )
        streamlit_sg.add_ingress_rule(alb_sg, ec2.Port.tcp(8501))

        # ── Streamlit ECR repo (import existing) ─────────────────────────────
        self.streamlit_repo = ecr.Repository.from_repository_name(
            self, "StreamlitRepo",
            repository_name=f"{PREFIX.lower()}-streamlit",
        )

        # ── Streamlit Task Definition ─────────────────────────────────────────
        streamlit_log_group = logs.LogGroup(
            self, "StreamlitLogs",
            log_group_name=f"/ecs/{PREFIX.lower()}-streamlit",
            removal_policy=cdk.RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.ONE_MONTH,
        )

        streamlit_task = ecs.FargateTaskDefinition(
            self, "StreamlitTask",
            family=f"{PREFIX.lower()}-streamlit",
            cpu=512,
            memory_limit_mib=1024,
            execution_role=exec_role,
        )
        streamlit_task.add_container(
            "StreamlitContainer",
            container_name="streamlit",
            image=ecs.ContainerImage.from_ecr_repository(self.streamlit_repo, tag="latest"),
            port_mappings=[ecs.PortMapping(container_port=8501)],
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="streamlit",
                log_group=streamlit_log_group,
            ),
        )

        # ── Application Load Balancer (shared) ────────────────────────────────
        alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(8501))

        alb = elbv2.ApplicationLoadBalancer(
            self,
            "ConnectorAlb",
            load_balancer_name=f"{PREFIX.lower()}-connector",
            vpc=vpc,
            internet_facing=True,
            security_group=alb_sg,
        )

        # ── ECS Fargate Service — Connector ───────────────────────────────────
        fargate_service = ecs.FargateService(
            self,
            "ConnectorService",
            service_name=f"{PREFIX.lower()}-connector",
            cluster=cluster,
            task_definition=task_def,
            desired_count=1,
            assign_public_ip=True,
            security_groups=[task_sg],
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
        )

        # ── ECS Fargate Service — Streamlit ───────────────────────────────────
        streamlit_service = ecs.FargateService(
            self, "StreamlitService",
            service_name=f"{PREFIX.lower()}-streamlit",
            cluster=cluster,
            task_definition=streamlit_task,
            desired_count=1,
            assign_public_ip=True,
            security_groups=[streamlit_sg],
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
        )

        # ── ALB Listeners ─────────────────────────────────────────────────────
        listener = alb.add_listener("HttpListener", port=80, open=False)
        listener.add_targets(
            "ConnectorTarget",
            port=8000,
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[fargate_service],
            health_check=elbv2.HealthCheck(
                path="/health",
                interval=cdk.Duration.seconds(30),
                healthy_threshold_count=2,
                unhealthy_threshold_count=3,
                timeout=cdk.Duration.seconds(10),
            ),
            deregistration_delay=cdk.Duration.seconds(10),
        )

        streamlit_listener = alb.add_listener(
            "StreamlitListener",
            port=8501,
            protocol=elbv2.ApplicationProtocol.HTTP,
            open=True,
        )
        streamlit_listener.add_targets(
            "StreamlitTarget",
            port=8501,
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[streamlit_service],
            health_check=elbv2.HealthCheck(
                path="/_stcore/health",
                interval=cdk.Duration.seconds(30),
                healthy_threshold_count=2,
                unhealthy_threshold_count=3,
                timeout=cdk.Duration.seconds(10),
            ),
            deregistration_delay=cdk.Duration.seconds(10),
        )

        # ── Outputs ───────────────────────────────────────────────────────────
        cdk.CfnOutput(
            self,
            "ECRRepositoryUri",
            value=self.ecr_repo.repository_uri,
            description="Push connector image here",
        )
        cdk.CfnOutput(
            self,
            "StreamlitECRUri",
            value=self.streamlit_repo.repository_uri,
            description="Push Streamlit image here",
        )
        cdk.CfnOutput(
            self,
            "ConnectorURL",
            value=f"http://{alb.load_balancer_dns_name}",
            description="Public connector URL — accessible from anywhere",
        )
        cdk.CfnOutput(
            self,
            "CloudWatchLogs",
            value=f"https://console.aws.amazon.com/cloudwatch/home?region={REGION}#logsV2:log-groups/log-group/{PREFIX.lower()}-connector",
        )
