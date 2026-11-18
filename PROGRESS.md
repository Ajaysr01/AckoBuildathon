# Project Status — Contract Guard

Status updated 2026-11-18. This file records implemented behavior and verification already run; it is not a future-work checklist.

## Implemented product

- FastAPI backend with SQLAlchemy persistence; PostgreSQL is used in Docker Compose and SQLite is the default for local development/tests when `DATABASE_URL` is unset.
- Provider and consumer registry, provider OpenAPI versions, consumer usage declarations, and import-run records are populated from the supplied starter kit. Manual service creation and consumer usage creation controls/routes have been removed.
- Repeatable starter-kit import preserves duplicate provider version strings as distinct records with source filename and warnings. Invalid imported specs remain visible with validation errors; normal uploads with validation failures are rejected.
- Spec uploads accept UTF-8 YAML (`.yaml`/`.yml`) and JSON (`.json`) only, require OpenAPI 3.0.3, validate local references, and reject external references. Successful uploads attach to the selected provider and are selected as the proposed version. A valid baseline from that same provider can be compared by record ID.
- Comparison supports common endpoint, route parameter, schema, request/response, lifecycle and `x-internal` findings. Consumer impact is matched against imported declarations only; classification remains heuristic.
- Publish policy, outcome history and metrics are implemented. Policy blocks breaking findings affecting declared consumers and expired `x-sunset` elements still used by declared consumers; it reports upcoming sunset warnings.
- React frontend supports import, service/version selection, upload, comparison, impact review, publish attempts, metrics and audit history.
- Docker Compose contains PostgreSQL 16, FastAPI, and a production-built React app served by Nginx. API waits for database health and frontend waits for API health; `API_PORT` and `WEB_PORT` can change host ports.

## Verification run

- `.venv/bin/pytest -q backend/tests`: **25 passed**, with one local LibreSSL/urllib3 compatibility warning.
- `npm run build` in `frontend`: passed.
- `docker compose config --quiet`: passed.
- `docker compose up --build -d`: latest backend/frontend images built; PostgreSQL, API, and web reported healthy.
- Clean isolated Compose smoke test: imported 12 specs (1 invalid retained), 4 consumer declarations, and 7 services; health/services/metrics API calls and frontend response succeeded. The isolated smoke-test project and its volume were removed afterward.
- Regression tests verify upload-then-compare, unsupported file extension/OpenAPI version rejection, and removal of manual creation routes.

## Current limitations

- Comparison coverage is intentionally incomplete for less-common OpenAPI constructs; severity is a heuristic, not proof of runtime compatibility.
- Impact and policy reflect only the consumer declarations present in the imported starter kit.
- Authentication, authorization, formal approvals, external `$ref` loading, notifications, and CI integration are not implemented.
- Final `npm audit --json` check reports four high-severity findings in the Vite toolchain, including a `picomatch` ReDoS advisory. Build succeeds, but no remediation was applied in this audit.
- The problem-statement transcript requirement is not currently met in the workspace: no `transcripts/` directory/export was found. Supply the genuine OpenCode session export separately if required for assessment; do not fabricate it.

## Scope protection

- Supplied starter-kit specifications, consumer declarations, and webhook receiver remain unmodified.
- Optional notifications, CI integration, and AI migration guidance remain outside the implemented scope.

## Final requirements assessment

- **Met in the tested scope:** shared local `$ref` resolution, core spec comparison and impact reporting, publish gate/history, UI for imported services/versions, metrics endpoint, and one-command Docker Compose runtime.
- **Partial / intentional deviation:** the statement calls for registering services/owners and consumer declarations; the product imports the supplied registry but does not allow manual creation. Classifier coverage is also heuristic and limited to common constructs.
- **Not release-ready for production:** unresolved high-severity frontend dependency advisories and no auth/approval safeguards. Buildathon demo status: ready for the imported starter-kit flow, with the above caveats disclosed.
