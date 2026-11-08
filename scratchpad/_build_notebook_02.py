"""Generate 02_nl_chat_walkthrough.ipynb programmatically to avoid JSON escape issues."""
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

def md(id_, text):
    return {"cell_type": "markdown", "id": id_, "metadata": {}, "source": [text]}

def code(id_, text):
    return {
        "cell_type": "code", "id": id_, "metadata": {},
        "execution_count": None, "outputs": [],
        "source": [text]
    }

cells = []

# ── Intro ─────────────────────────────────────────────────────────────────────
cells.append(md("intro", """\
# Natural Language → SQL Chat Walkthrough
## How YumBurger Translates a Plain English Question into an Athena Answer

---

### What this notebook covers

When a business user asks *"Who are the top 10 customers by revenue?"*, the system must:

1. Understand what `'revenue'` and `'top customers'` mean in this database schema
2. Build a precise SQL prompt enriched with schema + ontology context
3. Ask an LLM (Amazon Bedrock) to generate the SQL
4. **Verify** the SQL is safe — this is the critical security step
5. Assume the correct IAM persona role (least privilege)
6. Execute the SQL against Athena, enforced by Lake Formation
7. Return structured results and a plain-English summary

This notebook walks through every single step, cell by cell with full explanations.

### The core security invariant

> **LLM-generated SQL is NEVER executed directly.**
> The SQL must pass AST parsing, keyword checks, and table allowlist
> verification before it touches Athena. Lake Formation then enforces
> column and row permissions on top.

```
Question
  │
  ▼
Schema context  (Athena DESCRIBE)
  │
  ▼
Ontology hints  (Athena SELECT from semantic tables)
  │
  ▼
Bedrock LLM  →  raw SQL  (never executed directly)
  │
  ▼
SQLGlot AST verifier  ──  REJECTED → safe error returned
  │  APPROVED
  ▼
STS AssumeRole  (persona credentials, 15-min TTL)
  │
  ▼
Athena Engine v3  →  Lake Formation check  →  S3 Iceberg
  │
  ▼
Results  →  Bedrock summarization  →  Plain-English Answer
```

---

### Prerequisites
- AWS credentials configured (`aws configure`)
- YumBurger infrastructure deployed and Iceberg tables loaded
- Python packages: `boto3`, `sqlglot`, `pandas`, `python-dotenv`

```bash
pip install boto3 sqlglot pandas python-dotenv
```
"""))

# ── Setup ─────────────────────────────────────────────────────────────────────
cells.append(md("setup-hdr", """\
---
## 0 — Setup & Configuration

Import libraries and set configuration constants.
In production these values come from `.env` and `config/settings.yaml`.
"""))

cells.append(code("setup", """\
import sys, os, re, json, time
sys.path.insert(0, os.path.abspath('..'))

import boto3
import sqlglot
import sqlglot.expressions as exp
import pandas as pd
from dotenv import load_dotenv

load_dotenv('../.env')   # loads BEDROCK_MODEL_ID and AWS_PROFILE

# ── Configuration ─────────────────────────────────────────────────────────────
AWS_REGION          = 'us-east-1'
SILVER_DB           = 'yumburger_silver'
SEMANTIC_DB         = 'yumburger_semantic'
WORKGROUP           = 'yumBurger-wg'
RESULTS_BUCKET      = 'yumburger-athena-results-442042510197'
ACCOUNT_ID          = '442042510197'
ALLOWED_TABLES      = ['supplier', 'menu_item', 'customer', 'order', 'order_line']
BEDROCK_MODEL_ID    = os.environ.get('BEDROCK_MODEL_ID',
                                     'us.anthropic.claude-haiku-4-5-20251001-v1:0')

ROLE_MAP = {
    'analyst': f'arn:aws:iam::{ACCOUNT_ID}:role/yumBurger-persona-analyst',
    'admin'  : f'arn:aws:iam::{ACCOUNT_ID}:role/yumBurger-persona-admin',
}

# SQL keywords that are NEVER allowed in LLM-generated output
FORBIDDEN_KEYWORDS = {
    'INSERT','UPDATE','DELETE','DROP','CREATE','ALTER',
    'TRUNCATE','GRANT','REVOKE','EXEC','EXECUTE','MERGE','CALL','LOAD','COPY'
}

# ── AWS Clients (ambient session — connector-runtime role in ECS, profile locally)
session        = boto3.Session(region_name=AWS_REGION)
athena_client  = session.client('athena')
bedrock_client = session.client('bedrock-runtime')
sts_client     = session.client('sts')

print('Setup complete')
print(f'  Bedrock model : {BEDROCK_MODEL_ID}')
print(f'  Silver DB     : {SILVER_DB}')
"""))

