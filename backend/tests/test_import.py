from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


KIT = Path(__file__).resolve().parents[2] / "contract-guard-starter-kit"
test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
Base.metadata.create_all(bind=test_engine)


def override_db():
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


app.dependency_overrides[get_db] = override_db
client = TestClient(app)


def setup_function():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)


def test_import_preserves_duplicate_claims_versions_and_invalid_spec(monkeypatch):
    monkeypatch.setattr("app.main.STARTER_KIT", KIT)
    response = client.post("/api/import/starter-kit")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["imported_specs"] == 12
    assert result["imported_consumers"] == 4
    assert result["invalid_specs"] == 1
    assert any("info.version 1.1.0" in warning and "claims-api" in warning for warning in result["warnings"])
    claims = next(service for service in result["services"] if service["name"] == "claims-api")
    versions = client.get("/api/services/{}/versions".format(claims["id"])).json()
    duplicate_records = [row for row in versions if row["version"] == "1.1.0"]
    assert len(duplicate_records) == 2
    assert {row["source_filename"] for row in duplicate_records} == {
        "2-channel-and-notes.yaml", "3-channel-and-notes-fixed.yaml"
    }
    assert all(row["version_collision"] for row in duplicate_records)
    invalid = next(row for row in versions if row["source_filename"] == "2-channel-and-notes.yaml")
    assert invalid["validation_status"] == "invalid"
    assert any("ClaimDocumnt" in error for error in invalid["validation_errors"])


def test_import_is_idempotent(monkeypatch):
    monkeypatch.setattr("app.main.STARTER_KIT", KIT)
    first = client.post("/api/import/starter-kit").json()
    second = client.post("/api/import/starter-kit").json()
    assert first["imported_specs"] == 12
    assert second["imported_specs"] == 0
    assert client.get("/api/services").status_code == 200


def test_new_upload_rejects_duplicate_without_overwriting(monkeypatch):
    monkeypatch.setattr("app.main.STARTER_KIT", KIT)
    client.post("/api/import/starter-kit")
    quote = next(s for s in client.get("/api/services").json() if s["name"] == "quote-api")
    before = client.get("/api/services/{}/versions".format(quote["id"])).json()
    path = KIT / "specs" / "quote-api" / "1-initial.yaml"
    with path.open("rb") as spec:
        response = client.post("/api/services/{}/versions".format(quote["id"]), files={"file": (path.name, spec, "application/yaml")})
    assert response.status_code == 409
    assert "never overwritten" in response.json()["detail"]["message"]
    after = client.get("/api/services/{}/versions".format(quote["id"])).json()
    assert len(after) == len(before) == 4


def test_upload_rejects_invalid_spec(monkeypatch):
    monkeypatch.setattr("app.main.STARTER_KIT", KIT)
    client.post("/api/import/starter-kit")
    service = next(row for row in client.get("/api/services").json() if row["name"] == "quote-api")
    path = KIT / "specs" / "claims-api" / "2-channel-and-notes.yaml"
    with path.open("rb") as spec:
        response = client.post("/api/services/{}/versions".format(service["id"]), files={"file": (path.name, spec, "application/yaml")})
    assert response.status_code == 422
    assert any("ClaimDocumnt" in error for error in response.json()["detail"]["errors"])


def test_upload_adds_proposed_version_and_can_compare_to_provider_baseline(monkeypatch):
    monkeypatch.setattr("app.main.STARTER_KIT", KIT)
    client.post("/api/import/starter-kit")
    service = next(row for row in client.get("/api/services").json() if row["name"] == "quote-api")
    baseline_id = _version_id("quote-api", "1-initial.yaml")
    document = (KIT / "specs" / "quote-api" / "1-initial.yaml").read_text(encoding="utf-8")
    document = document.replace("version: 1.0.0", "version: 99.0.0", 1)
    response = client.post("/api/services/{}/versions".format(service["id"]),
        files={"file": ("candidate.yaml", document.encode("utf-8"), "application/yaml")})
    assert response.status_code == 201, response.text
    proposed = response.json()
    assert proposed["version"] == "99.0.0"
    comparison = client.get("/api/versions/{}/compare/{}".format(baseline_id, proposed["id"]))
    assert comparison.status_code == 200, comparison.text


