"""
Bodhi Sync — incremental export of schema metadata and ontology to S3.

Reads from Athena (silver + semantic zones) and writes versioned JSON payloads
to s3://<audit-bucket>/bodhi-sync/.  A manifest.json tracks the last-seen
Iceberg snapshot ID per table and an ontology content hash so only changed
data is re-exported (incremental).

When the Bodhi API becomes available, replace the S3 upload step with an
API call; the payload format is designed to be API-ready.

S3 layout
---------
bodhi-sync/
  manifest.json                     ← sync state (snapshot IDs + ontology hash)
  metadata/
    schema_<YYYYMMDD_HHMMSS>.json   ← versioned full schema snapshot
    schema_latest.json              ← always the most recent schema
  ontology/
    ontology_<YYYYMMDD_HHMMSS>.json ← versioned full ontology snapshot
    ontology_latest.json            ← always the most recent ontology
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import boto3

from connector.metadata import MetadataPlane
from connector.ontology import OntologyPlane
from connector.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# S3 destination — dedicated prefix inside the Athena results bucket
# (swap for a dedicated bodhi bucket when the API is live)
_SYNC_BUCKET = settings.athena_results_bucket
_SYNC_PREFIX = "bodhi-sync"
_MANIFEST_KEY = f"{_SYNC_PREFIX}/manifest.json"


# ---------------------------------------------------------------------------
# Payload shapes (Bodhi API contract placeholder)
# ---------------------------------------------------------------------------

def _build_schema_payload(
    schema: dict[str, list[dict[str, Any]]],
    snapshots: dict[str, dict[str, Any]],
    sync_id: str,
    synced_at: str,
) -> dict[str, Any]:
    return {
        "payload_type": "schema_metadata",
        "sync_id": sync_id,
        "synced_at": synced_at,
        "source": "athena/yumburger_silver",
        "tables": {
            table: {
                "columns": columns,
                "latest_snapshot": snapshots.get(table),
            }
            for table, columns in schema.items()
        },
    }


def _build_ontology_payload(
    classes: list[dict[str, Any]],
    properties: list[dict[str, Any]],
    mappings: list[dict[str, Any]],
    content_hash: str,
    sync_id: str,
    synced_at: str,
) -> dict[str, Any]:
    return {
        "payload_type": "ontology",
        "sync_id": sync_id,
        "synced_at": synced_at,
        "source": "athena/yumburger_semantic",
        "content_hash": content_hash,
        "classes": classes,
        "properties": properties,
        "mappings": mappings,
    }


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------

def _load_manifest(s3: Any) -> dict[str, Any]:
    """Load the existing manifest from S3, or return an empty one."""
    try:
        obj = s3.get_object(Bucket=_SYNC_BUCKET, Key=_MANIFEST_KEY)
        return json.loads(obj["Body"].read())
    except s3.exceptions.NoSuchKey:
        return {"snapshots": {}, "ontology_hash": None, "last_sync": None}
    except Exception as exc:
        logger.warning(f"Could not load manifest ({exc}); starting fresh.")
        return {"snapshots": {}, "ontology_hash": None, "last_sync": None}


def _save_manifest(s3: Any, manifest: dict[str, Any]) -> None:
    s3.put_object(
        Bucket=_SYNC_BUCKET,
        Key=_MANIFEST_KEY,
        Body=json.dumps(manifest, indent=2, default=str).encode(),
        ContentType="application/json",
    )
    logger.info(f"Manifest saved → s3://{_SYNC_BUCKET}/{_MANIFEST_KEY}")


# ---------------------------------------------------------------------------
# S3 upload helpers
# ---------------------------------------------------------------------------

def _upload_json(s3: Any, key: str, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, indent=2, default=str).encode()
    s3.put_object(Bucket=_SYNC_BUCKET, Key=key, Body=body, ContentType="application/json")
    logger.info(f"Uploaded → s3://{_SYNC_BUCKET}/{key}")


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


# ---------------------------------------------------------------------------
# Incremental checks
# ---------------------------------------------------------------------------

def _latest_snapshot_ids(
    metadata: MetadataPlane,
) -> dict[str, str | None]:
    """Return {table: latest_snapshot_id} for all allowed tables."""
    result: dict[str, str | None] = {}
    for table in settings.allowed_tables:
        try:
            snaps = metadata.get_snapshots(table)
            result[table] = snaps[0].get("snapshot_id") if snaps else None
        except Exception as exc:
            logger.warning(f"Could not fetch snapshots for {table}: {exc}")
            result[table] = None
    return result


def _ontology_hash(
    classes: list[dict],
    properties: list[dict],
    mappings: list[dict],
) -> str:
    combined = json.dumps(
        {"classes": classes, "properties": properties, "mappings": mappings},
        sort_keys=True,
        default=str,
    )
    return hashlib.md5(combined.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Main sync entry point
# ---------------------------------------------------------------------------

class BodhiSyncEngine:
    """
    Reads schema metadata and ontology from Athena and exports changed
    data to S3 as versioned JSON files.
    """

    def __init__(self, session: boto3.Session) -> None:
        self._session = session
        self._metadata = MetadataPlane(session)
        self._ontology = OntologyPlane(session)
        self._s3 = session.client("s3", region_name=settings.aws_region)

    def run(self, force: bool = False) -> dict[str, Any]:
        """
        Execute an incremental sync.

        Parameters
        ----------
        force : bool
            Skip incremental checks and always export everything.

        Returns
        -------
        dict with keys: schema_synced, ontology_synced, skipped, sync_id
        """
        sync_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        manifest = _load_manifest(self._s3)

        result: dict[str, Any] = {
            "sync_id": sync_id,
            "synced_at": now,
            "schema_synced": False,
            "ontology_synced": False,
            "skipped_tables": [],
            "updated_tables": [],
        }

        # ── Schema (incremental by Iceberg snapshot ID) ──────────────────────
        current_snapshots = _latest_snapshot_ids(self._metadata)
        changed_tables = [
            t for t, snap_id in current_snapshots.items()
            if force or manifest["snapshots"].get(t) != snap_id
        ]

        if changed_tables:
            logger.info(f"Schema changed for tables: {changed_tables}")
            schema = self._metadata.get_schema_summary()
            snap_detail: dict[str, Any] = {}
            for table in settings.allowed_tables:
                try:
                    snaps = self._metadata.get_snapshots(table)
                    snap_detail[table] = snaps[0] if snaps else None
                except Exception:
                    snap_detail[table] = None

            payload = _build_schema_payload(schema, snap_detail, sync_id, now)
            ts = _ts()
            _upload_json(self._s3, f"{_SYNC_PREFIX}/metadata/schema_{ts}.json", payload)
            _upload_json(self._s3, f"{_SYNC_PREFIX}/metadata/schema_latest.json", payload)

            # Update manifest
            manifest["snapshots"].update(current_snapshots)
            result["schema_synced"] = True
            result["updated_tables"] = changed_tables
        else:
            logger.info("Schema unchanged — skipping metadata export.")
            result["skipped_tables"] = list(current_snapshots.keys())

        # ── Ontology (incremental by content hash) ───────────────────────────
        classes = self._ontology.get_classes()
        properties = self._ontology.get_properties()
        mappings = self._ontology.get_all_mappings()
        onto_hash = _ontology_hash(classes, properties, mappings)

        if force or manifest.get("ontology_hash") != onto_hash:
            logger.info("Ontology changed — exporting.")
            payload = _build_ontology_payload(
                classes, properties, mappings, onto_hash, sync_id, now
            )
            ts = _ts()
            _upload_json(self._s3, f"{_SYNC_PREFIX}/ontology/ontology_{ts}.json", payload)
            _upload_json(self._s3, f"{_SYNC_PREFIX}/ontology/ontology_latest.json", payload)

            manifest["ontology_hash"] = onto_hash
            result["ontology_synced"] = True
        else:
            logger.info("Ontology unchanged — skipping ontology export.")

        manifest["last_sync"] = now
        _save_manifest(self._s3, manifest)

        logger.info(
            f"Sync complete — schema_synced={result['schema_synced']} "
            f"ontology_synced={result['ontology_synced']}"
        )
        return result
