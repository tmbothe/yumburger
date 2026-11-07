"""Ontology YAML validator."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError, computed_field, field_validator

ONTOLOGY_PATH = Path(__file__).parent / "yumburger.yaml"


class OntologyClass(BaseModel):
    uri: str
    label: str
    comment: str
    maps_to_table: str | None
    nl_terms: list[str]

    @field_validator("uri")
    @classmethod
    def uri_has_prefix(cls, v: str) -> str:
        if ":" not in v:
            raise ValueError(f"URI must have a prefix: {v}")
        return v

    @computed_field
    @property
    def local_name(self) -> str:
        return self.uri.split(":")[-1]


class OntologyProperty(BaseModel):
    uri: str
    label: str
    comment: str
    domain: str
    range: str
    maps_to_column: str | None
    nl_terms: list[str]

    @field_validator("uri")
    @classmethod
    def uri_has_prefix(cls, v: str) -> str:
        if ":" not in v:
            raise ValueError(f"URI must have a prefix: {v}")
        return v

    @computed_field
    @property
    def local_name(self) -> str:
        return self.uri.split(":")[-1]


class OntologyMeta(BaseModel):
    prefix: str
    namespace: str
    version: str
    label: str
    description: str


class Ontology(BaseModel):
    ontology: OntologyMeta
    classes: list[OntologyClass]
    properties: list[OntologyProperty]


def load_ontology(path: Path = ONTOLOGY_PATH) -> dict[str, Any]:
    with open(path) as f:
        return yaml.safe_load(f)


def validate(path: Path = ONTOLOGY_PATH) -> Ontology:
    """Validate the ontology YAML and return a parsed Ontology object."""
    raw = load_ontology(path)
    try:
        onto = Ontology.model_validate(raw)
    except ValidationError as e:
        print(f"Ontology validation failed:\n{e}")
        raise
    # Cross-check: all property domains reference known class URIs
    class_uris = {c.uri for c in onto.classes}
    for prop in onto.properties:
        if prop.domain not in class_uris and not prop.domain.startswith("xsd:"):
            raise ValueError(
                f"Property {prop.uri} has unknown domain: {prop.domain}"
            )
    print(f"Ontology valid: {len(onto.classes)} classes, {len(onto.properties)} properties")
    return onto


if __name__ == "__main__":
    import typer

    app = typer.Typer()

    @app.command()
    def validate_cmd(path: Path = ONTOLOGY_PATH):
        """Validate the ontology YAML."""
        try:
            onto = validate(path)
            print("Validation PASSED")
        except Exception as e:
            print(f"Validation FAILED: {e}")
            sys.exit(1)

    app()
