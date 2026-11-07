"""
verify_infra.py — Check that all YumBurger AWS resources exist and are tagged.
Run via: make verify-infra
"""

from __future__ import annotations

import sys
from pathlib import Path

import boto3
import yaml

ROOT = Path(__file__).parent.parent
with open(ROOT / "config" / "settings.yaml") as f:
    CFG = yaml.safe_load(f)

REGION = CFG["project"]["region"]
REQUIRED_TAGS = CFG["tags"]

session = boto3.Session(region_name=REGION)

CHECKS: list[tuple[str, callable]] = []
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str):
    def decorator(fn):
        CHECKS.append((name, fn))
        return fn
    return decorator


def _has_required_tags(tags: list[dict]) -> bool:
    tag_dict = {t["Key"]: t["Value"] for t in tags}
    for k, v in REQUIRED_TAGS.items():
        if tag_dict.get(k) != v:
            return False
    return True


@check("S3: raw bucket exists")
def check_raw_bucket():
    s3 = session.client("s3")
    s3.head_bucket(Bucket=CFG["s3"]["raw_bucket"])


@check("S3: silver bucket exists")
def check_silver_bucket():
    s3 = session.client("s3")
    s3.head_bucket(Bucket=CFG["s3"]["silver_bucket"])


@check("S3: semantic bucket exists")
def check_semantic_bucket():
    s3 = session.client("s3")
    s3.head_bucket(Bucket=CFG["s3"]["semantic_bucket"])


@check("S3: athena results bucket exists")
def check_athena_results_bucket():
    s3 = session.client("s3")
    s3.head_bucket(Bucket=CFG["s3"]["athena_results_bucket"])


@check("Athena: workgroup exists")
def check_athena_workgroup():
    athena = session.client("athena")
    wg = athena.get_work_group(WorkGroup=CFG["athena"]["workgroup"])
    assert wg["WorkGroup"]["State"] == "ENABLED"


@check("DynamoDB: audit table exists")
def check_dynamodb_audit_table():
    ddb = session.client("dynamodb")
    table = ddb.describe_table(TableName=CFG["dynamodb"]["audit_table"])
    assert table["Table"]["TableStatus"] == "ACTIVE"


@check("IAM: connector-runtime role exists")
def check_connector_runtime_role():
    iam = session.client("iam")
    iam.get_role(RoleName=CFG["iam"]["connector_runtime_role"])


@check("IAM: persona-analyst role exists")
def check_persona_analyst_role():
    iam = session.client("iam")
    iam.get_role(RoleName=CFG["iam"]["persona_analyst_role"])


@check("IAM: persona-admin role exists")
def check_persona_admin_role():
    iam = session.client("iam")
    iam.get_role(RoleName=CFG["iam"]["persona_admin_role"])


@check("Glue: yumburger_silver database exists")
def check_silver_database():
    glue = session.client("glue")
    glue.get_database(Name=CFG["athena"]["silver_database"])


@check("Glue: yumburger_semantic database exists")
def check_semantic_database():
    glue = session.client("glue")
    glue.get_database(Name=CFG["athena"]["semantic_database"])


def run_all_checks():
    print("YumBurger Infrastructure Verification")
    print("=" * 50)
    all_passed = True
    for name, fn in CHECKS:
        try:
            fn()
            print(f"  [PASS] {name}")
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            all_passed = False

    print("=" * 50)
    if all_passed:
        print("All checks PASSED")
    else:
        print("Some checks FAILED — see above")
        sys.exit(1)


if __name__ == "__main__":
    run_all_checks()
