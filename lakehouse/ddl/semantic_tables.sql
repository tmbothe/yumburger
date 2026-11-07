-- YumBurger — Semantic ontology tables in yumburger_semantic

CREATE TABLE IF NOT EXISTS yumburger_semantic.ontology_class (
    class_uri     STRING    COMMENT 'Full URI of the OWL class',
    local_name    STRING    COMMENT 'Short name (e.g. MenuItem)',
    label         STRING    COMMENT 'Human-readable label',
    comment       STRING    COMMENT 'Description',
    parent_uri    STRING    COMMENT 'Parent class URI (nullable)',
    maps_to_table STRING    COMMENT 'Silver table this class maps to',
    published_at  TIMESTAMP COMMENT 'When this class was published'
)
LOCATION 's3://yumburger-semantic-442042510197/semantic/ontology_class/'
TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format'     = 'parquet'
);

CREATE TABLE IF NOT EXISTS yumburger_semantic.ontology_property (
    property_uri    STRING    COMMENT 'Full URI of the OWL/SKOS property',
    local_name      STRING    COMMENT 'Short name (e.g. hasPrice)',
    label           STRING    COMMENT 'Human-readable label',
    comment         STRING    COMMENT 'Description',
    domain_uri      STRING    COMMENT 'Domain class URI',
    range_uri       STRING    COMMENT 'Range class or datatype URI',
    maps_to_column  STRING    COMMENT 'Silver column this property maps to (table.column)',
    published_at    TIMESTAMP COMMENT 'When this property was published'
)
LOCATION 's3://yumburger-semantic-442042510197/semantic/ontology_property/'
TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format'     = 'parquet'
);

CREATE TABLE IF NOT EXISTS yumburger_semantic.ontology_mapping (
    mapping_id      STRING    COMMENT 'UUID',
    nl_term         STRING    COMMENT 'Natural language term',
    class_uri       STRING    COMMENT 'Maps to ontology class',
    property_uri    STRING    COMMENT 'Maps to ontology property (nullable)',
    table_name      STRING    COMMENT 'Target silver table',
    column_name     STRING    COMMENT 'Target silver column (nullable)',
    published_at    TIMESTAMP COMMENT 'When this mapping was published'
)
LOCATION 's3://yumburger-semantic-442042510197/semantic/ontology_mapping/'
TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format'     = 'parquet'
);
