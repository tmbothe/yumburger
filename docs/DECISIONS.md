# YumBurger — Decisions Log

All verified AWS/library capabilities and limitations are recorded here before
being relied on in code. Format: Date | Decision | Rationale | Verified?

---

## D-001 | Athena as single Iceberg access layer
**Date**: 2026-11-07
**Decision**: All reads from Iceberg tables (data + metadata) go through Athena only.
Direct S3 access is explicitly Denied via IAM for the connector-runtime role.
**Rationale**: Athena enforces Lake Formation column masking and row filters at
execution time. Direct S3 reads would bypass governance entirely.
**Verified**: Lake Formation integration with Athena v3 confirmed in AWS docs.

---

## D-002 | Iceberg $snapshots via Athena
**Date**: 2026-11-07
**Decision**: Use `SELECT * FROM "db"."table$snapshots"` syntax in Athena to query
Iceberg metadata tables (snapshots, history, manifests).
**Rationale**: Athena supports Iceberg metadata tables natively with the `$` syntax.
**Verified**: Confirmed in Athena Iceberg docs — table$snapshots, table$history,
table$manifests, table$refs all supported.

---

## D-003 | LLM-generated SQL never executed directly
**Date**: 2026-11-07
**Decision**: The compiler module generates SQL from NL input using Bedrock, but
the generated SQL is passed through a verifier (AST check, whitelist of allowed
table names and columns) before being handed to the Athena engine.
**Rationale**: Prevents prompt injection, SQL injection, and unauthorized table access.
**Verified**: Implementation requirement — no AWS dependency.

---

## D-004 | Redshift Serverless as Bodhi backend (future)
**Date**: 2026-11-07
**Decision**: Redshift Serverless workgroup is provisioned but paused by default.
It will be used as the Bodhi agent backend in a future phase.
**Rationale**: Scale-to-zero cost model. Only active during demos.
**Verified**: Redshift Serverless pause/resume supported via API.
NOTE: Bodhi integration is out of scope for current POC phases 1-7.

---

## D-005 | CDK Python v2 for all IaC
**Date**: 2026-11-07
**Decision**: AWS CDK v2 (Python) is the only IaC tool. No CloudFormation templates
edited directly. No console changes after initial deploy.
**Rationale**: CLAUDE.md requirement. CDK v2 consolidates all construct libraries
into a single package (aws-cdk-lib).
**Verified**: aws-cdk-lib >= 2.100.0 confirmed compatible with Python 3.11.

---

## D-006 | Lake Formation data lake settings
**Date**: 2026-11-07
**Decision**: Lake Formation "Use only IAM access control" is DISABLED (opt-out of
legacy mode). LF is the authoritative permission system for Glue Catalog resources.
**Rationale**: LF column masking and row filters only work when LF is authoritative.
Legacy IAM-only mode bypasses LF entirely.
**Verified**: AWS docs confirm LF column masking requires LF-managed permissions.

---

## D-007 | Iceberg table format version 2
**Date**: 2026-11-07
**Decision**: All Iceberg tables created with `'format-version' = '2'` and
`'write.delete.mode' = 'merge-on-read'`.
**Rationale**: Format v2 supports row-level deletes (needed for GDPR compliance).
Athena supports Iceberg v2 natively.
**Verified**: Athena Engine v3 supports Iceberg v2 format.

---

## D-008 | DynamoDB for audit log
**Date**: 2026-11-07
**Decision**: Audit events (request_id, persona, query_hash, table, ts, row_count)
written to DynamoDB table `yumBurger-audit` before query execution (pre-audit)
and after (post-audit with result_count).
**Rationale**: DynamoDB is serverless, low-latency, and cost-effective for
high-cardinality write workloads.
**Verified**: DynamoDB on-demand billing, no minimum capacity requirement.

---

## D-009 | Synthetic data scale — "small"
**Date**: 2026-11-07
**Decision**: DATA_SCALE=small targets:
- supplier: 50 rows
- menu_item: 30 rows
- customer: 500 rows
- order: 2,000 rows
- order_line: 6,000 rows
**Rationale**: Minimizes Athena scan cost and S3 storage during POC.
**Verified**: Design decision only.

---

## D-010 | Bedrock model for NL→SQL compiler
**Date**: 2026-11-07
**Decision**: BEDROCK_MODEL_ID is read from .env (not hardcoded). Default:
`anthropic.claude-3-5-sonnet-20241022-v2:0` or similar.
**Rationale**: Model IDs change frequently; externalize to .env for easy swap.
**Verified**: Bedrock InvokeModel API confirmed for Claude models in us-east-1.
