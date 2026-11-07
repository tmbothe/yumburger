"""Ontology publisher — writes validated ontology to yumburger_semantic Iceberg tables."""

from __future__ import annotations

import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import boto3
import pandas as pd
import yaml

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

with open(ROOT / "config" / "settings.yaml") as f:
    CFG = yaml.safe_load(f)

REGION = CFG["project"]["region"]
RESULTS_BUCKET = CFG["s3"]["athena_results_bucket"]
SEMANTIC_DB = CFG["athena"]["semantic_database"]
SEMANTIC_BUCKET = CFG["s3"]["semantic_bucket"]
WORKGROUP = CFG["athena"]["workgroup"]

from ontology.validator import Ontology, validate


def _run_athena(session: boto3.Session, sql: str, timeout: int = 120) -> str:
    athena = session.client("athena")
    resp = athena.start_query_execution(
        QueryString=sql,
        WorkGroup=WORKGROUP,
        QueryExecutionContext={"Database": SEMANTIC_DB},
        ResultConfiguration={"OutputLocation": f"s3://{RESULTS_BUCKET}/ontology-publish/"},
    )
    qid = resp["QueryExecutionId"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = athena.get_query_execution(QueryExecutionId=qid)
        state = result["QueryExecution"]["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(2)
    if state != "SUCCEEDED":
        reason = result["QueryExecution"]["Status"].get("StateChangeReason", "unknown")
        raise RuntimeError(f"Athena {state}: {reason}\nSQL: {sql[:200]}")
    return qid


def publish(onto: Ontology | None = None) -> None:
    """Publish ontology to yumburger_semantic Iceberg tables."""
    if onto is None:
        onto = validate()

    session = boto3.Session(region_name=REGION)
    s3 = session.client("s3")
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # Build DataFrames
    class_rows = []
    for cls in onto.classes:
        class_rows.append({
            "class_uri": cls.uri,
            "local_name": cls.uri.split(":")[-1],
            "label": cls.label,
            "comment": cls.comment,
            "parent_uri": None,
            "maps_to_table": cls.maps_to_table,
            "published_at": now,
        })

    prop_rows = []
    for prop in onto.properties:
        prop_rows.append({
            "property_uri": prop.uri,
            "local_name": prop.uri.split(":")[-1],
            "label": prop.label,
            "comment": prop.comment,
            "domain_uri": prop.domain,
            "range_uri": prop.range,
            "maps_to_column": prop.maps_to_column,
            "published_at": now,
        })

    mapping_rows = []
    for cls in onto.classes:
        for term in cls.nl_terms:
            mapping_rows.append({
                "mapping_id": str(uuid.uuid4()),
                "nl_term": term,
                "class_uri": cls.uri,
                "property_uri": None,
                "table_name": cls.maps_to_table,
                "column_name": None,
                "published_at": now,
            })
    for prop in onto.properties:
        for term in prop.nl_terms:
            table_col = prop.maps_to_column
            table_name = table_col.split(".")[0] if table_col and "." in table_col else None
            col_name = table_col.split(".")[1] if table_col and "." in table_col else None
            mapping_rows.append({
                "mapping_id": str(uuid.uuid4()),
                "nl_term": term,
                "class_uri": prop.domain,
                "property_uri": prop.uri,
                "table_name": table_name,
                "column_name": col_name,
                "published_at": now,
            })

    # Upload Parquet staging files
    datasets = {
        "ontology_class": pd.DataFrame(class_rows),
        "ontology_property": pd.DataFrame(prop_rows),
        "ontology_mapping": pd.DataFrame(mapping_rows),
    }

    import tempfile
    for table_name, df in datasets.items():
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            df.to_parquet(f.name, index=False, engine="pyarrow")
            staging_key = f"semantic-staging/{table_name}/{table_name}.parquet"
            s3.upload_file(f.name, RESULTS_BUCKET, staging_key)
            print(f"  Staged {table_name}: {len(df)} rows -> s3://{RESULTS_BUCKET}/{staging_key}")

    # INSERT via Athena (using external table as source)
    for table_name in datasets:
        # Create external staging table
        schema_map = {
            "ontology_class": "class_uri STRING, local_name STRING, label STRING, comment STRING, parent_uri STRING, maps_to_table STRING, published_at STRING",
            "ontology_property": "property_uri STRING, local_name STRING, label STRING, comment STRING, domain_uri STRING, range_uri STRING, maps_to_column STRING, published_at STRING",
            "ontology_mapping": "mapping_id STRING, nl_term STRING, class_uri STRING, property_uri STRING, table_name STRING, column_name STRING, published_at STRING",
        }
        create_ext = f"""
            CREATE EXTERNAL TABLE IF NOT EXISTS {SEMANTIC_DB}.{table_name}_staging (
                {schema_map[table_name]}
            )
            STORED AS PARQUET
            LOCATION 's3://{RESULTS_BUCKET}/semantic-staging/{table_name}/'
        """
        _run_athena(session, create_ext)

        # INSERT INTO Iceberg with explicit cast for published_at timestamp
        col_selects = {
            "ontology_class":    "class_uri, local_name, label, comment, parent_uri, maps_to_table, CAST(published_at AS TIMESTAMP) AS published_at",
            "ontology_property": "property_uri, local_name, label, comment, domain_uri, range_uri, maps_to_column, CAST(published_at AS TIMESTAMP) AS published_at",
            "ontology_mapping":  "mapping_id, nl_term, class_uri, property_uri, table_name, column_name, CAST(published_at AS TIMESTAMP) AS published_at",
        }
        select_cols = col_selects[table_name]
        insert = f"INSERT INTO {SEMANTIC_DB}.{table_name} SELECT {select_cols} FROM {SEMANTIC_DB}.{table_name}_staging"
        print(f"  Inserting {table_name}...")
        _run_athena(session, insert)
        print(f"  Inserted {table_name}")

        # Drop staging
        _run_athena(session, f"DROP TABLE IF EXISTS {SEMANTIC_DB}.{table_name}_staging")

    print("Ontology published successfully.")


def export(format: str = "jsonld", output: Path | None = None) -> None:
    """Export ontology to JSON-LD or SKOS Turtle format."""
    onto = validate()
    ns = onto.ontology.namespace

    if format == "jsonld":
        doc = {
            "@context": {
                "yumburger": ns,
                "owl": "http://www.w3.org/2002/07/owl#",
                "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
                "xsd": "http://www.w3.org/2001/XMLSchema#",
            },
            "@graph": [],
        }
        for cls in onto.classes:
            doc["@graph"].append({
                "@id": cls.uri.replace("yumburger:", ns),
                "@type": "owl:Class",
                "rdfs:label": cls.label,
                "rdfs:comment": cls.comment,
            })
        for prop in onto.properties:
            doc["@graph"].append({
                "@id": prop.uri.replace("yumburger:", ns),
                "@type": "owl:ObjectProperty",
                "rdfs:label": prop.label,
                "rdfs:comment": prop.comment,
                "rdfs:domain": {"@id": prop.domain.replace("yumburger:", ns)},
                "rdfs:range": {"@id": prop.range.replace("yumburger:", ns) if "yumburger:" in prop.range else prop.range},
            })
        output_path = output or Path("ontology/export/yumburger.jsonld")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(doc, indent=2))
        print(f"Exported JSON-LD to {output_path}")

    elif format == "skos":
        lines = [
            "@prefix yumburger: <" + ns + "> .",
            "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .",
            "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
            "",
        ]
        for cls in onto.classes:
            local = cls.uri.split(":")[-1]
            lines += [
                f"yumburger:{local} a skos:Concept ;",
                f'    skos:prefLabel "{cls.label}"@en ;',
                f'    skos:definition "{cls.comment}"@en .',
                "",
            ]
        output_path = output or Path("ontology/export/yumburger.skos.ttl")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines))
        print(f"Exported SKOS Turtle to {output_path}")
    else:
        raise ValueError(f"Unknown format: {format}")


if __name__ == "__main__":
    import typer
    app = typer.Typer()

    @app.command()
    def publish_cmd():
        publish()

    @app.command()
    def export_cmd(format: str = "jsonld", output: Path = None):
        export(format=format, output=output)

    app()
