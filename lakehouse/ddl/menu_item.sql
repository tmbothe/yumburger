-- YumBurger — menu_item Iceberg table DDL

CREATE TABLE IF NOT EXISTS yumburger_silver.menu_item (
    item_id          STRING    COMMENT 'UUID primary key',
    name             STRING    COMMENT 'Menu item name',
    category         STRING    COMMENT 'Menu category: Burger, Chicken, Fish, Sides, Beverages, Desserts, Breakfast, Combo',
    price_usd        DOUBLE    COMMENT 'Current price in USD',
    calories         INT       COMMENT 'Calorie count',
    is_available     BOOLEAN   COMMENT 'Is the item currently available?',
    introduced_date  DATE      COMMENT 'Date item was introduced to menu',
    allergens        STRING    COMMENT 'Comma-separated allergen list'
)
LOCATION 's3://yumburger-silver-442042510197/silver/menu_item/'
TBLPROPERTIES (
    'table_type'      = 'ICEBERG',
    'format'          = 'parquet',
    'write_compression' = 'snappy'
);
