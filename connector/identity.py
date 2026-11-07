"""Identity Plane — STS AssumeRole to get persona credentials."""

from __future__ import annotations

import logging
from typing import Literal

import boto3
from botocore.credentials import RefreshableCredentials
from botocore.session import get_session as botocore_get_session

from connector.settings import get_settings

logger = logging.getLogger(__name__)

PersonaType = Literal["analyst", "admin"]


def assume_persona_role(persona: PersonaType) -> boto3.Session:
    """
    Assume the IAM role for the given persona and return a boto3 Session.
    The connector-runtime role (current context) assumes the persona role via STS.
    """
    settings = get_settings()
    account_id = settings.account_id

    role_map: dict[PersonaType, str] = {
        "analyst": f"arn:aws:iam::{account_id}:role/{settings.persona_analyst_role}",
        "admin": f"arn:aws:iam::{account_id}:role/{settings.persona_admin_role}",
    }
    role_arn = role_map[persona]

    sts = boto3.client("sts", region_name=settings.aws_region)
    logger.info(f"Assuming role {role_arn} for persona={persona}")

    response = sts.assume_role(
        RoleArn=role_arn,
        RoleSessionName=f"yumBurger-connector-{persona}",
        DurationSeconds=900,  # 15 minutes
    )
    creds = response["Credentials"]

    session = boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
        region_name=settings.aws_region,
    )
    logger.info(f"Assumed role for persona={persona} successfully")
    return session


def get_caller_identity() -> dict:
    """Return the current caller identity (useful for diagnostics)."""
    sts = boto3.client("sts")
    return sts.get_caller_identity()
