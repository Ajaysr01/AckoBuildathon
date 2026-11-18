import json
from pathlib import Path

import pytest

from app.specs import SpecError, parse_and_validate, version_from_document


KIT = Path(__file__).resolve().parents[2] / "contract-guard-starter-kit"


def test_parses_json_and_validates_openapi():
    raw = json.dumps({
        "openapi": "3.0.3",
        "info": {"title": "Test", "version": "1.0.0"},
        "paths": {},
    })
    document, errors = parse_and_validate(raw, "test.json")
    assert errors == []
    assert version_from_document(document) == "1.0.0"


def test_reports_unresolved_local_ref_in_claims_spec():
    path = KIT / "specs" / "claims-api" / "2-channel-and-notes.yaml"
    document, errors = parse_and_validate(path.read_text(), path.name)
    assert version_from_document(document) == "1.1.0"
    assert any("ClaimDocumnt" in error and "Unresolved local $ref" in error for error in errors)


def test_resolves_internal_ref():
    document = {
        "openapi": "3.0.3",
        "info": {"title": "Test", "version": "1.0.0"},
        "paths": {},
        "components": {"schemas": {"Item": {"type": "object"}}},
        "x-test": {"$ref": "#/components/schemas/Item"},
    }
    _, errors = parse_and_validate(json.dumps(document), "spec.json")
    assert errors == []


def test_rejects_non_object_spec_root():
    with pytest.raises(SpecError, match="root must be an object"):
        parse_and_validate("[]", "spec.yaml")