# ── Athena helper ─────────────────────────────────────────────────────────────
cells.append(md("athena-hdr", """\
---
## 0.1 — Athena Query Helper

Every Athena interaction follows the same three-step pattern:
1. **Submit** — `start_query_execution`, get back an execution ID
2. **Poll** — check `get_query_execution` until state is `SUCCEEDED` or `FAILED`
3. **Fetch** — paginate through `get_query_results`, convert rows to dicts

We wrap this in a helper so every step below stays readable.
The helper accepts an optional `client` argument so we can later swap in
a **persona session** instead of the default session.
"""))

cells.append(code("athena-helper", """\
def run_athena(sql: str, database: str = SILVER_DB,
               client=None, timeout: int = 60) -> list:
    \"\"\"Execute SQL via Athena and return rows as list of dicts.\"\"\"
    c = client or athena_client

    resp = c.start_query_execution(
        QueryString=sql,
        WorkGroup=WORKGROUP,
        QueryExecutionContext={'Database': database},
        ResultConfiguration={
            'OutputLocation': f's3://{RESULTS_BUCKET}/notebook-scratch/'
        }
    )
    exec_id = resp['QueryExecutionId']
    print(f'  QueryExecutionId: {exec_id}')

    deadline = time.time() + timeout
    while time.time() < deadline:
        result = c.get_query_execution(QueryExecutionId=exec_id)
        state  = result['QueryExecution']['Status']['State']
        if state == 'SUCCEEDED':
            break
        if state in ('FAILED', 'CANCELLED'):
            reason = result['QueryExecution']['Status'].get('StateChangeReason', 'unknown')
            raise RuntimeError(f'Athena {state}: {reason}')
        time.sleep(1)
    else:
        raise TimeoutError(f'Query timed out after {timeout}s')

    paginator = c.get_paginator('get_query_results')
    rows, columns, first_page = [], [], True
    for page in paginator.paginate(QueryExecutionId=exec_id):
        result_rows = page['ResultSet']['Rows']
        if first_page:
            columns     = [col['VarCharValue'] for col in result_rows[0]['Data']]
            result_rows = result_rows[1:]     # skip the header row
            first_page  = False
        for row in result_rows:
            values = [d.get('VarCharValue') for d in row['Data']]
            rows.append(dict(zip(columns, values)))
    return rows

print('run_athena helper defined')
"""))

# ── Step 1 ────────────────────────────────────────────────────────────────────
cells.append(md("step1-hdr", """\
---
## Step 1 — Ask the Question

Everything starts with a plain English question from the user.
No SQL knowledge required.

Try any of these (or write your own):

| Question | What it exercises |
|---|---|
| `'Who are the top 10 customers by total revenue?'` | JOIN, aggregation, ORDER BY |
| `'What is total revenue by region?'` | GROUP BY, ontology mapping |
| `'Which menu items contain gluten?'` | String filter, allergen column |
| `'How many active suppliers do we have?'` | COUNT, WHERE filter |
| `'What are the 5 most expensive menu items?'` | ORDER BY, LIMIT |
"""))

cells.append(code("question", """\
# Change this line to try a different question
QUESTION = 'Who are the top 10 customers by total revenue?'
PERSONA  = 'analyst'   # 'analyst' or 'admin'

print('Question :', QUESTION)
print('Persona  :', PERSONA)
"""))

