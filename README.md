# Contract Guard

Contract Guard compares OpenAPI specification versions, shows changes and impact on registered consumers, and applies a publishing gate before a proposed version can be published.

## Run the application

Requirements: Docker with Compose, or Python 3.9+ and Node.js 20.19+ for local development.

From the project root:

```sh
docker compose up --build
```

Open the React application at <http://localhost:5173> and the FastAPI/OpenAPI docs at <http://localhost:8000/docs>. PostgreSQL data is persisted in a Compose volume. Stop with `docker compose down` (data remains in the volume; `docker compose down -v` removes it). If the default ports are occupied, set `WEB_PORT` and/or `API_PORT` before starting Compose. If changing the API port, also set the browser-facing API URL because it is compiled into the frontend image; for example: `API_PORT=8010 VITE_API_URL=http://localhost:8010 docker compose up --build`.

Compose builds three services: PostgreSQL 16 (`db`), the FastAPI backend (`backend/Dockerfile`, Python 3.12 and the pinned packages in `backend/requirements.txt`), and the React frontend (`frontend/Dockerfile`, Node 20.19 for the Vite build, served as static files by Nginx). The API waits for PostgreSQL health before starting; the frontend waits for the API health check and is built once into a production bundle. The browser-facing API URL is passed as the `VITE_API_URL` build argument in `docker-compose.yml`.

To run services locally without containers, start PostgreSQL and set `DATABASE_URL`, then:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn app.main:app --app-dir backend --reload
```

In another terminal:

```sh
cd frontend
npm install
npm run dev
```

SQLite is used by default if `DATABASE_URL` is not set (convenient for local/test runs). The API reads starter-kit data from `../contract-guard-starter-kit` by default; set `STARTER_KIT_PATH` to override.

## Use

1. Choose **Import starter kit** to register the three providers, four consumer declarations, and all 12 supplied spec files.
2. Select a provider and choose exact baseline and proposed records. Duplicate imported Claims `1.1.0` versions remain distinct by filename and can be selected explicitly.
3. Review findings and declared consumer impact. Uploading a regular spec requires YAML/JSON with a valid OpenAPI 3.0.3 document and resolvable local `$ref`s. Duplicate provider/version uploads are rejected; records are never overwritten.
4. Publish a proposed version against the selected baseline. A blocked attempt is recorded in publish history.

Impact is based only on registered consumer declarations. A “no declared consumer affected” result does not imply there are no other consumers.

## API endpoints

- `GET /api/health`
- `GET /api/services`, `POST /api/services`
- `GET /api/services/{service_id}/versions`, `POST /api/services/{service_id}/versions`
- `GET /api/services/{service_id}/usages`, `POST /api/services/{service_id}/usages`
- `POST /api/import/starter-kit`, `GET /api/import/runs`
- `GET /api/versions/{from_id}/compare/{to_id}`
- `POST /api/versions/{version_id}/publish?baseline_id={baseline_id}`
- `GET /api/publish-attempts`, `GET /api/metrics`

The interactive API reference is available at `/docs`.

## Tests

Backend tests:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt pytest
pytest -q backend/tests
```

Frontend production build:

```sh
cd frontend
npm install
npm run build
```

## Current scope and limitations

- Implemented: service registry, starter-kit import, YAML/JSON/OpenAPI structural and local-ref validation, duplicate-version handling, semantic comparison for common OpenAPI schemas/parameters/responses, declared consumer impact, provisional configurable publish policy, publish-attempt history, metrics, and a React UI.
- Imported invalid specs remain visible with errors so import can complete; invalid user uploads are rejected.
- The provisional policy blocks breaking changes affecting declared consumers and blocks expired `x-sunset` elements when still used by a declared consumer. Deprecation/sunset policy is centralized in `backend/app/policy.py` and should be updated to match product-owner guidance.
- Dependency audit reported unresolved high-severity advisories in the Vite toolchain (including `picomatch`); the UI builds, but resolve or document this toolchain risk before external deployment.
- No auth/approval workflow, external `$ref` loading, notifications, or CI integration is included yet. Unsupported OpenAPI constructs and classifier edge cases need further coverage before production use.
- Severity/classification is a heuristic and should be treated as review guidance, not proof of runtime behavior.

## Buildathon documents

- `PLAN.md` — Gate 1 plan
- `PROGRESS.md` — milestone status
- `DECISIONS.md` — assumptions and decisions
- `REVIEW.md` — final self-review (complete before final submission)
