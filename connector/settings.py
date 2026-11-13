"""Connector settings — loaded from .env + config/settings.yaml."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).parent.parent
_CFG_PATH = ROOT / "config" / "settings.yaml"

with open(_CFG_PATH) as _f:
    _YAML = yaml.safe_load(_f)


class ConnectorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # From .env
    aws_region: str = Field(default=_YAML["project"]["region"])
    aws_profile: str = Field(default="default")
    bedrock_model_id: str = Field(default="anthropic.claude-3-5-sonnet-20241022-v2:0")
    connector_host: str = Field(default="0.0.0.0")
    connector_port: int = Field(default=8000)
    log_level: str = Field(default="INFO")

    # From YAML (not overridable via env for safety)
    @property
    def project_prefix(self) -> str:
        return _YAML["project"]["prefix"]

    @property
    def account_id(self) -> str:
        return _YAML["project"]["account_id"]

    @property
    def silver_db(self) -> str:
        return _YAML["athena"]["silver_database"]

    @property
    def semantic_db(self) -> str:
        return _YAML["athena"]["semantic_database"]

    @property
    def workgroup(self) -> str:
        return _YAML["athena"]["workgroup"]

    @property
    def audit_table(self) -> str:
        return _YAML["dynamodb"]["audit_table"]

    @property
    def memory_table(self) -> str:
        return _YAML["dynamodb"]["memory_table"]

    @property
    def athena_results_bucket(self) -> str:
        return _YAML["s3"]["athena_results_bucket"]

    @property
    def connector_runtime_role(self) -> str:
        return _YAML["iam"]["connector_runtime_role"]

    @property
    def persona_analyst_role(self) -> str:
        return _YAML["iam"]["persona_analyst_role"]

    @property
    def persona_admin_role(self) -> str:
        return _YAML["iam"]["persona_admin_role"]

    @property
    def allowed_tables(self) -> list[str]:
        return _YAML["allowed_query_tables"]

    @property
    def query_timeout_seconds(self) -> int:
        return _YAML["athena"]["query_timeout_seconds"]


@lru_cache(maxsize=1)
def get_settings() -> ConnectorSettings:
    return ConnectorSettings()