# ── Step 2 ────────────────────────────────────────────────────────────────────
cells.append(md("step2-hdr", """\
---
## Step 2 — Load Schema Context from Athena

Before asking Bedrock to generate SQL, we must give it the **database schema**.
Without this the LLM would hallucinate column names, join keys, and table names.

We run `DESCRIBE <table>` for each allowed table via Athena and collect
the column definitions. This context is embedded directly in the Bedrock prompt.

> **Production note:** The connector caches the schema at startup so it only
> runs these 5 DESCRIBE queries once, not on every user request.
"""))

cells.append(code("load-schema", """\
print('Loading schema context from Athena ...')
schema_context = {}

for table in ALLOWED_TABLES:
    print(f'  DESCRIBE {table} ...')
    rows = run_athena(f'DESCRIBE {SILVER_DB}.{table}', database=SILVER_DB)
    # Filter out Iceberg internal metadata rows (they start with '#')
    schema_context[table] = [
        {'col_name': r['col_name'], 'data_type': r['data_type']}
        for r in rows
        if r.get('col_name') and not r['col_name'].startswith('#')
    ]

print('\\nSchema loaded:')
for t, cols in schema_context.items():
    names = [c['col_name'] for c in cols]
    print(f'  {t:<15} -> {names}')
"""))

# ── Step 3 ────────────────────────────────────────────────────────────────────
cells.append(md("step3-hdr", """\
---
## Step 3 — Resolve Ontology Hints

The schema tells Bedrock *what columns exist* but not *what business words mean*.
The ontology fills this gap.

We scan the user question for words that appear in the `ontology_mapping` table.
Each match provides a `hint` — a plain-text explanation that Bedrock receives
alongside the schema.

**Example:** the word `'revenue'` might map to:
```
nl_term: revenue
maps_to_table: order_line
maps_to_column: unit_price
hint: Revenue = SUM(order_line.unit_price * order_line.quantity)
```

This tells Bedrock exactly what SQL expression to use — no guessing.
"""))

cells.append(code("load-ontology", """\
print('Loading ontology mappings from Athena ...')
all_mappings = run_athena(
    'SELECT * FROM ontology_mapping ORDER BY nl_term',
    database=SEMANTIC_DB
)
print(f'  {len(all_mappings)} total mappings loaded')
"""))

cells.append(code("resolve-hints", """\
def resolve_ontology_hints(question: str, mappings: list) -> list:
    \"\"\"Return ontology rows whose nl_term appears in the question.\"\"\"
    q_lower = question.lower()
    return [
        m for m in mappings
        if (m.get('nl_term') or '').lower().strip() and
           (m.get('nl_term') or '').lower().strip() in q_lower
    ]

ontology_hints = resolve_ontology_hints(QUESTION, all_mappings)

if ontology_hints:
    print(f'Resolved {len(ontology_hints)} ontology hint(s):')
    df_hints = pd.DataFrame(ontology_hints)
    display(df_hints[['nl_term', 'maps_to_table', 'maps_to_column', 'hint']].fillna(''))
else:
    print('No specific ontology matches — LLM will use schema context alone')
"""))

# ── Step 4 ────────────────────────────────────────────────────────────────────
cells.append(md("step4-hdr", """\
---
## Step 4 — Build the Bedrock Prompt

We now combine all context into a structured prompt:

| Part | Content |
|---|---|
| **System prompt** | Strict rules: SELECT only, no DDL, use provided tables only |
| **Schema context** | Column definitions for all 5 silver tables (JSON) |
| **Ontology hints** | Business-term → column mappings relevant to this question |
| **User question** | The plain-English question from Step 1 |

The richer the context, the more accurate and consistent the generated SQL.
"""))