def test_manual_service_and_usage_creation_routes_are_removed(monkeypatch):
    monkeypatch.setattr("app.main.STARTER_KIT", KIT)
    client.post("/api/import/starter-kit")
    services = client.get("/api/services").json()
    consumer = next(row for row in services if row["role"] == "consumer")
    assert client.post("/api/services", json={"name": "manual", "role": "provider"}).status_code == 405
    assert client.post("/api/services/{}/usages".format(consumer["id"]), json={}).status_code == 404


def test_upload_rejects_unsupported_file_extension(monkeypatch):
    monkeypatch.setattr("app.main.STARTER_KIT", KIT)
    client.post("/api/import/starter-kit")
    service = next(row for row in client.get("/api/services").json() if row["name"] == "quote-api")
    response = client.post("/api/services/{}/versions".format(service["id"]),
        files={"file": ("spec.txt", b"openapi: 3.0.3", "text/plain")})
    assert response.status_code == 415
    assert "YAML" in response.json()["detail"] and "JSON" in response.json()["detail"]


def _version_id(service_name, filename):
    service = next(s for s in client.get("/api/services").json() if s["name"] == service_name)
    versions = client.get("/api/services/{}/versions".format(service["id"])).json()
    return next(row["id"] for row in versions if row["source_filename"] == filename)


def test_quote_diff_matches_mobile_breakdown_field(monkeypatch):
    monkeypatch.setattr("app.main.STARTER_KIT", KIT)
    client.post("/api/import/starter-kit")
    before = _version_id("quote-api", "2-reorganised.yaml")
    after = _version_id("quote-api", "3-price-lines.yaml")
    result = client.get("/api/versions/{}/compare/{}".format(before, after)).json()
    rename = next(change for change in result["changes"] if change["kind"] == "field_removed" and change["location"].endswith("amount"))
    assert rename["severity"] == "breaking"
    assert any(consumer["name"] == "mobile-app" for consumer in rename["affected_consumers"])
    assert rename["publish_blocked"] is True


def test_schema_component_reorganization_is_not_reported_as_change(monkeypatch):
    monkeypatch.setattr("app.main.STARTER_KIT", KIT)
    client.post("/api/import/starter-kit")
    before = _version_id("quote-api", "1-initial.yaml")
    after = _version_id("quote-api", "2-reorganised.yaml")
    result = client.get("/api/versions/{}/compare/{}".format(before, after)).json()
    findings = result["changes"]
    assert not any(change["kind"] in {"field_added", "field_removed", "type_changed"} and "vehicle" in change["location"] for change in findings)
    assert any(change["kind"] == "path_parameter_renamed" and "/quotes/{id}" in change["location"] for change in findings)


def test_policy_diff_finds_consumer_used_removed_field(monkeypatch):
    monkeypatch.setattr("app.main.STARTER_KIT", KIT)
    client.post("/api/import/starter-kit")
    before = _version_id("policy-api", "2-deprecations.yaml")
    after = _version_id("policy-api", "3-remove-old-fields.yaml")
    result = client.get("/api/versions/{}/compare/{}".format(before, after)).json()
    legacy = next(change for change in result["changes"] if change["kind"] == "field_removed" and change["location"].endswith("legacyCode"))
    assert any(consumer["name"] == "payments-svc" for consumer in legacy["affected_consumers"])


def test_policy_diff_reports_required_field_and_enum_restriction(monkeypatch):
    monkeypatch.setattr("app.main.STARTER_KIT", KIT)
    client.post("/api/import/starter-kit")
    before = _version_id("policy-api", "3-remove-old-fields.yaml")
    after = _version_id("policy-api", "4-endorsement-rules.yaml")
    result = client.get("/api/versions/{}/compare/{}".format(before, after)).json()
    required = next(change for change in result["changes"] if change["kind"] == "field_added" and change["location"].endswith("requestedBy"))
    assert required["publish_blocked"] is True
    assert any(consumer["name"] == "partner-portal" for consumer in required["affected_consumers"])
    enum_change = next(change for change in result["changes"] if change["kind"] == "enum_changed")
    assert enum_change["publish_blocked"] is True
    assert any(consumer["name"] == "partner-portal" for consumer in enum_change["affected_consumers"])


def test_compare_rejects_cross_provider_records(monkeypatch):
    monkeypatch.setattr("app.main.STARTER_KIT", KIT)
    client.post("/api/import/starter-kit")
    quote = _version_id("quote-api", "1-initial.yaml")
    policy = _version_id("policy-api", "1-initial.yaml")
    response = client.get("/api/versions/{}/compare/{}".format(quote, policy))
    assert response.status_code == 422


