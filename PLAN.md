# Contract Guard — Current Plan and Implemented Behavior

This plan preserves the goals while noting where current implementation or later scope decisions differ from the original must-haves.

## Problem and users

Contract Guard is a registry and publishing gate for OpenAPI services. It helps API owners understand whether a proposed spec change affects known consumers before publishing; consumer teams can see what changed and why it may affect them; platform leads can review outcomes and protection metrics.

The desired outcome is to catch and explain consumer-impacting API changes before release, not to debug production failures afterward. Impact analysis is explicitly limited to declared consumers; the UI must say “no declared consumer affected,” not claim that there are no other consumers.

## Requirements and current implementation

### Explicit must-haves and current status

- **Registry — partial against original requirement:** provider/consumer services and declarations are created by starter-kit import. Manual service/consumer registration was later removed by user request. UTF-8 YAML (`.yaml`/`.yml`) and JSON (`.json`) OpenAPI 3.0.3 uploads are supported through UI/API; invalid uploads return errors.
- **Shared components and comparison — common-case support:** local `$ref`s are validated/resolved so component-only organization changes are ignored. Endpoints, route placeholders, parameters, common nested/list request/response schemas, types, requiredness, enums/constraints, and response status/body changes are detected. Less-common constructs are not exhaustive.
- **Classification and impact — heuristic:** findings give plain-language summaries and severity; affected consumers are matched only from imported declarations and their `sends`/`reads` paths.
- **Publish control:** current policy blocks breaking findings affecting declared consumers and expired `x-sunset` elements still used by declared consumers; upcoming deprecation/sunset use is warned.
- **Changelog, history, UI, metrics, runnable setup:** pairwise comparison returns findings, publish attempts and outcomes are persisted, React UI exposes the imported-registry workflow, metrics are available, and Compose runs the PostgreSQL/API/frontend stack.

### Agreed provisional policy

- A breaking change blocks publishing only if it impacts a declared consumer.
- A deprecated or `x-sunset` element used by a declared consumer warns while the sunset date is today or in the future. It becomes blocking the day after that date if still used.
- Keep classification and publish-policy decisions separate in code so the policy can be revised independently; runtime policy configuration is not implemented.
- Treat `x-internal` as an OpenAPI extension indicating internal use and `x-sunset` as an end-of-life date. Neither extension is required in a spec.
- Product owner permitted a suitable policy choice; the implemented policy is provisional rather than a product-owner-mandated standard.

## Starter kit and import decisions

- Import all three providers’ four spec files and all four consumer declarations. Do not modify the supplied `specs/` or `consumers/` files.
- Support normal spec uploads through UI and API in addition to starter-kit import.
- Preserve every imported file, including the two Claims specs both declaring `info.version: 1.1.0`.
- Give each spec record an internal ID. Store `info.version` and source filename separately; use filename to distinguish same-version imported records.
- Allow duplicate version strings in starter-kit imports with a warning, without failing the entire import. Allow explicit comparison of selected records even when their `info.version` strings match.
- For new uploads, reject a duplicate provider + `info.version` before overwriting anything; explain that the user should cancel or upload a corrected spec with a unique version. Never overwrite an existing record or its history.
- Compare explicit spec records; do not infer ordering between duplicate version strings or alter version strings during import.

## Discovery questions and answers

- `x-internal`/`x-sunset` meaning: treat the former as marking internal use and the latter as end-of-life date; neither is mandatory.
- Which consumers are in scope? Only consumers declared in the supplied/registered usage data.
- How to order/identify specs? Use `info.version`; internal record IDs distinguish records. Warn on duplicate imported versions; reject new upload collisions rather than overwrite.
- How to onboard starter-kit data? Import services, specs, and consumer declarations; allow spec upload through UI/API. Manual service/usage registration was later removed as recorded below.
- Optional enhancements: defer notifications, CI integration, and AI-written migration guidance until core must-haves work.
- Policy choice: product owner allowed a suitable choice. Current severity and sunset behavior is implemented as provisional policy in a separate module.
- Later scope change: remove service and consumer-usage creation from UI/API; retain starter-kit import. The removed UI captured only untyped `reads`/`sends` paths, which could imply unsupported precision. This is an intentional deviation from the original registration must-have.

## Implemented scope and deferred features

### Implemented

1. Starter-kit registry import, YAML/JSON validation, local `$ref` checks, and upload collision messages.
2. Common-case semantic OpenAPI comparison and human-readable findings.
3. Declared consumer matching for methods, endpoint shapes, sent/read paths, nested fields, and list paths.
4. Separate provisional publishing policy, publish outcomes, and append-only attempt history through the application API.
5. React UI, metrics, backend tests, and Docker Compose setup.

### Defer

- Webhook notifications, CI check endpoint, AI-generated migration guides, manual service/usage creation

## System design
Use one modular application to keep the buildathon product understandable and easy to run:

