"""
dq_check.py — Data quality checks on loaded Iceberg tables.
Runs via Athena. Run via: make dq
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import boto3
import yaml

ROOT = Path(__file__).parent.parent
with open(ROOT / "config" / "settings.yaml") as f:
    CFG = yaml.safe_load(f)

REGION = CFG["project"]["region"]
WORKGROUP = CFG["athena"]["workgroup"]
SILVER_DB = CFG["athena"]["silver_database"]
RESULTS_BUCKET = CFG["s3"]["athena_results_bucket"]

session = boto3.Session(region_name=REGION)
athena = session.client("athena")


def run_query(sql: str) -> list[dict]:
    resp = athena.start_query_execution(
        QueryString=sql,
        WorkGroup=WORKGROUP,
        QueryExecutionContext={"Database": SILVER_DB},
        ResultConfiguration={"OutputLocation": f"s3://{RESULTS_BUCKET}/dq-results/"},
    )
    qid = resp["QueryExecutionId"]
    while True:
        result = athena.get_query_execution(QueryExecutionId=qid)
        state = result["QueryExecution"]["Status"]["State"]
        if state == "SUCCEEDED":
            break
        if state in ("FAILED", "CANCELLED"):
            reason = result["QueryExecution"]["Status"].get("StateChangeReason", "")
            raise RuntimeError(f"Query {state}: {reason}")
        time.sleep(2)
    rows_resp = athena.get_query_results(QueryExecutionId=qid)
    rows = rows_resp["ResultSet"]["Rows"]
    if len(rows) < 2:
        return []
    cols = [c["VarCharValue"] for c in rows[0]["Data"]]
    return [dict(zip(cols, [d.get("VarCharValue") for d in row["Data"]])) for row in rows[1:]]


DQ_CHECKS = [
    # Row count checks
    ("supplier row count >= 1", "SELECT COUNT(*) as cnt FROM supplier", lambda r: int(r[0]["cnt"]) >= 1),
    ("menu_item row count >= 1", "SELECT COUNT(*) as cnt FROM menu_item", lambda r: int(r[0]["cnt"]) >= 1),
    ("customer row count >= 1", "SELECT COUNT(*) as cnt FROM customer", lambda r: int(r[0]["cnt"]) >= 1),
    ("order row count >= 1", 'SELECT COUNT(*) as cnt FROM "order"', lambda r: int(r[0]["cnt"]) >= 1),
    ("order_line row count >= 1", "SELECT COUNT(*) as cnt FROM order_line", lambda r: int(r[0]["cnt"]) >= 1),
    # No null PKs
    ("supplier no null supplier_id", "SELECT COUNT(*) as cnt FROM supplier WHERE supplier_id IS NULL", lambda r: int(r[0]["cnt"]) == 0),
    ("menu_item no null item_id", "SELECT COUNT(*) as cnt FROM menu_item WHERE item_id IS NULL", lambda r: int(r[0]["cnt"]) == 0),
    ("customer no null customer_id", "SELECT COUNT(*) as cnt FROM customer WHERE customer_id IS NULL", lambda r: int(r[0]["cnt"]) == 0),
    ("order no null order_id", 'SELECT COUNT(*) as cnt FROM "order" WHERE order_id IS NULL', lambda r: int(r[0]["cnt"]) == 0),
    # Price > 0
    ("menu_item price > 0", "SELECT COUNT(*) as cnt FROM menu_item WHERE price_usd <= 0", lambda r: int(r[0]["cnt"]) == 0),
    # Referential integrity: order_line.order_id in order
    ("order_line FK to order", """
        SELECT COUNT(*) as cnt FROM order_line ol
        LEFT JOIN "order" o ON ol.order_id = o.order_id
        WHERE o.order_id IS NULL
    """, lambda r: int(r[0]["cnt"]) == 0),
]


def main():
    print("YumBurger Data Quality Checks")
    print("=" * 50)
    all_passed = True
    for name, sql, assertion in DQ_CHECKS:
        try:
            rows = run_query(sql.strip())
            passed = assertion(rows)
            status = "[PASS]" if passed else "[FAIL]"
            if not passed:
                all_passed = False
                print(f"  {status} {name} — got {rows}")
            else:
                print(f"  {status} {name}")
        except Exception as e:
            print(f"  [ERROR] {name}: {e}")
            all_passed = False

    print("=" * 50)
    if all_passed:
        print("All DQ checks PASSED")
    else:
        print("Some DQ checks FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
