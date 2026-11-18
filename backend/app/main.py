import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .compare import compare_specs
from .models import ConsumerUsage, ImportRun, PublishAttempt, Service, SpecVersion
from .policy import apply_publish_policy
from .specs import SpecError, parse_and_validate, version_from_document


ROOT = Path(__file__).resolve().parents[2]
STARTER_KIT = Path(os.getenv("STARTER_KIT_PATH", str(ROOT / "contract-guard-starter-kit")))
Base.metadata.create_all(bind=engine)


def _ensure_schema_compatibility():
    """Add columns introduced after an existing local SQLite database was created."""
    inspector = inspect(engine)
    if "spec_versions" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("spec_versions")}
    dialect = engine.dialect.name
    statements = []
    if "published" not in columns:
        statements.append("ALTER TABLE spec_versions ADD COLUMN published BOOLEAN NOT NULL DEFAULT FALSE")
    if "published_at" not in columns:
        timestamp_type = "TIMESTAMP" if dialect == "postgresql" else "DATETIME"
        statements.append("ALTER TABLE spec_versions ADD COLUMN published_at {}".format(timestamp_type))
    if statements:
        with engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))


_ensure_schema_compatibility()

app = FastAPI(title="Contract Guard", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ServiceCreate(BaseModel):
    name: str
    role: str
    owner: Optional[str] = None


class ConsumerUsageCreate(BaseModel):
    provider_service_id: int
    method: str
    path: str
    sends: List[str] = []
    reads: List[str] = []


def service_json(service: Service):
    return {"id": service.id, "name": service.name, "role": service.role, "owner": service.owner}


def spec_json(spec: SpecVersion):
    return {
        "id": spec.id,
        "service_id": spec.service_id,
        "version": spec.version,
        "source_filename": spec.source_filename,
        "validation_status": spec.validation_status,
        "validation_errors": spec.validation_errors,
        "imported": spec.imported,
        "created_at": spec.created_at.isoformat() + "Z",
    }


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/services")
def list_services(db: Session = Depends(get_db)):
    services = db.query(Service).order_by(Service.role, Service.name).all()
    result = []
    for service in services:
        item = service_json(service)
        item["version_count"] = db.query(SpecVersion).filter(SpecVersion.service_id == service.id).count()
        result.append(item)
    return result


@app.post("/api/services", status_code=201)
def create_service(payload: ServiceCreate, db: Session = Depends(get_db)):
    role = payload.role.lower()
    if role not in {"provider", "consumer"}:
        raise HTTPException(422, "role must be 'provider' or 'consumer'.")
    name = payload.name.strip()
    if not name:
        raise HTTPException(422, "name is required.")
    if db.query(Service).filter(Service.name == name).first():
        raise HTTPException(409, "A service with this name is already registered.")
    service = Service(name=name, role=role, owner=payload.owner)
    db.add(service)
    db.commit()
    db.refresh(service)
    return service_json(service)


@app.get("/api/services/{service_id}/usages")
def list_consumer_usages(service_id: int, db: Session = Depends(get_db)):
    consumer = db.query(Service).filter(Service.id == service_id, Service.role == "consumer").first()
    if not consumer:
        raise HTTPException(404, "Consumer service not found.")
    rows = db.query(ConsumerUsage).filter(ConsumerUsage.consumer_service_id == service_id).all()
    return [{"id": row.id, "provider_service_id": row.provider_service_id, "method": row.method,
             "path": row.path, "sends": row.sends, "reads": row.reads} for row in rows]


@app.post("/api/services/{service_id}/usages", status_code=201)
def register_consumer_usage(service_id: int, payload: ConsumerUsageCreate, db: Session = Depends(get_db)):
    consumer = db.query(Service).filter(Service.id == service_id, Service.role == "consumer").first()
    provider = db.query(Service).filter(Service.id == payload.provider_service_id, Service.role == "provider").first()
    if not consumer:
        raise HTTPException(404, "Consumer service not found.")
    if not provider:
        raise HTTPException(404, "Provider service not found.")
    method = payload.method.strip().upper()
    path = payload.path.strip()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD", "TRACE"}:
        raise HTTPException(422, "method must be a supported HTTP method.")
    if not path.startswith("/"):
        raise HTTPException(422, "path must start with '/'.")
    existing = db.query(ConsumerUsage).filter_by(consumer_service_id=consumer.id,
        provider_service_id=provider.id, method=method, path=path).first()
    if existing:
        raise HTTPException(409, "This consumer usage is already registered.")
    row = ConsumerUsage(consumer_service_id=consumer.id, provider_service_id=provider.id,
                        method=method, path=path, sends=payload.sends, reads=payload.reads)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "consumer_service_id": consumer.id, "provider_service_id": provider.id,
            "method": row.method, "path": row.path, "sends": row.sends, "reads": row.reads}


