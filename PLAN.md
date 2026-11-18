# Contract Guard — Implemented Product Plan
This document describes the product and design that are implemented in this workspace. It is an as-built record, not a list of future work. It explains the implemented user flow, where decisions are made in the code, and why those decisions were chosen.

## 1. Product purpose and current scope
Contract Guard stores provider services and OpenAPI specification versions, compares two valid versions, matches reported changes to declared consumer usage, and records whether a proposed version is published or blocked by policy.

The impact boundary is explicit: a comparison considers only consumer usages registered in Contract Guard. A result with no matched consumer means **no declared consumer was matched**, not that no other consumer exists.

Implemented as core product behavior:
- Provider and consumer service registry, including owner/team metadata.
- Starter-kit import for provider specs and consumer usage declarations.
- YAML/JSON OpenAPI 3.0.3 upload, validation, and listing by internal spec record ID.
- Semantic comparison for common endpoint, parameter, schema, and response changes, including local `$ref` resolution.
- Declared-consumer impact matching and a separate publish policy.
- Publish attempt history and registry metrics.
- React interface for import, registry actions, uploads, comparisons, publish outcomes, audit history, and metrics.
- Docker Compose configuration for PostgreSQL, FastAPI, and a built React frontend served by Nginx.

## 2. User workflow
1. **Start the stack.** The documented command is `docker compose up --build`, configured to build and start PostgreSQL, the API, and frontend. Compose syntax is verified, but a full startup has not been run because Docker was unavailable. Local development can instead run the API and Vite frontend separately; SQLite is the API's default database when `DATABASE_URL` is unset.
2. **Import or register.** The user imports the starter kit or registers services and consumer usage. Import is repeatable: existing source records and usages are retained rather than duplicated.
3. **Choose provider versions.** Versions are selected by internal record ID. The UI also displays the `info.version` value and source filename, so duplicate imported version strings remain distinguishable.
4. **Compare.** A baseline and proposed version for the same provider are compared. Invalid imported records are retained and returned by the versions API, but are excluded from the UI's compare selectors and rejected by the compare API.
5. **Review impact and policy.** Findings identify their location, classification, matched declared consumers, and policy outcome/reason where blocked.
6. **Attempt publish.** The API evaluates the comparison using the policy module and records every attempt (published or blocked). The audit view displays recent attempts and can expand to all records.

## 3. Component responsibilities and decision locations

### API and persistence — `backend/app/main.py`, `backend/app/models.py`, `backend/app/database.py`

- `main.py` exposes the registry, import, upload, compare, publish, history, and metrics routes.
- `models.py` defines the persisted `Service`, `SpecVersion`, `ConsumerUsage`, `ImportRun`, and `PublishAttempt` records.
- `database.py` selects `DATABASE_URL` when provided; otherwise it uses a local SQLite database. SQLAlchemy sessions are provided to API routes through `get_db`.
- API route validation enforces provider/consumer roles, supported methods, leading-slash usage paths, duplicate service names, and valid provider IDs.
- An upload is rejected when parsing/validation fails or when the same provider already has that `info.version`. Existing records are not overwritten.
- Startup creates missing tables and includes a small compatibility migration for the `published` and `published_at` columns on older `spec_versions` databases. This supports previously created local databases without discarding stored records.
- The frontend refreshes services, attempts, and metrics independently. A failing metrics request therefore does not prevent the service list or history from rendering.

### Spec parsing and validation — `backend/app/specs.py`

- YAML is parsed for `.yaml`/`.yml`; JSON is parsed for `.json`. A malformed document or non-object root raises a clear `SpecError`.
- The implemented validator requires OpenAPI `3.0.3`, `info.title`, `info.version`, a `paths` object, object path items, and response maps for operations. It then uses `openapi-spec-validator` for OpenAPI validation.
- Every `$ref` is checked recursively. Local JSON-pointer references must resolve within the same document; external references are rejected rather than fetched.
- `info.version` is display metadata. Database identity is the internal `SpecVersion.id`; source filename is retained to distinguish imported duplicate version strings.
- Normal uploads with errors are rejected. During starter-kit import, invalid specs are stored with `validation_status="invalid"` and validation errors so other files can still import; the versions API returns those records and errors, while compare selection excludes invalid versions.

### Starter-kit import — `backend/app/main.py` (`POST /api/import/starter-kit`)

- The starter-kit location is configured with `STARTER_KIT_PATH`; the default points to `contract-guard-starter-kit` beside the app root.
- Provider directories and supported YAML/JSON files are imported in sorted order. Owner metadata is extracted from the first suitable YAML spec description when available.
- Consumer declarations are parsed from YAML and stored as usage rows with provider, method, path, fields sent, and fields read.
- Import is idempotent by provider + spec version + source filename for specs and by consumer/provider/method/path for usage rows.
- Multiple imported files with the same `info.version` are preserved as separate records and surfaced with warnings. This is necessary for the supplied Claims specs, which intentionally include duplicate `1.1.0` versions.
- Each run persists counts and warnings in `ImportRun`; imported invalid specs do not abort the entire import.

### Semantic comparison and impact — `backend/app/compare.py`

`compare_specs` is the single comparison path used by both the compare API and publish endpoint. It rejects cross-provider comparisons and invalid spec records.

Implemented comparisons include:

- Added/removed operations and route placeholder renames.
- Parameters, including requiredness, schema changes, and path-parameter rename reporting.
- Request and response schemas with local `$ref` resolution, nested properties, arrays/items, types, required fields, enums, common constraints, and response status/body changes.
- Lifecycle metadata findings for deprecated or `x-sunset` operations and schema fields found in proposed request/response shapes.
- `x-internal` status changes for operations.

Consumer matching uses `ConsumerUsage.method` and normalized route shape. Field findings are then matched to `sends` for request changes or `reads` for response changes, with schema-path checks against the consuming operation. Operation removals and selected response removals are treated as impacting all declarations for that endpoint. Every finding lists only matched declared consumers.

Severity is a deterministic heuristic in the comparison code, not an exhaustive proof of runtime compatibility. The checker handles the common constructs above; it does not claim full coverage of every OpenAPI schema feature.

### Publish policy — `backend/app/policy.py`

Comparison and publish policy are separate on purpose. `compare.py` describes observed changes; `apply_publish_policy` decides whether a particular change set is allowed.

The current implemented provisional policy is:

- Block a breaking finding when it impacts at least one declared consumer.
- For a proposed deprecated or `x-sunset` element that is used by a declared consumer, warn before sunset expiry.
- Block a proposed `x-sunset` element after its date has passed if a declared consumer still uses it.
- Do not block lifecycle metadata solely because it exists when no declared consumer is matched.

The policy returns blockers, warnings, a reason for each blocker, and a policy version. The compare endpoint and publish endpoint call the same policy implementation so the review UI reflects the gate's rules. A severity label of `non-breaking` does not itself guarantee publishing: the lifecycle rule can still block an expired sunset element in use.

### Publish history and metrics — `backend/app/main.py`, `backend/app/models.py`

- Each request to `POST /api/versions/{version_id}/publish?baseline_id=...` performs a fresh comparison and policy evaluation, then stores a `PublishAttempt` with outcome, reason, baseline/proposed internal IDs, and policy findings.
- Repeated attempts are separate audit records; the route does not deduplicate retries.
- Allowed attempts mark the proposed spec as published and record `published_at`. Blocked attempts remain visible but do not mark it published.
- `GET /api/publish-attempts` returns attempts newest first. `GET /api/metrics` counts outcomes, affected declared consumers, invalid specs, imported version collisions, and blocked categories.

### React interface — `frontend/src/App.jsx`, `frontend/src/styles.css`

- The interface calls the FastAPI endpoints from the browser. `VITE_API_URL` selects the API base URL; its development default is `http://localhost:8000`.
- Dashboard service, publish history, and metrics requests use independent results so a single failed section does not hide the others.
- Starter-kit import reports a short `Upload Successful` confirmation; detailed import warnings remain available from the API import-run record.
- The interface includes service registration, consumer usage registration, spec upload, provider/version selection, comparison findings, policy reasons, publish actions, metrics, and an expandable audit history.
- The top-level manual refresh control is intentionally not shown; dashboard data loads on application start and is reloaded after import, uploads, and publish attempts.

### Container setup — `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`

- `db` uses PostgreSQL 16 with a named data volume and a `pg_isready` health check.
- `api` builds from `backend/Dockerfile`, installs pinned `backend/requirements.txt`, waits for the database health check, mounts the starter kit read-only, and exposes container port 8000. The host port is configurable with `API_PORT` (default 8000). `DATABASE_URL`, `STARTER_KIT_PATH`, and `FRONTEND_ORIGIN` are set in Compose.
- `web` builds the frontend with Node 20.19 and `npm ci`, then serves the production Vite bundle through Nginx on container port 80, mapped to the configurable `WEB_PORT` (default 5173). It waits for API health. `VITE_API_URL` is passed as a build argument because it is embedded into browser-side assets at build time.
- Both app images define basic health checks. `web` waits for the API health check, and the API waits for database health. Docker Compose startup has been run successfully in this workspace: database/API/web containers reached healthy status, the API health, services, and metrics endpoints returned success, and Nginx returned the frontend HTML. Host ports can be overridden with `API_PORT` and `WEB_PORT`; if the API port changes, set `VITE_API_URL` to the corresponding browser-accessible URL and rebuild the frontend.

## 4. Implemented API surface

- `GET /api/health`
- `GET /api/services`, `POST /api/services`
- `GET /api/services/{service_id}/usages`, `POST /api/services/{service_id}/usages`
- `GET /api/services/{service_id}/versions`, `POST /api/services/{service_id}/versions`
- `POST /api/import/starter-kit`, `GET /api/import/runs`
- `GET /api/versions/{from_id}/compare/{to_id}`
- `POST /api/versions/{version_id}/publish?baseline_id={baseline_id}`
- `GET /api/publish-attempts`, `GET /api/metrics`

## 5. Verification present in the repository

- Backend integration/unit tests are in `backend/tests/` and cover import idempotency, duplicate imported versions, invalid local references, upload rejection, semantic diff cases, consumer impact, publish outcomes, policy/sunset behavior, history accumulation, and metrics.
- The frontend has a production build command (`cd frontend && npm run build`).
- Compose configuration validation is `docker compose config --quiet`.
- The most recently run verification at the time this plan was updated: `21 passed` for `pytest -q backend/tests`; frontend `npm run build` passed; `docker compose config --quiet` passed. Docker image startup was not verified because the Docker daemon was unavailable.