cells.append(code("build-prompt", """\
SYSTEM_PROMPT = (
    "You are a SQL query generator for YumBurger restaurant analytics.\\n"
    "Generate ONLY a single SELECT query. No explanations, no markdown, just the raw SQL.\\n"
    "\\n"
    "Rules:\\n"
    "- Use only the tables and columns provided in the schema context\\n"
    "- Never use INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, or any DDL/DML\\n"
    "- Always use table aliases\\n"
    "- Limit results to 1000 rows maximum unless the question specifies a count\\n"
    "- Use LOWER() for case-insensitive string comparisons\\n"
    f"- Database: {SILVER_DB}\\n"
)

schema_str = json.dumps(schema_context, indent=2)
hints_str  = json.dumps(ontology_hints[:20], indent=2) if ontology_hints else '[]'

USER_PROMPT = (
    "Schema context (table -> columns):\\n"
    + schema_str
    + "\\n\\nOntology hints (natural language -> table/column mappings):\\n"
    + hints_str
    + f"\\n\\nQuestion: {QUESTION}\\n"
    + "\\nGenerate a single SELECT SQL query to answer this question.\\n"
    + f"Database: {SILVER_DB}\\n"
    + "Return ONLY the SQL query, nothing else."
)

print('=== SYSTEM PROMPT ===')
print(SYSTEM_PROMPT)
print('=== USER PROMPT (first 600 chars) ===')
print(USER_PROMPT[:600], '...')
print(f'\\nTotal prompt length: {len(USER_PROMPT):,} characters')
"""))

# ── Step 5 ────────────────────────────────────────────────────────────────────
cells.append(md("step5-hdr", """\
---
## Step 5 — Call Bedrock → Get Raw SQL

We send the prompt to Amazon Bedrock using the Messages API format.

The model is instructed to return **only the SQL** — no explanations, no markdown.
After the call we strip any accidental formatting just in case.

> **Important:** This SQL output is **not yet safe to run**.
> It is raw LLM output and must pass the verifier in Step 6 before we can trust it.
"""))

cells.append(code("call-bedrock", """\
print(f'Calling Bedrock ({BEDROCK_MODEL_ID}) ...')
t0 = time.time()

body = {
    'anthropic_version': 'bedrock-2023-05-31',
    'max_tokens': 1024,
    'system': SYSTEM_PROMPT,
    'messages': [
        {'role': 'user', 'content': USER_PROMPT}
    ]
}

response   = bedrock_client.invoke_model(
    modelId=BEDROCK_MODEL_ID,
    body=json.dumps(body),
    contentType='application/json',
    accept='application/json'
)
result     = json.loads(response['body'].read())
raw_sql    = result['content'][0]['text']
bedrock_ms = int((time.time() - t0) * 1000)

print(f'  Bedrock responded in {bedrock_ms} ms')
print(f'  Input tokens  : {result.get("usage", {}).get("input_tokens", "n/a")}')
print(f'  Output tokens : {result.get("usage", {}).get("output_tokens", "n/a")}')
print()
print('=== RAW LLM OUTPUT (before verification) ===')
print(raw_sql)
"""))

cells.append(code("strip-md", """\
# Strip markdown code fences in case the LLM added them despite instructions
cleaned_sql = re.sub(r'```sql\\s*', '', raw_sql, flags=re.IGNORECASE)
cleaned_sql = re.sub(r'```\\s*',    '', cleaned_sql).strip()

print('=== CLEANED SQL (stripped markdown) ===')
print(cleaned_sql)
"""))

# ── Step 6 ────────────────────────────────────────────────────────────────────
cells.append(md("step6-hdr", """\
---
## Step 6 — Verify SQL with SQLGlot AST

This is the **most important security step** in the entire pipeline.
We never trust LLM output directly.

The verifier runs four checks in sequence:

| Check | What it prevents |
|---|---|
| **Forbidden keyword scan** | `DROP TABLE`, `DELETE FROM`, `INSERT INTO`, etc. |
| **AST parse** | Malformed SQL or SQL injection tricks that bypass keyword scan |
| **SELECT-only check** | Any statement type other than SELECT |
| **Table allowlist** | Queries referencing tables outside the approved set |

After all checks pass, SQLGlot **regenerates** the SQL in Trino dialect.
This has a critical side effect: reserved-word table names like `order` are
automatically double-quoted as `"order"` so Athena does not misread them as
the SQL keyword ORDER.

If any check fails, the query is **rejected immediately** — no Athena call,
no data access, and a safe error is returned to the user.
"""))

