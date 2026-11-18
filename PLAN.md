# Contract Guard — Build Plan

## Problem and users

Contract Guard helps API-owning engineers understand and prevent changes that break known consumers before publishing. Consumer engineers need clear impact and reasons; platform leads need visibility into publishing outcomes. Impact is limited to registered consumer declarations, so reports must say “no declared consumer affected” rather than claim there are no consumers.

## Requirements and decisions

- Register services/owners; accept OpenAPI YAML/JSON through UI and API; reject invalid uploads clearly.
- Compare semantic API behavior, including `$ref`-backed schemas; classify operations, parameters, nested/list fields, types, requiredness, enums, and response code changes.
- Register consumer usage; show affected declared consumers and explain findings; block publishing when a declared consumer breaks.
- Keep changelog, publish-attempt history, UI, metrics, and one-command startup.
- Treat `x-internal` as internal-use metadata and `x-sunset` as end-of-life metadata; extensions are optional.
- Provisional policy: block breaking changes only when declared consumers are affected; warn for deprecated/sunset elements before expiry and block after expiry if a declared consumer still uses the element. Keep policy configurable.
- Import all supplied specs and consumers without modifying the starter kit. Imported duplicate `info.version` records are preserved and warned about; new uploads colliding on provider + version are rejected without overwriting.
- Defer optional webhooks, CI integration, and AI-generated migration help.
- Product-owner answers on severity and sunset policy are pending; provisional policy can be adjusted.

## Research

- oasdiff documents distinct diff, changelog, breaking-change, and validation functions: https://github.com/oasdiff/oasdiff
- Apigee API hub documents OpenAPI linting with default/custom rules: https://cloud.google.com/apigee/docs/apihub/validate-spec

## Design

- Modular FastAPI backend, React frontend, PostgreSQL persistence.
- Modules: registry/import, validation, comparison, consumer impact, publish policy, history/metrics.
- Data: Service; SpecVersion with internal ID, `info.version`, source filename, source document and validation status; ConsumerUsage; ChangeFinding; PublishAttempt.
- Spec records use internal IDs, not version strings, as identity. Preserve duplicate imported versions distinguished by filename; uploads reject collisions. Never overwrite published history.
- UI: services; service/version detail and upload; semantic compare; impact and publish; history and metrics.
- API outline: `/api/services`, `/api/services/{id}/versions`, `/api/import/starter-kit`, `/api/versions/{from}/compare/{to}`, `/api/versions/{id}/publish`, `/api/publish-attempts`, `/api/metrics`.

## Tests and success measures

- Unit: parse/validate, `$ref` handling, version collisions, semantic diff, impact matching, and publish policy including sunset boundaries.
- Integration: import/upload/compare/publish persistence; duplicate import retained; upload collision does not overwrite.
- Acceptance: import provided kit, verify invalid Claims `$ref`, known consumer impacts, publishing decisions and history.
- Metrics: attempts by outcome, breaking changes blocked for declared consumers, affected declared consumers, expired-used elements blocked, invalid specs, collisions detected without overwrite.
- Test outcomes will be reported only after tests are executed.

## Milestones

1. Registry/import API, persistence, OpenAPI validation, collision behavior.
2. Semantic diff and plain-language change findings.
3. Consumer impact matching and configurable publishing policy/history.
4. React UI, metrics, integration/acceptance tests, and runnable documentation.
