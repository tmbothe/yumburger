-- YumBurger — supplier Iceberg table DDL
-- Execute via Athena workgroup: yumBurger-wg

CREATE TABLE IF NOT EXISTS yumburger_silver.supplier (
    supplier_id      STRING        COMMENT 'UUID primary key',
    name             STRING        COMMENT 'Supplier company name',
    category         STRING        COMMENT 'Supply category: Beef, Chicken, Fish, Produce, Dairy, Bread, Beverages, Packaging',
    region           STRING        COMMENT 'US geographic region',
    state            STRING        COMMENT 'US state code (2-char)',
    contact_email    STRING        COMMENT 'Primary contact email',
    phone            STRING        COMMENT 'Phone number',
    active           BOOLEAN       COMMENT 'Is the supplier active?',
    contract_start   DATE          COMMENT 'Contract start date',
    annual_spend_usd DOUBLE        COMMENT 'Estimated annual spend in USD'
)
LOCATION 's3://yumburger-silver-442042510197/silver/supplier/'
TBLPROPERTIES (
    'table_type'      = 'ICEBERG',
    'format'          = 'parquet',
    'write_compression' = 'snappy'
);