cells.append(code("verifier", """\
class VerificationError(Exception):
    pass


def verify_sql(sql: str, allowed_tables: list, database: str) -> str:
    \"\"\"
    Verify LLM-generated SQL before execution.
    Returns cleaned, safe SQL string or raises VerificationError.
    \"\"\"
    upper       = sql.upper()
    allowed_set = {t.lower() for t in allowed_tables}

    # Check 1: Forbidden keywords
    for kw in FORBIDDEN_KEYWORDS:
        if re.search(rf'\\b{kw}\\b', upper):
            raise VerificationError(f"Forbidden keyword '{kw}' in generated SQL")
    print('  Check 1 PASSED: no forbidden keywords')

    # Check 2: AST parse
    try:
        parsed = sqlglot.parse_one(sql, dialect='trino')
    except Exception as e:
        raise VerificationError(f'SQL parse error: {e}') from e
    print('  Check 2 PASSED: SQL parses cleanly')

    # Check 3: Must be a SELECT statement
    if not isinstance(parsed, exp.Select):
        raise VerificationError(
            f'Generated SQL is not a SELECT: {type(parsed).__name__}'
        )
    print('  Check 3 PASSED: statement is a SELECT')

    # Check 4: All referenced tables must be in allowlist
    for table in parsed.find_all(exp.Table):
        tname = table.name.lower()
        if tname and tname not in allowed_set:
            raise VerificationError(f"Table not in allowlist: '{tname}'")
    print('  Check 4 PASSED: all tables are in allowlist')

    # Regenerate SQL with Trino dialect (auto-quotes reserved-word table names)
    needs_limit = not parsed.find(exp.Limit)
    try:
        verified = parsed.sql(dialect='trino')
    except Exception:
        verified = sql   # fall back to original if regeneration fails

    if needs_limit:
        verified = verified.rstrip().rstrip(';') + ' LIMIT 1000'
        print('  Note: LIMIT 1000 appended (was missing)')

    return verified


print('Running SQL verification ...')
try:
    verified_sql = verify_sql(cleaned_sql, ALLOWED_TABLES, SILVER_DB)
    print()
    print('=== VERIFIED SQL (safe to execute) ===')
    print(verified_sql)
except VerificationError as e:
    print(f'VERIFICATION FAILED: {e}')
    print('The query will NOT be sent to Athena.')
    raise
"""))

cells.append(md("step6b-hdr", """\
### Why SQLGlot auto-quotes `order`

`ORDER` is a reserved SQL keyword. If the LLM writes `FROM order o`, Athena fails
with a syntax error. SQLGlot's Trino dialect detects this and rewrites it to
`FROM "order" AS o` automatically.
"""))

cells.append(code("quoting-demo", """\
# Demonstrate automatic reserved-word quoting
demo = 'SELECT o.order_id, o.total_amount FROM order o JOIN customer c ON o.customer_id = c.customer_id'
rewritten = sqlglot.parse_one(demo, dialect='trino').sql(dialect='trino')

print('Input  :', demo)
print('Output :', rewritten)
print()
print('Notice: "order" is now double-quoted -> Athena executes correctly')
"""))

# ── Step 7 ────────────────────────────────────────────────────────────────────
cells.append(md("step7-hdr", """\
---
## Step 7 — Assume Persona Role via STS

The connector **does not run queries as itself**. It assumes a short-lived IAM role
via AWS STS (Security Token Service) before calling Athena.

**Why persona roles?**

| Without persona roles | With persona roles |
|---|---|
| All queries run with the same permissions | Each persona has only the permissions it needs |
| A single misconfiguration exposes everything | Blast radius is limited to that persona's scope |
| No differentiation between analyst and admin | Lake Formation can apply different column/row filters per role |

Session credentials expire after **15 minutes**. After that, STS must be called again.
"""))

cells.append(code("assume-role", """\
role_arn = ROLE_MAP[PERSONA]
print(f'Assuming role for persona={PERSONA}: {role_arn}')

t0       = time.time()
sts_resp = sts_client.assume_role(
    RoleArn=role_arn,
    RoleSessionName=f'yumBurger-notebook-{PERSONA}',
    DurationSeconds=900   # 15-minute session
)
creds    = sts_resp['Credentials']
sts_ms   = int((time.time() - t0) * 1000)

persona_session = boto3.Session(
    aws_access_key_id=creds['AccessKeyId'],
    aws_secret_access_key=creds['SecretAccessKey'],
    aws_session_token=creds['SessionToken'],
    region_name=AWS_REGION
)
persona_athena = persona_session.client('athena')

print(f'  Role assumed in {sts_ms} ms')
print(f'  AccessKeyId : {creds["AccessKeyId"]}')
print(f'  Expiration  : {creds["Expiration"]}')
"""))

