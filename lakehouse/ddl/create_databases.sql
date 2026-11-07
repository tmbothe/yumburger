-- YumBurger Lakehouse — Create Glue Databases
-- Run via Athena (these are handled by CDK LakeFormationStack, but kept here for reference)

CREATE DATABASE IF NOT EXISTS yumburger_silver
  COMMENT 'YumBurger Iceberg silver zone'
  LOCATION 's3://yumburger-silver-442042510197/silver/';

CREATE DATABASE IF NOT EXISTS yumburger_semantic
  COMMENT 'YumBurger semantic ontology zone'
  LOCATION 's3://yumburger-semantic-442042510197/semantic/';
