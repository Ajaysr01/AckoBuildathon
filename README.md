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

1. Choose **Import starter kit** to register the three providers, four consumer declarations, and all 12 supplied spec files. The import is repeatable and does not duplicate records.
2. Select a provider and choose exact baseline and proposed records. Duplicate imported Claims `1.1.0` versions remain distinct by filename and can be selected explicitly. Services and consumer declarations are sourced from the starter-kit import; manual creation is not available.
3. To add a proposed version, upload a UTF-8 YAML (`.yaml`/`.yml`) or JSON (`.json`) file containing a valid OpenAPI 3.0.3 document with resolvable local `$ref`s. The uploaded version is added to the selected provider and automatically selected as proposed; choose any valid version of that same provider as baseline. Unsupported extensions, invalid specs, cross-provider comparisons, and duplicate provider/version uploads are rejected. Existing records are never overwritten.
4. Publish a proposed version against the selected baseline. A blocked attempt is recorded in publish history.

Impact is based only on registered consumer declarations. A “no declared consumer affected” result does not imply there are no other consumers.

## API endpoints

- `GET /api/health`
- `GET /api/services`
- `GET /api/services/{service_id}/versions`, `POST /api/services/{service_id}/versions`
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

Latest recorded verification: 25 backend tests passed (one local LibreSSL/urllib3 warning), the frontend production build passed, `docker compose config --quiet` passed, and the rebuilt Compose database/API/web services reported healthy. A clean isolated Docker smoke test also verified starter-kit import and API/frontend responses; this is not a browser-driven UI acceptance test.

## Current scope and limitations

- Implemented: imported service registry (manual service and consumer-usage creation is removed), starter-kit import, UTF-8 YAML/JSON OpenAPI 3.0.3 structural and local-ref validation, duplicate-version handling, semantic comparison for common OpenAPI schemas/parameters/responses, declared consumer impact, provisional publish policy, publish-attempt history, metrics, and a React UI.
- Imported invalid specs remain visible with errors so import can complete; invalid user uploads are rejected.
- The implemented publish policy is maintained in `backend/app/policy.py`: it blocks breaking changes that affect declared consumers and expired `x-sunset` elements still used by a declared consumer, and warns for upcoming sunsets. Impact is limited to imported declarations.
- The last recorded dependency audit reported high-severity advisories in the Vite toolchain (including `picomatch`). The frontend builds, but this is a dependency risk to revisit before external deployment; no newer audit result is recorded here.
- No auth/approval workflow, external `$ref` loading, notifications, or CI integration is included. Unsupported OpenAPI constructs and classifier edge cases need further coverage before production use.
- Severity/classification is a heuristic and should be treated as review guidance, not proof of runtime behavior.

## Buildathon documents

- `PLAN.md` — implemented product and technical behavior
- `PROGRESS.md` — current implemented status and verification
- `DECISIONS.md` — assumptions and decisions
- `REVIEW.md` — current self-review and known limitations
