-- YumBurger — customer Iceberg table DDL
-- PII columns: first_name, last_name, email
-- LF column filter hides PII from analyst persona

CREATE TABLE IF NOT EXISTS yumburger_silver.customer (
    customer_id         STRING    COMMENT 'UUID primary key',
    first_name          STRING    COMMENT '[PII] First name',
    last_name           STRING    COMMENT '[PII] Last name',
    email               STRING    COMMENT '[PII] Email address',
    tier                STRING    COMMENT 'Loyalty tier: Bronze, Silver, Gold, Platinum',
    region              STRING    COMMENT 'US geographic region',
    state               STRING    COMMENT 'US state code (2-char)',
    signup_date         DATE      COMMENT 'Loyalty program signup date',
    birth_year          INT       COMMENT 'Birth year (not full DOB)',
    total_orders        INT       COMMENT 'Lifetime order count',
    lifetime_spend_usd  DOUBLE    COMMENT 'Lifetime spend in USD'
)
LOCATION 's3://yumburger-silver-442042510197/silver/customer/'
TBLPROPERTIES (
    'table_type'      = 'ICEBERG',
    'format'          = 'parquet',
    'write_compression' = 'snappy'
);
