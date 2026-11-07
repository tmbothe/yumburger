"""
YumBurger lakehouse loader.

Steps:
1. Upload Parquet files from data/raw/ to S3 raw bucket
2. Create Iceberg tables via Athena DDL
3. INSERT INTO Iceberg tables from raw Parquet (via Athena CTAS or direct INSERT)
4. Verify row counts
"""

from __future__ import annotations

import sys
from pathlib import Path

import boto3
import yaml

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

with open(ROOT / "config" / "settings.yaml") as f:
    CFG = yaml.safe_load(f)

REGION = CFG["project"]["region"]
RAW_BUCKET = CFG["s3"]["raw_bucket"]
SILVER_BUCKET = CFG["s3"]["silver_bucket"]
WORKGROUP = CFG["athena"]["workgroup"]
SILVER_DB = CFG["athena"]["silver_database"]
RESULTS_BUCKET = CFG["s3"]["athena_results_bucket"]

DDL_DIR = ROOT / "lakehouse" / "ddl"
DATA_DIR = ROOT / "data" / "raw"

TABLES = ["supplier", "menu_item", "customer", "order", "order_line"]


def get_session():
    return boto3.Session(region_name=REGION)


def upload_parquet_files(session: boto3.Session) -> None:
    s3 = session.client("s3")
    print(f"\n==> Uploading Parquet files to s3://{RAW_BUCKET}/raw/")
    for table in TABLES:
        local = DATA_DIR / f"{table}.parquet"
        if not local.exists():
            raise FileNotFoundError(f"Missing {local} — run 'make datagen' first")
        key = f"raw/{table}/{table}.parquet"
        s3.upload_file(str(local), RAW_BUCKET, key)
        size = local.stat().st_size // 1024
        print(f"  Uploaded {table}.parquet ({size} KB) -> s3://{RAW_BUCKET}/{key}")


