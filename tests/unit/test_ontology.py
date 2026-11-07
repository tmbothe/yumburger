"""Unit tests for ontology validator."""

from __future__ import annotations

from pathlib import Path

import pytest
from ontology.validator import validate


class TestOntologyValidator:
    def test_validate_passes(self):
        onto = validate()
        assert onto is not None

    def test_classes_present(self):
        onto = validate()
        class_names = {c.local_name for c in onto.classes}
        assert "MenuItem" in class_names
        assert "Supplier" in class_names
        assert "Customer" in class_names
        assert "Order" in class_names

    def test_properties_present(self):
        onto = validate()
        prop_names = {p.local_name for p in onto.properties}
        assert "hasPrice" in prop_names
        assert "hasCalories" in prop_names
        assert "placedBy" in prop_names

    def test_property_domains_reference_known_classes(self):
        onto = validate()
        class_uris = {c.uri for c in onto.classes}
        for prop in onto.properties:
            if not prop.domain.startswith("xsd:"):
                assert prop.domain in class_uris, (
                    f"Property {prop.uri} domain {prop.domain} not in known classes"
                )

    def test_all_classes_have_nl_terms(self):
        onto = validate()
        for cls in onto.classes:
            assert len(cls.nl_terms) > 0, f"Class {cls.uri} has no nl_terms"

    def test_ontology_namespace(self):
        onto = validate()
        assert "yumburger.com" in onto.ontology.namespace

    def test_menu_item_maps_to_table(self):
        onto = validate()
        menu_cls = next(c for c in onto.classes if c.local_name == "MenuItem")
        assert menu_cls.maps_to_table == "menu_item"
