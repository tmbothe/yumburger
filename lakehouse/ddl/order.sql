-- YumBurger — order Iceberg table DDL

CREATE TABLE IF NOT EXISTS yumburger_silver.order (
    order_id        STRING       COMMENT 'UUID primary key',
    customer_id     STRING       COMMENT 'FK -> customer.customer_id',
    location_id     STRING       COMMENT 'Restaurant location ID (LOC-STATE-NNN)',
    order_ts        TIMESTAMP    COMMENT 'Order timestamp (UTC)',
    channel         STRING       COMMENT 'Order channel: In-Store, Drive-Through, Mobile App, Delivery',
    payment_method  STRING       COMMENT 'Payment method',
    region          STRING       COMMENT 'Restaurant region (denormalized)',
    state           STRING       COMMENT 'Restaurant state (denormalized)',
    total_usd       DOUBLE       COMMENT 'Total order value in USD',
    item_count      INT          COMMENT 'Number of line items'
)
PARTITIONED BY (month(order_ts))
LOCATION 's3://yumburger-silver-442042510197/silver/order/'
TBLPROPERTIES (
    'table_type'      = 'ICEBERG',
    'format'          = 'parquet',
    'write_compression' = 'snappy'
);