def test_publish_blocks_consumer_break_and_records_attempt(monkeypatch):
    monkeypatch.setattr("app.main.STARTER_KIT", KIT)
    client.post("/api/import/starter-kit")
    proposed = _version_id("quote-api", "3-price-lines.yaml")
    baseline = _version_id("quote-api", "2-reorganised.yaml")
    response = client.post("/api/versions/{}/publish?baseline_id={}".format(proposed, baseline))
    assert response.status_code == 200
    assert response.json()["outcome"] == "blocked"
    attempts = client.get("/api/publish-attempts").json()
    assert len(attempts) == 1
    assert attempts[0]["outcome"] == "blocked"


def test_publish_allows_safe_version_and_metrics_count_attempts(monkeypatch):
    monkeypatch.setattr("app.main.STARTER_KIT", KIT)
    client.post("/api/import/starter-kit")
    baseline = _version_id("quote-api", "3-price-lines.yaml")
    proposed = _version_id("quote-api", "4-ncb-and-taxes.yaml")
    response = client.post("/api/versions/{}/publish?baseline_id={}".format(proposed, baseline))
    assert response.status_code == 200
    assert response.json()["outcome"] == "published"
    assert client.get("/api/metrics").json()["publish_attempts"] == 1


def test_policy_sunset_block_after_date():
    from datetime import date
    from app.policy import apply_publish_policy

    comparison = {"changes": [{
        "location": "Policy.legacyCode", "severity": "non-breaking", "affected_consumers": [{"name": "payments-svc"}],
        "sunset_date": "2026-11-01",
    }]}
    result = apply_publish_policy(comparison, today=date(2026, 11, 2))
    assert result["allowed"] is False
    assert result["blockers"]


def test_policy_sunset_warns_before_date():
    from datetime import date
    from app.policy import apply_publish_policy

    comparison = {"changes": [{
        "location": "Policy.legacyCode", "severity": "non-breaking", "affected_consumers": [{"name": "payments-svc"}],
        "sunset_date": "2027-06-01",
    }]}
    result = apply_publish_policy(comparison, today=date(2027, 5, 31))
    assert result["allowed"] is True
    assert result["warnings"]


def test_expired_sunset_marker_is_affected_and_blocks(monkeypatch):
    monkeypatch.setattr("app.main.STARTER_KIT", KIT)
    client.post("/api/import/starter-kit")
    baseline = _version_id("policy-api", "1-initial.yaml")
    proposed = _version_id("policy-api", "2-deprecations.yaml")
    comparison = client.get("/api/versions/{}/compare/{}".format(baseline, proposed)).json()
    lifecycle = next(change for change in comparison["changes"] if change.get("sunset_date") == "2026-11-01" and change["location"].endswith("legacyCode"))
    assert any(consumer["name"] == "payments-svc" for consumer in lifecycle["affected_consumers"])
    result = client.post("/api/versions/{}/publish?baseline_id={}".format(proposed, baseline)).json()
    assert result["outcome"] == "blocked"
    blocked_finding = next(finding for finding in result["policy"]["blockers"] if finding.get("sunset_date") == "2026-11-01")
    assert "Sunset date" in result["policy"]["block_reasons"][blocked_finding["location"]]


def test_each_publish_retry_is_added_to_audit(monkeypatch):
    monkeypatch.setattr("app.main.STARTER_KIT", KIT)
    client.post("/api/import/starter-kit")
    baseline = _version_id("quote-api", "3-price-lines.yaml")
    proposed = _version_id("quote-api", "4-ncb-and-taxes.yaml")
    first = client.post("/api/versions/{}/publish?baseline_id={}".format(proposed, baseline))
    second = client.post("/api/versions/{}/publish?baseline_id={}".format(proposed, baseline))
    assert first.status_code == second.status_code == 200
    attempts = client.get("/api/publish-attempts").json()
    assert len(attempts) == 2
    assert attempts[0]["id"] > attempts[1]["id"]
    assert client.get("/api/metrics").json()["publish_attempts"] == 2


def test_dashboard_metrics_endpoint_succeeds():
    response = client.get("/api/metrics")
    assert response.status_code == 200
    assert response.json()["publish_attempts"] == 0