- **Backend:** Python FastAPI modules for registry/import, validation, comparison, impact/classification, publishing policy, history, and metrics.
- **Frontend:** React UI for services, versions, upload/import, comparison, impact/publish, and history/metrics.
- **Persistence:** PostgreSQL in Compose and SQLite by default for local/test use. Persist services, spec documents/metadata, consumer declarations, import runs, and publish attempts. Comparison findings are computed per request; policy findings are stored with publish attempts rather than in a separate comparison table.
- **Starter kit:** import original files without changing them. Reuse the webhook receiver unchanged only if notifications are added later.

### Data model

- `Service`: name, provider/consumer role, owner/team.
- `SpecVersion`: internal ID, provider service, OpenAPI `info.version`, original document, source filename, validation result, status, timestamps.
- `ConsumerUsage`: consumer, provider, method, path, `sends`, and `reads` field paths.
- Change findings are computed by the comparison module and returned to callers; no standalone `ChangeFinding` table is implemented.
- `PublishAttempt`: proposed spec record, selected baseline, outcome, timestamp, reason, and policy findings.

Enforce provider-scoped unique `info.version` for new UI/API uploads. Starter-kit import may retain duplicate version strings, distinguished by internal ID and filename. Never overwrite existing records. Publish attempts point to record IDs, preserving exact provenance.

### API outline

- `GET /api/services` — services and owners.
- `GET /api/services/{service_id}/versions` — spec records and statuses.
- `POST /api/services/{service_id}/versions` — upload and validate; collision returns a warning/error without overwriting.
- `POST /api/import/starter-kit` — import specs and consumer declarations; report duplicate-version warnings while preserving every file.
- `GET /api/versions/{from_id}/compare/{to_id}` — changes, explanations, and impact for explicitly selected spec records.
- `POST /api/versions/{version_id}/publish?baseline_id={baseline_id}` — evaluate the selected baseline and record the publish/block attempt under the implemented policy.
- `GET /api/publish-attempts` — outcomes and reasons.
- `GET /api/metrics` — protection summary.
- `GET /api/import/runs` — persisted starter-kit import summaries.
- `GET /api/health` — API health response.

Manual `POST /api/services` and usage write/list endpoints are not implemented. Services and consumer declarations are created by starter-kit import only.

## Main screens

1. **Registry:** imported provider cards show owners and version counts; consumer records support impact matching. There are no manual create forms.
2. **Compare and upload:** select a provider and valid baseline/proposed records; upload a proposed spec for that provider; view validation and duplicate-version outcomes; display semantic findings with before/after and plain-language explanation.
3. **Impact and publish:** affected declared consumers, policy outcome, and publish/block action.
4. **History and metrics:** attempts, reasons, blocked/published counts, affected consumers, expired used elements, invalid stored specs, and detected version collisions.

## Tests and runtime verification

- **Automated coverage present:** parsing, unsupported suffix/OpenAPI version, local refs, import idempotency/duplicates/invalid records, upload validation/collision and upload-then-compare, comparison/impact, policy boundaries, publish history and metrics.
- **Runtime checks performed:** clean isolated Compose import, API health/services/metrics, frontend response, and UI browser smoke load. These checks do not constitute exhaustive browser click-through acceptance testing.

Report tests as passing only after actually executing them.

## Success metrics

- Publish attempts by outcome.
- Publishes blocked due to a declared-consumer break.
- Declared consumers identified as affected.
- Blocks due to expired elements still used by declared consumers.
- Invalid imported specs retained and visible; normal invalid uploads rejected (the invalid-spec metric counts retained invalid records).
- Duplicate version collisions detected without overwriting records.

Metrics describe only loaded/declared data; they do not prove no undeclared consumers exist.

## Known edge cases

- Two Claims starter-kit files declare `info.version: 1.1.0`; import both, distinguish by source filename and internal ID, warn, and allow explicitly selected comparison.
- A Claims spec has an unresolved local `$ref`; reject it for upload with a precise error, while import should report the invalid record clearly and continue importing other files.
- A deprecated/sunset field may be consumer-used; policy depends on the sunset date and must be timezone/date-boundary tested.
- Path placeholder names may change while endpoint shape stays similar; compare routes semantically for consumer matching but report route changes to users.
- Consumers describe what they used when written; do not assume declarations are current or exhaustive.

## Current policy and limitations

The policy remains provisional and independently editable in `backend/app/policy.py`. Manual service/usage registration remains intentionally absent. Comparison remains heuristic and impact is limited to imported declarations.

## Current verification and readiness

- `.venv/bin/pytest -q backend/tests`: 25 passed, with one local LibreSSL/urllib3 warning.
- `npm run build` in `frontend`: passed.
- `docker compose config --quiet` and `docker compose up --build -d`: passed; PostgreSQL, API, and web reported healthy.
- Clean isolated Docker smoke test imported 12 specs (one retained invalid), four consumer declarations, and seven services. API/frontend checks passed; Chromium UI smoke load rendered imported services/versions without console errors.
- `npm audit --json`: four high-severity frontend toolchain findings; no remediation has been applied. This is not production security clearance.
- **Readiness:** suitable for a scoped starter-kit workflow demo with deviations disclosed; production readiness is not established.