@app.get("/api/services/{service_id}/versions")
def list_versions(service_id: int, db: Session = Depends(get_db)):
    service = db.query(Service).filter(Service.id == service_id, Service.role == "provider").first()
    if not service:
        raise HTTPException(404, "Provider service not found.")
    specs = db.query(SpecVersion).filter(SpecVersion.service_id == service_id).all()
    specs.sort(key=lambda spec: (_version_sort_key(spec.version), spec.source_filename or ""))
    counts = {}
    for spec in specs:
        counts[spec.version] = counts.get(spec.version, 0) + 1
    result = []
    for spec in specs:
        item = spec_json(spec)
        item["version_collision"] = counts[spec.version] > 1
        result.append(item)
    return result


@app.post("/api/services/{service_id}/versions", status_code=201)
async def upload_version(service_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    service = db.query(Service).filter(Service.id == service_id, Service.role == "provider").first()
    if not service:
        raise HTTPException(404, "Provider service not found.")
    filename = file.filename or "spec.yaml"
    if not filename.lower().endswith((".yaml", ".yml", ".json")):
        raise HTTPException(415, "Upload a YAML (.yaml/.yml) or JSON (.json) OpenAPI file.")
    raw = (await file.read()).decode("utf-8", errors="replace")
    try:
        document, errors = parse_and_validate(raw, filename)
        version = version_from_document(document)
    except SpecError as exc:
        raise HTTPException(422, str(exc))
    if errors:
        raise HTTPException(422, {"message": "The OpenAPI specification is invalid.", "errors": errors})
    collision = db.query(SpecVersion).filter(SpecVersion.service_id == service_id, SpecVersion.version == version).first()
    if collision:
        raise HTTPException(409, {
            "message": "Version {} already exists for {}. Existing records are never overwritten.".format(version, service.name),
            "existing_spec_id": collision.id,
            "suggestion": "Cancel the upload or change info.version to a unique version.",
        })
    spec = SpecVersion(
        service_id=service.id,
        version=version,
        source_filename=filename,
        document=document,
        raw_content=raw,
        validation_status="valid",
        validation_errors=[],
        imported=False,
    )
    db.add(spec)
    db.commit()
    db.refresh(spec)
    return spec_json(spec)


@app.post("/api/import/starter-kit")
def import_starter_kit(db: Session = Depends(get_db)):
    specs_dir = STARTER_KIT / "specs"
    consumers_dir = STARTER_KIT / "consumers"
    if not specs_dir.is_dir() or not consumers_dir.is_dir():
        raise HTTPException(404, "Starter kit not found. Set STARTER_KIT_PATH to its folder.")

    summary = {"imported_specs": 0, "invalid_specs": 0, "imported_consumers": 0, "warnings": [], "errors": []}
    version_index = {}

    for provider_dir in sorted(path for path in specs_dir.iterdir() if path.is_dir()):
        provider = _get_or_create_service(db, provider_dir.name, "provider", _owner_from_first_spec(provider_dir))
        for path in sorted(provider_dir.iterdir()):
            if path.suffix.lower() not in {".yaml", ".yml", ".json"}:
                continue
            raw = path.read_text(encoding="utf-8")
            try:
                document, validation_errors = parse_and_validate(raw, path.name)
                version = version_from_document(document)
            except SpecError as exc:
                message = "{}: {}".format(path.name, exc)
                summary["errors"].append(message)
                # Keep an invalid import visible without inventing a version; filename uniquely identifies it.
                document = {"_invalid_import": True, "filename": path.name}
                version = "invalid:{}".format(path.name)
                validation_errors = [str(exc)]
            version_index[(provider.id, version)] = version_index.get((provider.id, version), 0) + 1
            collision = db.query(SpecVersion).filter(
                SpecVersion.service_id == provider.id,
                SpecVersion.version == version,
                SpecVersion.source_filename == path.name,
            ).first()
            if collision:
                summary["warnings"].append("{} already imported; kept existing record.".format(path.relative_to(STARTER_KIT)))
                continue
            spec = SpecVersion(
                service_id=provider.id,
                version=version,
                source_filename=path.name,
                document=document,
                raw_content=raw,
                validation_status="invalid" if validation_errors else "valid",
                validation_errors=validation_errors,
                imported=True,
            )
            db.add(spec)
            summary["imported_specs"] += 1
            if validation_errors:
                summary["invalid_specs"] += 1
                summary["warnings"].append("{} imported as invalid: {}".format(path.name, "; ".join(validation_errors)))

    db.flush()
    for (provider_id, version), count in version_index.items():
        if count > 1:
            filenames = [row[0] for row in db.query(SpecVersion.source_filename).filter(
                SpecVersion.service_id == provider_id, SpecVersion.version == version
            ).all()]
            summary["warnings"].append("{} has {} imported specs with info.version {}; kept as separate records: {}".format(
                db.get(Service, provider_id).name, count, version, ", ".join(filenames)
            ))

    for consumer_path in sorted(consumers_dir.glob("*.yaml")):
        try:
            import yaml
            data = yaml.safe_load(consumer_path.read_text(encoding="utf-8")) or {}
            name = data.get("consumer")
            if not name:
                summary["errors"].append("{}: missing consumer name.".format(consumer_path.name))
                continue
            team = data.get("team")
            consumer = _get_or_create_service(db, name, "consumer", team)
            for use in data.get("uses", []):
                provider = db.query(Service).filter(Service.name == use.get("provider"), Service.role == "provider").first()
                if not provider:
                    summary["errors"].append("{}: provider '{}' is not registered.".format(consumer_path.name, use.get("provider")))
                    continue
                method = str(use.get("method", "")).upper()
                path = str(use.get("path", ""))
                existing = db.query(ConsumerUsage).filter_by(
                    consumer_service_id=consumer.id, provider_service_id=provider.id,
                    method=method, path=path,
                ).first()
                if existing:
                    continue
                db.add(ConsumerUsage(
                    consumer_service_id=consumer.id,
                    provider_service_id=provider.id,
                    method=method,
                    path=path,
                    sends=use.get("sends", []) or [],
                    reads=use.get("reads", []) or [],
                ))
            summary["imported_consumers"] += 1
        except Exception as exc:
            summary["errors"].append("{}: {}".format(consumer_path.name, exc))

    run = ImportRun(
        imported_specs=summary["imported_specs"],
        invalid_specs=summary["invalid_specs"],
        imported_consumers=summary["imported_consumers"],
        warnings=summary["warnings"],
    )
    db.add(run)
    db.commit()
    summary["import_run_id"] = run.id
    summary["services"] = [service_json(service) for service in db.query(Service).order_by(Service.role, Service.name).all()]
    return summary


@app.get("/api/import/runs")
def list_import_runs(db: Session = Depends(get_db)):
    runs = db.query(ImportRun).order_by(ImportRun.id.desc()).all()
    return [{"id": row.id, "imported_specs": row.imported_specs, "invalid_specs": row.invalid_specs,
             "imported_consumers": row.imported_consumers, "warnings": row.warnings,
             "created_at": row.created_at.isoformat() + "Z"} for row in runs]


@app.get("/api/versions/{from_id}/compare/{to_id}")
def compare_versions(from_id: int, to_id: int, db: Session = Depends(get_db)):
    before = db.query(SpecVersion).filter(SpecVersion.id == from_id).first()
    after = db.query(SpecVersion).filter(SpecVersion.id == to_id).first()
    if not before or not after:
        raise HTTPException(404, "One or both spec versions were not found.")
    try:
        return compare_specs(db, before, after)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.post("/api/versions/{version_id}/publish")
def publish_version(version_id: int, baseline_id: int, db: Session = Depends(get_db)):
    proposed = db.query(SpecVersion).filter(SpecVersion.id == version_id).first()
    baseline = db.query(SpecVersion).filter(SpecVersion.id == baseline_id).first()
    if not proposed or not baseline:
        raise HTTPException(404, "Proposed or baseline spec was not found.")
    try:
        comparison = compare_specs(db, baseline, proposed)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    policy = apply_publish_policy(comparison)
    outcome = "published" if policy["allowed"] else "blocked"
    reason = "Published: no blocking findings for declared consumers." if policy["allowed"] else "Blocked: {} finding(s) affect declared consumers.".format(len(policy["blockers"]))
    attempt = PublishAttempt(
        proposed_spec_id=proposed.id,
        baseline_spec_id=baseline.id,
        outcome=outcome,
        reason=reason,
        findings=policy,
    )
    db.add(attempt)
    if policy["allowed"]:
        proposed.published = True
        proposed.published_at = datetime.utcnow()
    db.commit()
    db.refresh(attempt)
    return {
        "attempt_id": attempt.id,
        "outcome": outcome,
        "reason": reason,
        "policy": policy,
        "proposed_spec_id": proposed.id,
        "baseline_spec_id": baseline.id,
    }


@app.get("/api/publish-attempts")
def list_publish_attempts(db: Session = Depends(get_db)):
    attempts = db.query(PublishAttempt).order_by(PublishAttempt.id.desc()).all()
    return [{"id": row.id, "proposed_spec_id": row.proposed_spec_id, "baseline_spec_id": row.baseline_spec_id,
             "outcome": row.outcome, "reason": row.reason, "findings": row.findings,
             "created_at": row.created_at.isoformat() + "Z"} for row in attempts]


@app.get("/api/metrics")
def metrics(db: Session = Depends(get_db)):
    attempts = db.query(PublishAttempt).all()
    specs = db.query(SpecVersion).all()
    blocked = [row for row in attempts if row.outcome == "blocked"]
    affected = set()
    breaking_attempts = 0
    expired_used_blocks = 0
    for attempt in blocked:
        blockers = (attempt.findings or {}).get("blockers", [])
        if any(finding.get("severity") == "breaking" for finding in blockers):
            breaking_attempts += 1
        for finding in blockers:
            affected.update(item["name"] for item in finding.get("affected_consumers", []))
            if finding.get("sunset_date"):
                expired_used_blocks += 1
    collision_keys = {
        (spec.service_id, spec.version)
        for spec in specs if spec.imported and db.query(SpecVersion).filter(
            SpecVersion.service_id == spec.service_id, SpecVersion.version == spec.version
        ).count() > 1
    }
    return {
        "publish_attempts": len(attempts),
        "published": sum(1 for row in attempts if row.outcome == "published"),
        "blocked": len(blocked),
        "blocked_for_declared_consumer_break": breaking_attempts,
        "affected_declared_consumers": len(affected),
        "expired_used_elements_blocked": expired_used_blocks,
        "invalid_specs": sum(1 for spec in specs if spec.validation_status == "invalid"),
        "version_collisions_detected": len(collision_keys),
    }


def _get_or_create_service(db: Session, name: str, role: str, owner: Optional[str]):
    service = db.query(Service).filter(Service.name == name).first()
    if service:
        if service.role != role:
            raise ValueError("Service {} already exists as {}.".format(name, service.role))
        if owner and not service.owner:
            service.owner = owner
        return service
    service = Service(name=name, role=role, owner=owner)
    db.add(service)
    db.flush()
    return service


def _owner_from_first_spec(provider_dir: Path) -> Optional[str]:
    for path in sorted(provider_dir.glob("*.yaml")):
        match = re.search(r"Owner:\s*([^.'\"]+)", path.read_text(encoding="utf-8"))
        if match:
            return match.group(1).strip()
    return None


def _version_sort_key(version: str):
    """Sort numeric version components numerically, with filename as duplicate tie-breaker."""
    match = re.match(r"^(\d+(?:\.\d+)*)(.*)$", version)
    if not match:
        return (1, version.lower())
    numbers = tuple(int(part) for part in match.group(1).split("."))
    return (0, numbers, match.group(2).lower())
