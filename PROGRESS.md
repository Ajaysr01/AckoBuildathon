# Progress

## Milestone 1 — Registry and import (complete)

- Added FastAPI endpoints for service registration/listing, spec upload/listing, starter-kit import, and import history.
- Added SQLAlchemy persistence with PostgreSQL configuration for Docker Compose and SQLite as a convenient local/test default.
- Starter-kit import preserves duplicate Claims `1.1.0` entries as separate records; invalid specs remain visible with validation errors, while other files import.
- New spec uploads validate OpenAPI structure and local `$ref`s and reject provider/version collisions without overwriting.
- Verification: `pytest -q backend/tests` passed (8 tests); Python compile check passed.
- Container startup not yet verified because Docker daemon is not running in this environment.
- Milestone 2 complete: semantic comparison endpoint resolves local `$ref`s, ignores component-only reorganization, reports route placeholder renames and schema/parameter/response changes, and matches finding locations against declared consumer use.
- Milestones 2–4 complete: publish gate records allow/block decisions and history; metrics endpoint and React interface are implemented. Policy includes provisional sunset behavior. Consumer usage can also be registered through the API.
- Verification: `pytest -q backend/tests` passed (19 tests); `python -m compileall` passed; `npm run build` passed; `docker compose config --quiet` passed.
- Container startup could not be verified: Docker CLI is present but the Docker daemon is not running/reachable.
- `README.md` and `REVIEW.md` are drafted. Product-owner policy answers are still pending.
- Next: after Docker becomes available, run PostgreSQL + API + UI together and manually verify the full flow.
- Scope unchanged: supplied specs, consumer declarations, and webhook receiver remain untouched.
