"""ServiceStack — ECR + ECS Fargate (no ALB) for YumBurger POC.

Single Fargate task running both FastAPI (port 8000 internal) and
Streamlit (port 8501 public). Accessed via the task's public IP directly.
No ALB — cost is ~$8/month when running, $0 when scaled to zero.
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_ecs as ecs
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

        repo_name = f"{PREFIX.lower()}-app"

        # ── ECR Repository ────────────────────────────────────────────────────
        self.ecr_repo = ecr.Repository(
            self,
            "AppRepo",
            repository_name=repo_name,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            empty_on_delete=True,
        )

        # ── Default VPC ───────────────────────────────────────────────────────
        vpc = ec2.Vpc.from_lookup(self, "DefaultVpc", is_default=True)

        # ── Security Group — allow Streamlit (8501) from anywhere ─────────────
        sg = ec2.SecurityGroup(
            self,
            "AppSg",
            vpc=vpc,
            description="YumBurger POC - allow Streamlit UI from internet",
            allow_all_outbound=True,
        )
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(8501), "Streamlit UI")

        # ── ECS Cluster ───────────────────────────────────────────────────────
        cluster = ecs.Cluster(
            self,
            "Cluster",
            cluster_name=f"{PREFIX.lower()}-cluster",
            vpc=vpc,
        )

        # ── CloudWatch Logs ───────────────────────────────────────────────────
        log_group = logs.LogGroup(
            self,
            "AppLogs",
            log_group_name=f"/ecs/{PREFIX.lower()}-app",
            removal_policy=cdk.RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.ONE_WEEK,
        )

        # ── Task Execution Role (pull ECR image + write logs) ─────────────────
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

        # ── Task Definition (0.5 vCPU / 1 GB) ────────────────────────────────
        task_def = ecs.FargateTaskDefinition(
            self,
            "AppTask",
            family=f"{PREFIX.lower()}-app",
            cpu=512,
            memory_limit_mib=1024,
            task_role=connector_runtime_role,
            execution_role=exec_role,
        )

        task_def.add_container(
            "AppContainer",
            container_name="app",
            image=ecs.ContainerImage.from_ecr_repository(self.ecr_repo, tag="latest"),
            port_mappings=[ecs.PortMapping(container_port=8501)],
            environment={
                "BEDROCK_MODEL_ID": bedrock_model_id,
                "AWS_REGION": REGION,
                "CONNECTOR_URL": "http://localhost:8000",
                "LOG_LEVEL": "INFO",
            },
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="app",
                log_group=log_group,
            ),
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "curl -f http://localhost:8501/_stcore/health || exit 1"],
                interval=cdk.Duration.seconds(30),
                timeout=cdk.Duration.seconds(10),
                start_period=cdk.Duration.seconds(120),
                retries=3,
            ),
        )

        # ── Fargate Service — public IP, no ALB ───────────────────────────────
        # desired_count=0 at deploy time — start with no running tasks.
        # Push the Docker image to ECR first, then scale to 1:
        #   aws ecs update-service --cluster yumburger-cluster --service yumburger-app --desired-count 1
        self.service = ecs.FargateService(
            self,
            "AppService",
            service_name=f"{PREFIX.lower()}-app",
            cluster=cluster,
            task_definition=task_def,
            desired_count=0,
            assign_public_ip=True,
            security_groups=[sg],
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
        )

        # ── Outputs ───────────────────────────────────────────────────────────
        cdk.CfnOutput(
            self, "ECRRepositoryUri",
            value=self.ecr_repo.repository_uri,
            description="Push image here: docker push <uri>:latest",
        )
        cdk.CfnOutput(
            self, "ClusterName",
            value=cluster.cluster_name,
        )
        cdk.CfnOutput(
            self, "ServiceName",
            value=self.service.service_name,
        )
        cdk.CfnOutput(
            self, "GetIPCommand",
            value=(
                f"TASK=$(aws ecs list-tasks --cluster {PREFIX.lower()}-cluster "
                f"--service-name {PREFIX.lower()}-app --query taskArns[0] --output text) && "
                f"ENI=$(aws ecs describe-tasks --cluster {PREFIX.lower()}-cluster --tasks $TASK "
                f"--query \"tasks[0].attachments[0].details[?name=='networkInterfaceId'].value\" --output text) && "
                f"aws ec2 describe-network-interfaces --network-interface-ids $ENI "
                f"--query \"NetworkInterfaces[0].Association.PublicIp\" --output text"
            ),
            description="Run this to get the Streamlit public IP after deploy",
        )
        cdk.CfnOutput(
            self, "ScaleDownCommand",
            value=f"aws ecs update-service --cluster {PREFIX.lower()}-cluster --service {PREFIX.lower()}-app --desired-count 0 --region {REGION}",
            description="Scale to 0 to stop billing when not in use",
        )
        cdk.CfnOutput(
            self, "ScaleUpCommand",
            value=f"aws ecs update-service --cluster {PREFIX.lower()}-cluster --service {PREFIX.lower()}-app --desired-count 1 --region {REGION}",
            description="Scale back up to 1 when needed",
        )
