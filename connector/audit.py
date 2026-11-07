"""Audit Plane — DynamoDB audit trail for all connector requests."""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import boto3

from connector.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

TTL_90_DAYS = 90 * 24 * 3600


class AuditPlane:
    """
    Writes audit events to DynamoDB before and after query execution.
    Uses the connector-runtime role (not persona role).
    """

    def __init__(self) -> None:
        self._client = boto3.client("dynamodb", region_name=settings.aws_region)
        self._table = settings.audit_table

    def _now_iso(self) -> str:
        return datetime.now(tz=timezone.utc).isoformat()

    def _ttl(self) -> int:
        return int(time.time()) + TTL_90_DAYS

    def _query_hash(self, sql: str) -> str:
        return hashlib.sha256(sql.encode()).hexdigest()[:16]

    def pre_audit(
        self,
        request_id: str,
        persona: str,
        question: str,
        compiled_sql: str,
        tables_accessed: list[str],
    ) -> None:
        """Write a PRE_QUERY audit event."""
        item = {
            "request_id": {"S": request_id},
            "ts": {"S": self._now_iso()},
            "event_type": {"S": "PRE_QUERY"},
            "persona": {"S": persona},
            "question_hash": {"S": hashlib.sha256(question.encode()).hexdigest()[:16]},
            "query_hash": {"S": self._query_hash(compiled_sql)},
            "tables": {"SS": tables_accessed or ["unknown"]},
            "ttl": {"N": str(self._ttl())},
        }
        try:
            self._client.put_item(TableName=self._table, Item=item)
            logger.debug(f"Pre-audit written for request_id={request_id}")
        except Exception as e:
            # Audit failures must not block query execution
            logger.error(f"Pre-audit write failed: {e}")

    def post_audit(
        self,
        request_id: str,
        persona: str,
        row_count: int,
        execution_id: str,
        duration_ms: int,
        success: bool,
        error_msg: str | None = None,
    ) -> None:
        """Write a POST_QUERY audit event."""
        item: dict[str, Any] = {
            "request_id": {"S": f"{request_id}#post"},
            "ts": {"S": self._now_iso()},
            "event_type": {"S": "POST_QUERY"},
            "persona": {"S": persona},
            "row_count": {"N": str(row_count)},
            "execution_id": {"S": execution_id},
            "duration_ms": {"N": str(duration_ms)},
            "success": {"BOOL": success},
            "ttl": {"N": str(self._ttl())},
        }
        if error_msg:
            item["error_msg"] = {"S": error_msg[:1000]}
        try:
            self._client.put_item(TableName=self._table, Item=item)
            logger.debug(f"Post-audit written for request_id={request_id}")
        except Exception as e:
            logger.error(f"Post-audit write failed: {e}")