def run_athena_query(
    session: boto3.Session,
    sql: str,
    database: str | None = None,
    timeout: int = 300,
) -> str:
    import time

    athena = session.client("athena")
    kwargs: dict = {
        "QueryString": sql,
        "WorkGroup": WORKGROUP,
        "ResultConfiguration": {
            "OutputLocation": f"s3://{RESULTS_BUCKET}/load-results/",
        },
    }
    if database:
        kwargs["QueryExecutionContext"] = {"Database": database}

    resp = athena.start_query_execution(**kwargs)
    qid = resp["QueryExecutionId"]

    deadline = __import__("time").time() + timeout
    while __import__("time").time() < deadline:
        result = athena.get_query_execution(QueryExecutionId=qid)
        state = result["QueryExecution"]["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(3)
    else:
        athena.stop_query_execution(QueryExecutionId=qid)
        raise TimeoutError(f"Query timed out: {sql[:80]}")

    if state != "SUCCEEDED":
        reason = result["QueryExecution"]["Status"].get("StateChangeReason", "unknown")
        raise RuntimeError(f"Athena {state}: {reason}\nSQL: {sql[:200]}")

    return qid


def create_iceberg_tables(session: boto3.Session) -> None:
    print(f"\n==> Creating Iceberg tables in {SILVER_DB}")
    for table in TABLES:
        ddl_file = DDL_DIR / f"{table}.sql"
        if not ddl_file.exists():
            print(f"  SKIP {table} — no DDL file found")
            continue
        sql = ddl_file.read_text()
        # Remove SQL comments lines and split
        stmts = [s.strip() for s in sql.split(";") if s.strip()]
        # Strip leading comment lines from each statement
        def _strip_comments(stmt: str) -> str:
            lines = [l for l in stmt.splitlines() if not l.strip().startswith("--")]
            return "\n".join(lines).strip()
        stmts = [_strip_comments(s) for s in stmts]
        for stmt in stmts:
            if len(stmt) < 10:
                continue
            print(f"  Creating {table}...")
            run_athena_query(session, stmt)
            print(f"  Created {table}")


RAW_STAGING_DB = "yumburger_raw"

# Column schemas for staging tables (Glue API format)
_STAGING_SCHEMAS: dict[str, list[dict]] = {
    "supplier": [
        {"Name": "supplier_id", "Type": "string"},
        {"Name": "name", "Type": "string"},
        {"Name": "category", "Type": "string"},
        {"Name": "region", "Type": "string"},
        {"Name": "state", "Type": "string"},
        {"Name": "contact_email", "Type": "string"},
        {"Name": "phone", "Type": "string"},
        {"Name": "active", "Type": "boolean"},
        {"Name": "contract_start", "Type": "date"},
        {"Name": "annual_spend_usd", "Type": "double"},
    ],
    "menu_item": [
        {"Name": "item_id", "Type": "string"},
        {"Name": "name", "Type": "string"},
        {"Name": "category", "Type": "string"},
        {"Name": "price_usd", "Type": "double"},
        {"Name": "calories", "Type": "int"},
        {"Name": "is_available", "Type": "boolean"},
        {"Name": "introduced_date", "Type": "date"},
        {"Name": "allergens", "Type": "string"},
    ],
    "customer": [
        {"Name": "customer_id", "Type": "string"},
        {"Name": "first_name", "Type": "string"},
        {"Name": "last_name", "Type": "string"},
        {"Name": "email", "Type": "string"},
        {"Name": "tier", "Type": "string"},
        {"Name": "region", "Type": "string"},
        {"Name": "state", "Type": "string"},
        {"Name": "signup_date", "Type": "date"},
        {"Name": "birth_year", "Type": "int"},
        {"Name": "total_orders", "Type": "int"},
        {"Name": "lifetime_spend_usd", "Type": "double"},
    ],
    "order": [
        {"Name": "order_id", "Type": "string"},
        {"Name": "customer_id", "Type": "string"},
        {"Name": "location_id", "Type": "string"},
        {"Name": "order_ts", "Type": "timestamp"},
        {"Name": "channel", "Type": "string"},
        {"Name": "payment_method", "Type": "string"},
        {"Name": "region", "Type": "string"},
        {"Name": "state", "Type": "string"},
        {"Name": "total_usd", "Type": "double"},
        {"Name": "item_count", "Type": "int"},
    ],
    "order_line": [
        {"Name": "line_id", "Type": "string"},
        {"Name": "order_id", "Type": "string"},
        {"Name": "item_id", "Type": "string"},
        {"Name": "item_name", "Type": "string"},
        {"Name": "category", "Type": "string"},
        {"Name": "qty", "Type": "int"},
        {"Name": "unit_price", "Type": "double"},
        {"Name": "line_total", "Type": "double"},
    ],
}


def create_staging_database(session: boto3.Session) -> None:
    """Create a non-LF-managed Glue database for raw Parquet staging via Glue API."""
    glue = session.client("glue")
    try:
        glue.create_database(
            DatabaseInput={
                "Name": RAW_STAGING_DB,
                "Description": "Temporary staging database for YumBurger raw Parquet load (not LF-managed)",
            }
        )
        print(f"  Created staging database: {RAW_STAGING_DB}")
    except glue.exceptions.AlreadyExistsException:
        print(f"  Staging database {RAW_STAGING_DB} already exists, continuing.")


def create_staging_tables(session: boto3.Session) -> None:
    """Register raw Parquet files as external tables in the staging DB via Glue API (bypasses LF)."""
    print(f"\n==> Registering raw Parquet as staging tables in {RAW_STAGING_DB}")
    create_staging_database(session)
    glue = session.client("glue")
    for table in TABLES:
        columns = _STAGING_SCHEMAS[table]
        s3_location = f"s3://{RAW_BUCKET}/raw/{table}/"
        try:
            glue.create_table(
                DatabaseName=RAW_STAGING_DB,
                TableInput={
                    "Name": f"{table}_raw",
                    "StorageDescriptor": {
                        "Columns": columns,
                        "Location": s3_location,
                        "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
                        "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
                        "SerdeInfo": {
                            "SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe",
                            "Parameters": {"serialization.format": "1"},
                        },
                        "Compressed": True,
                    },
                    "TableType": "EXTERNAL_TABLE",
                    "Parameters": {"classification": "parquet", "EXTERNAL": "TRUE"},
                },
            )
            print(f"  Registered {table}_raw -> {s3_location}")
        except glue.exceptions.AlreadyExistsException:
            print(f"  {table}_raw already registered, skipping.")


def insert_into_iceberg(session: boto3.Session) -> None:
    print(f"\n==> Inserting data into Iceberg tables")
    for table in TABLES:
        # Quote table name to handle reserved keywords like 'order'
        sql = f'INSERT INTO "{SILVER_DB}"."{table}" SELECT * FROM {RAW_STAGING_DB}.{table}_raw'
        print(f"  Inserting {table}...")
        run_athena_query(session, sql)
        print(f"  Inserted {table}")


def verify_counts(session: boto3.Session) -> None:
    print(f"\n==> Verifying row counts")
    athena = session.client("athena")
    for table in TABLES:
        sql = f'SELECT COUNT(*) AS cnt FROM "{SILVER_DB}"."{table}"'
        qid = run_athena_query(session, sql)
        result = athena.get_query_results(QueryExecutionId=qid)
        rows = result["ResultSet"]["Rows"]
        count = int(rows[1]["Data"][0]["VarCharValue"]) if len(rows) > 1 else 0
        print(f"  {table}: {count:,} rows")


def cleanup_staging(session: boto3.Session) -> None:
    """Drop the temporary staging database and tables via Glue API."""
    print(f"\n==> Cleaning up staging database {RAW_STAGING_DB}")
    glue = session.client("glue")
    for table in TABLES:
        try:
            glue.delete_table(DatabaseName=RAW_STAGING_DB, Name=f"{table}_raw")
            print(f"  Deleted {table}_raw")
        except glue.exceptions.EntityNotFoundException:
            pass
    try:
        glue.delete_database(Name=RAW_STAGING_DB)
        print(f"  Deleted database {RAW_STAGING_DB}")
    except glue.exceptions.EntityNotFoundException:
        pass


def main() -> None:
    print("YumBurger Lakehouse Loader")
    print("=" * 40)
    session = get_session()

    upload_parquet_files(session)
    create_iceberg_tables(session)
    create_staging_tables(session)
    insert_into_iceberg(session)
    verify_counts(session)
    cleanup_staging(session)

    print("\n==> Load complete!")


if __name__ == "__main__":
    main()
