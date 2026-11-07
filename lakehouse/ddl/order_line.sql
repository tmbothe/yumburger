-- YumBurger — order_line Iceberg table DDL

CREATE TABLE IF NOT EXISTS yumburger_silver.order_line (
    line_id         STRING    COMMENT 'UUID primary key',
    order_id        STRING    COMMENT 'FK -> order.order_id',
    item_id         STRING    COMMENT 'FK -> menu_item.item_id',
    item_name       STRING    COMMENT 'Menu item name (denormalized)',
    category        STRING    COMMENT 'Menu category (denormalized)',
    qty             INT       COMMENT 'Quantity ordered',
    unit_price      DOUBLE    COMMENT 'Unit price at time of order',
    line_total      DOUBLE    COMMENT 'qty * unit_price'
)
LOCATION 's3://yumburger-silver-442042510197/silver/order_line/'
TBLPROPERTIES (
    'table_type'      = 'ICEBERG',
    'format'          = 'parquet',
    'write_compression' = 'snappy'
);
