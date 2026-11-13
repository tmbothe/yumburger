"""
Memory Plane — Tiered conversation memory for session-aware NL interactions.

Tier 1 (Hot):  Last HOT_WINDOW turns injected verbatim into the LLM prompt.
Tier 2 (Warm): Bedrock-compressed summary of older turns stored as one DynamoDB item.
Tier 3 (Cold): Full turn history in DynamoDB, TTL = 30 days.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import boto3

from connector.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

TTL_30_DAYS = 30 * 24 * 3600
HOT_WINDOW = 5    # turns injected verbatim into prompt
COMPACT_AT = 10   # trigger Bedrock compaction when session exceeds this many turns


@dataclass
class ConversationTurn:
    turn_index: int
    question: str
    answer: str
    sql: str
    row_count: int
    ts: str


@dataclass
class ConversationContext:
    session_id: str
    turns: list[ConversationTurn] = field(default_factory=list)
    summary: str | None = None
    total_turns: int = 0

    def is_empty(self) -> bool:
        return self.total_turns == 0

    def to_prompt_block(self) -> str:
        """
        Format the context as a prompt block for injection into LLM calls.
        Returns an empty string when there is no history.
        """
        if self.is_empty():
            return ""

        parts: list[str] = ["[CONVERSATION CONTEXT]"]

        if self.summary:
            parts.append("Session summary (earlier turns):")
            parts.append(self.summary)
            parts.append("")

        if self.turns:
            parts.append("Recent turns:")
            for t in self.turns:
                parts.append(
                    f"Turn {t.turn_index} — User: {t.question}\n"
                    f"         SQL:    {t.sql[:200]}{'...' if len(t.sql) > 200 else ''}\n"
                    f"         Answer: {t.answer[:300]}{'...' if len(t.answer) > 300 else ''}"
                )

        parts.append("[END CONTEXT]")
        return "\n".join(parts)


class MemoryPlane:
    """
    Tiered conversation memory backed by DynamoDB.

    Usage:
        memory = MemoryPlane()
        ctx = memory.get_context(session_id)          # before calling LLM
        # ... call LLM with ctx.to_prompt_block() ...
        memory.add_turn(session_id, persona, q, a, sql, row_count)
    """

    def __init__(self) -> None:
        self._ddb = boto3.client("dynamodb", region_name=settings.aws_region)
        self._bedrock = boto3.client("bedrock-runtime", region_name=settings.aws_region)
        self._table = settings.memory_table

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def get_context(self, session_id: str) -> ConversationContext:
        """Return last HOT_WINDOW turns + any existing session summary."""
        ctx = ConversationContext(session_id=session_id)
        try:
            items = self._query_session(session_id)
        except Exception as e:
            logger.error(f"Memory read failed for session {session_id}: {e}")
            return ctx

        summary_item = next(
            (i for i in items if i.get("sk", {}).get("S") == "summary"), None
        )
        turn_items = [
            i for i in items if i.get("sk", {}).get("S", "").startswith("turn#")
        ]
        turn_items.sort(key=lambda i: i["sk"]["S"])

        ctx.total_turns = len(turn_items)

        if summary_item:
            ctx.summary = summary_item.get("content", {}).get("S")

        for item in turn_items[-HOT_WINDOW:]:
            ctx.turns.append(
                ConversationTurn(
                    turn_index=int(item.get("turn_index", {}).get("N", "0")),
                    question=item.get("question", {}).get("S", ""),
                    answer=item.get("answer", {}).get("S", ""),
                    sql=item.get("sql", {}).get("S", ""),
                    row_count=int(item.get("row_count", {}).get("N", "0")),
                    ts=item.get("ts", {}).get("S", ""),
                )
            )

        return ctx

    def add_turn(
        self,
        session_id: str,
        persona: str,
        question: str,
        answer: str,
        sql: str,
        row_count: int,
    ) -> int:
        """
        Persist one conversation turn to DynamoDB.
        Returns the new turn index (1-based), or 0 on failure.
        Triggers compaction when the session crosses COMPACT_AT turns.
        """
        try:
            current_count = self._get_turn_count(session_id)
            new_index = current_count + 1
            sk = f"turn#{new_index:04d}"

            item: dict[str, Any] = {
                "session_id": {"S": session_id},
                "sk": {"S": sk},
                "turn_index": {"N": str(new_index)},
                "persona": {"S": persona},
                "question": {"S": question[:2000]},
                "answer": {"S": answer[:2000]},
                "sql": {"S": sql[:4000]},
                "row_count": {"N": str(row_count)},
                "ts": {"S": self._now_iso()},
                "ttl": {"N": str(self._ttl())},
            }
            self._ddb.put_item(TableName=self._table, Item=item)
            logger.debug(f"Memory {sk} written for session {session_id}")

            # Compact on the turn immediately after every COMPACT_AT boundary
            if new_index > COMPACT_AT and (new_index - HOT_WINDOW) % COMPACT_AT == 1:
                try:
                    self._summarize_and_compact(session_id)
                except Exception as e:
                    logger.warning(f"Compaction skipped (non-fatal): {e}")

            return new_index
        except Exception as e:
            logger.error(f"Memory write failed for session {session_id}: {e}")
            return 0

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _query_session(self, session_id: str) -> list[dict[str, Any]]:
        resp = self._ddb.query(
            TableName=self._table,
            KeyConditionExpression="session_id = :sid",
            ExpressionAttributeValues={":sid": {"S": session_id}},
        )
        return resp.get("Items", [])

    def _get_turn_count(self, session_id: str) -> int:
        items = self._query_session(session_id)
        return sum(1 for i in items if i.get("sk", {}).get("S", "").startswith("turn#"))

    def _summarize_and_compact(self, session_id: str) -> None:
        """
        Summarize older turns with Bedrock and upsert a 'summary' item.
        Original turn items are kept for audit purposes.
        """
        items = self._query_session(session_id)
        turn_items = sorted(
            [i for i in items if i.get("sk", {}).get("S", "").startswith("turn#")],
            key=lambda i: i["sk"]["S"],
        )

        # Summarize everything outside the hot window
        to_summarize = turn_items[:-HOT_WINDOW] if len(turn_items) > HOT_WINDOW else []
        if not to_summarize:
            return

        history_text = "\n".join(
            f"Turn {i.get('turn_index', {}).get('N', '?')}: "
            f"Q: {i.get('question', {}).get('S', '')} | "
            f"A: {i.get('answer', {}).get('S', '')[:300]}"
            for i in to_summarize
        )

        resp = self._bedrock.invoke_model(
            modelId=settings.bedrock_model_id,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 400,
                "system": (
                    "You summarize analytics conversation history. "
                    "Preserve entity names, table names, filters, metrics, and key findings. "
                    "Be concise — 3 to 5 sentences maximum."
                ),
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"Summarize this conversation history:\n\n{history_text}"
                        ),
                    }
                ],
            }),
            contentType="application/json",
            accept="application/json",
        )
        summary_text = json.loads(resp["body"].read())["content"][0]["text"]
        last_turn = int(to_summarize[-1].get("turn_index", {}).get("N", "0"))

        self._ddb.put_item(
            TableName=self._table,
            Item={
                "session_id": {"S": session_id},
                "sk": {"S": "summary"},
                "content": {"S": summary_text},
                "summarized_through_turn": {"N": str(last_turn)},
                "ts": {"S": self._now_iso()},
                "ttl": {"N": str(self._ttl())},
            },
        )
        logger.info(f"Session {session_id} compacted through turn {last_turn}")

    def _now_iso(self) -> str:
        return datetime.now(tz=timezone.utc).isoformat()

    def _ttl(self) -> int:
        return int(time.time()) + TTL_30_DAYS