# ── Step 8 ────────────────────────────────────────────────────────────────────
cells.append(md("step8-hdr", """\
---
## Step 8 — Execute the Verified SQL via Athena

We execute using the **persona client** so Athena passes those credentials to
Lake Formation. Lake Formation applies column-level and row-level access controls
before reading a single byte from S3.

If the persona lacks permission to see a column, that column simply does not appear
in the result — no error, no exception, no data leak.
"""))

cells.append(code("execute", """\
print(f'Executing SQL via Athena as persona={PERSONA} ...')
t0 = time.time()

rows = run_athena(verified_sql, database=SILVER_DB, client=persona_athena)

athena_ms = int((time.time() - t0) * 1000)
print(f'  Query returned {len(rows)} rows in {athena_ms} ms')
"""))

# ── Step 9 ────────────────────────────────────────────────────────────────────
cells.append(md("step9-hdr", """\
---
## Step 9 — Display Results as a DataFrame
"""))

cells.append(code("display-results", """\
if rows:
    df = pd.DataFrame(rows)
    print(f'Result set: {len(df)} rows x {len(df.columns)} columns')
    display(df)
else:
    print('No rows returned.')
"""))

# ── Step 10 ───────────────────────────────────────────────────────────────────
cells.append(md("step10-hdr", """\
---
## Step 10 — Summarize with Bedrock (Plain-English Answer)

The raw data table is not what a business user asked for.
They asked a question; they expect a plain-English answer.

We send the result rows back to Bedrock with a summarization prompt.
The model receives:
- The original question (for context)
- The first 20 rows of results (enough to answer accurately)
- An instruction to respond concisely in business language

This is what the `/ask` endpoint returns as the `answer` field.
"""))

cells.append(code("summarize", """\
BODHI_SYSTEM = (
    "You are a business analytics assistant for YumBurger restaurant chain. "
    "You receive SQL query results and must answer the user's original question in clear, "
    "concise business language. Be specific: include numbers, names, and rankings where "
    "relevant. Keep the answer to 2-4 sentences."
)

results_text = json.dumps(rows[:20], indent=2, default=str) if rows else 'No results.'

summarize_prompt = (
    f"Original question: {QUESTION}\\n\\n"
    f"SQL query results (up to 20 rows):\\n{results_text}\\n\\n"
    "Please answer the original question based on these results."
)

print('Calling Bedrock for plain-English summary ...')
t0 = time.time()

body = {
    'anthropic_version': 'bedrock-2023-05-31',
    'max_tokens': 512,
    'system': BODHI_SYSTEM,
    'messages': [{'role': 'user', 'content': summarize_prompt}]
}
resp       = bedrock_client.invoke_model(
    modelId=BEDROCK_MODEL_ID,
    body=json.dumps(body),
    contentType='application/json',
    accept='application/json'
)
answer     = json.loads(resp['body'].read())['content'][0]['text']
summary_ms = int((time.time() - t0) * 1000)

print(f'  Bedrock responded in {summary_ms} ms')
print()
print('=' * 60)
print('  ANSWER')
print('=' * 60)
print(answer)
"""))

# ── Step 11 ───────────────────────────────────────────────────────────────────
cells.append(md("step11-hdr", """\
---
## Step 11 — Full End-to-End Trace
"""))

