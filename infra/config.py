"""Shared CDK configuration loaded from config/settings.yaml."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

_ROOT = Path(__file__).parent.parent
_SETTINGS_PATH = _ROOT / "config" / "settings.yaml"


def load_settings() -> dict:
    with open(_SETTINGS_PATH) as f:
        return yaml.safe_load(f)


CFG = load_settings()
PROJECT = CFG["project"]
S3 = CFG["s3"]
ATHENA = CFG["athena"]
DYNAMODB = CFG["dynamodb"]
IAM_CFG = CFG["iam"]
TAGS = CFG["tags"]
BUDGET = CFG["budget"]

ACCOUNT_ID: str = PROJECT["account_id"]
REGION: str = PROJECT["region"]
PREFIX: str = PROJECT["prefix"]
OWNER: str = PROJECT["owner"]
ENV: str = PROJECT["env"]

CDK_ENV = {"account": ACCOUNT_ID, "region": REGION}

COMMON_TAGS = {
    "project": PREFIX,
    "owner": OWNER,
    "env": ENV,
}
