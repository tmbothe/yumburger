"""
sync_bodhi.py — CLI runner for the Bodhi incremental sync.

Usage
-----
  # Normal incremental run (only exports what changed)
  python scripts/sync_bodhi.py

  # Force full re-export regardless of snapshot/hash state
  python scripts/sync_bodhi.py --force

  # Run as a cron job every 15 minutes:
  */15 * * * * cd /app && python scripts/sync_bodhi.py >> logs/bodhi_sync.log 2>&1

Environment
-----------
  Reads .env for AWS_PROFILE / AWS_REGION.
  Connector runtime role assumed automatically via identity.py.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

from connector.bodhi_sync import BodhiSyncEngine
from connector.settings import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("sync_bodhi")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Bodhi incremental metadata + ontology sync")
    p.add_argument(
        "--force",
        action="store_true",
        help="Force full re-export, ignoring snapshot/hash state",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Check what would sync without writing to S3",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    settings = get_settings()

    logger.info("=== Bodhi Sync started ===")
    logger.info(f"force={args.force}  dry_run={args.dry_run}")

    # Use the ambient session (connector runtime role in ECS, or default AWS profile locally)
    import boto3
    session = boto3.Session(region_name=settings.aws_region)

    if args.dry_run:
        logger.info("DRY RUN — no S3 writes will occur.")
        # Still read from Athena so we can report what would change
        from connector.metadata import MetadataPlane
        from connector.ontology import OntologyPlane
        from connector.bodhi_sync import (
            _latest_snapshot_ids,
            _load_manifest,
            _ontology_hash,
            _SYNC_BUCKET,
            _MANIFEST_KEY,
        )
        s3 = session.client("s3", region_name=settings.aws_region)
        manifest = _load_manifest(s3)

        metadata = MetadataPlane(session)
        ontology = OntologyPlane(session)

        current_snapshots = _latest_snapshot_ids(metadata)
        changed = [t for t, s in current_snapshots.items() if manifest["snapshots"].get(t) != s]

        classes = ontology.get_classes()
        props = ontology.get_properties()
        mappings = ontology.get_all_mappings()
        onto_hash = _ontology_hash(classes, props, mappings)
        onto_changed = manifest.get("ontology_hash") != onto_hash

        report = {
            "schema_tables_would_sync": changed,
            "ontology_would_sync": onto_changed,
            "current_snapshots": current_snapshots,
            "manifest_snapshots": manifest["snapshots"],
            "current_ontology_hash": onto_hash,
            "manifest_ontology_hash": manifest.get("ontology_hash"),
        }
        print(json.dumps(report, indent=2, default=str))
        return

    engine = BodhiSyncEngine(session)
    result = engine.run(force=args.force)

    print(json.dumps(result, indent=2, default=str))
    logger.info("=== Bodhi Sync complete ===")


if __name__ == "__main__":
    main()