cells.append(code("trace", """\
total_ms = bedrock_ms + athena_ms + summary_ms

print('=' * 60)
print('  END-TO-END PIPELINE TRACE')
print('=' * 60)
print(f'  Question          : {QUESTION}')
print(f'  Persona           : {PERSONA}')
print()
print('  Steps:')
print(f'    1  Schema loaded  : {len(ALLOWED_TABLES)} tables via Athena DESCRIBE')
print(f'    2  Ontology hints : {len(ontology_hints)} matched in question')
print(f'    3  Bedrock SQL    : {bedrock_ms} ms')
print(f'    4  SQLGlot verify : PASSED (4/4 checks)')
print(f'    5  STS AssumeRole : {PERSONA} persona')
print(f'    6  Athena execute : {athena_ms} ms  ->  {len(rows)} rows')
print(f'    7  Bedrock summary: {summary_ms} ms')
print()
print(f'  Total latency     : ~{total_ms} ms')
print()
print('  Verified SQL:')
print(f'    {verified_sql}')
print()
print('  Answer:')
print(f'    {answer}')
"""))

# ── Bonus: single function ────────────────────────────────────────────────────
cells.append(md("e2e-hdr", """\
---
## Bonus — Single ask() Function

Now that we understand every step, here is the entire pipeline in one function.
This mirrors what the `/ask` FastAPI endpoint does.
Change the question below and re-run to explore.
"""))

cells.append(code("e2e-fn", """\
def ask(question: str, persona: str = 'analyst', max_rows: int = 20) -> dict:
    \"\"\"Full NL->SQL->Athena->Answer pipeline. Returns dict with answer, sql, row_count.\"\"\"
    t_start = time.time()

    # 1. Schema
    schema = {}
    for table in ALLOWED_TABLES:
        rows_ = run_athena(f'DESCRIBE {SILVER_DB}.{table}', database=SILVER_DB)
        schema[table] = [
            {'col_name': r['col_name'], 'data_type': r['data_type']}
            for r in rows_ if r.get('col_name') and not r['col_name'].startswith('#')
        ]

    # 2. Ontology
    mappings_ = run_athena('SELECT * FROM ontology_mapping', database=SEMANTIC_DB)
    hints_    = resolve_ontology_hints(question, mappings_)

    # 3. Bedrock SQL generation
    sys_p  = (
        "You are a SQL query generator for YumBurger restaurant analytics. "
        "Generate ONLY a single SELECT query. No explanations, no markdown, just SQL. "
        "Never use DDL or DML. Use table aliases. Max 1000 rows. "
        f"Database: {SILVER_DB}"
    )
    usr_p  = (
        "Schema:\\n" + json.dumps(schema, indent=2) +
        "\\n\\nOntology hints:\\n" + json.dumps(hints_[:20], indent=2) +
        f"\\n\\nQuestion: {question}\\nReturn ONLY the SQL."
    )
    body_  = {
        'anthropic_version': 'bedrock-2023-05-31', 'max_tokens': 1024,
        'system': sys_p, 'messages': [{'role': 'user', 'content': usr_p}]
    }
    raw_   = json.loads(bedrock_client.invoke_model(
        modelId=BEDROCK_MODEL_ID, body=json.dumps(body_),
        contentType='application/json', accept='application/json'
    )['body'].read())['content'][0]['text']

    # 4. Clean + verify
    clean_ = re.sub(r'```sql\\s*', '', raw_, flags=re.IGNORECASE)
    clean_ = re.sub(r'```\\s*', '', clean_).strip()
    sql_   = verify_sql(clean_, ALLOWED_TABLES, SILVER_DB)

    # 5. Assume persona role
    creds_ = sts_client.assume_role(
        RoleArn=ROLE_MAP[persona],
        RoleSessionName=f'yumBurger-ask-{persona}',
        DurationSeconds=900
    )['Credentials']
    p_sess_ = boto3.Session(
        aws_access_key_id=creds_['AccessKeyId'],
        aws_secret_access_key=creds_['SecretAccessKey'],
        aws_session_token=creds_['SessionToken'],
        region_name=AWS_REGION
    )

    # 6. Execute
    result_rows_ = run_athena(sql_, database=SILVER_DB, client=p_sess_.client('athena'))

    # 7. Summarize
    sum_body_ = {
        'anthropic_version': 'bedrock-2023-05-31', 'max_tokens': 512,
        'system': (
            "You are a business analytics assistant for YumBurger. "
            "Answer the question concisely in 2-4 sentences using the provided data."
        ),
        'messages': [{'role': 'user', 'content':
            f"Question: {question}\\n\\nData: {json.dumps(result_rows_[:max_rows], default=str)}"
        }]
    }
    answer_ = json.loads(bedrock_client.invoke_model(
        modelId=BEDROCK_MODEL_ID, body=json.dumps(sum_body_),
        contentType='application/json', accept='application/json'
    )['body'].read())['content'][0]['text']

    return {
        'question'    : question,
        'answer'      : answer_,
        'compiled_sql': sql_,
        'row_count'   : len(result_rows_),
        'duration_ms' : int((time.time() - t_start) * 1000)
    }

print('ask() function defined')
"""))

cells.append(code("try1", """\
r = ask('What are the 5 most expensive menu items?')
print('Q:', r['question'])
print('A:', r['answer'])
print('SQL:', r['compiled_sql'])
print(f'({r[\"row_count\"]} rows, {r[\"duration_ms\"]} ms)')
"""))

cells.append(code("try2", """\
r2 = ask('How many active suppliers do we have?')
print('Q:', r2['question'])
print('A:', r2['answer'])
print('SQL:', r2['compiled_sql'])
"""))

cells.append(code("try3", """\
r3 = ask('Which menu items contain gluten?')
print('Q:', r3['question'])
print('A:', r3['answer'])
print('SQL:', r3['compiled_sql'])
"""))

# ── Security demo ─────────────────────────────────────────────────────────────
cells.append(md("sec-hdr", """\
---
## Security Demo — What the Verifier Rejects

Let's prove the verifier works by trying to sneak in malicious SQL.
Every one of these should be caught and rejected.
"""))

cells.append(code("security", """\
attack_cases = [
    ('DROP TABLE attack',    'DROP TABLE yumburger_silver.customer'),
    ('DELETE attack',        'DELETE FROM customer WHERE 1=1'),
    ('Non-allowlist table',  'SELECT * FROM pg_user'),
    ('Non-SELECT statement', 'INSERT INTO customer VALUES (1, \\'hacker\\')'),
    ('Malformed SQL',        'SELECT FROM WHERE;;;'),
]

print('=== SECURITY VERIFICATION TESTS ===')
for label, bad_sql in attack_cases:
    print(f'\\n[{label}]')
    print(f'  Input: {bad_sql}')
    try:
        result_ = verify_sql(bad_sql, ALLOWED_TABLES, SILVER_DB)
        print('  RESULT: !! PASSED (unexpected - check verifier logic)')
    except VerificationError as e:
        print(f'  RESULT: REJECTED correctly -- {e}')
"""))

# ── Conclusion ────────────────────────────────────────────────────────────────
cells.append(md("conclusion", """\
---
## Summary — The 7-Stage Pipeline

```
Stage 1  SCHEMA LOAD    DESCRIBE via Athena (cached at startup)
Stage 2  ONTOLOGY       SELECT from yumburger_semantic tables
Stage 3  PROMPT BUILD   Schema + hints + question -> Bedrock request
Stage 4  BEDROCK        LLM generates candidate SQL (not yet safe)
Stage 5  VERIFY         SQLGlot AST — 4 checks, regenerate with quoting
Stage 6  STS            AssumeRole -> persona credentials (15-min TTL)
Stage 7  ATHENA         Execute -> Lake Formation enforces permissions -> S3
Stage 8  SUMMARIZE      Bedrock generates plain-English answer
```

**Key properties of this design:**

- LLM SQL is **never** executed directly — always verified first
- Persona roles enforce **least privilege** at the data layer
- Schema + ontology context make answers **accurate and consistent**
- Every query is **auditable** — logged to DynamoDB with hashed question + SQL
- Reserved-word tables (`order`) are **auto-quoted** by SQLGlot — no manual workarounds

---
*YumBurger Analytics · NL-to-SQL Chat Prototype*
"""))

# ── Assemble and write ────────────────────────────────────────────────────────
nb = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.11.0"}
    },
    "cells": cells
}

out = "02_nl_chat_walkthrough.ipynb"
with open(out, "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)

print(f"Written: {out}")

# Validate
with open(out, encoding="utf-8") as f:
    json.load(f)
print("JSON validation: OK")
