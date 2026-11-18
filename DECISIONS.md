# Decisions

- 2026-11-18 — Build the product beside the starter kit at the workspace root; preserve starter-kit files.
- 2026-11-18 — Use FastAPI, React, and PostgreSQL as selected by the product owner.
- 2026-11-18 — Spec records have internal IDs; `info.version` is metadata. Import preserves duplicate version strings with warnings; new upload collisions are rejected and never overwrite records.
- 2026-11-18 — Keep invalid starter-kit specs as visible invalid records so import can continue and report them; reject invalid regular uploads.
- 2026-11-18 — Keep the provisional publish policy separate from change classification in `backend/app/policy.py`, so findings describe changes while policy determines whether publishing is allowed.
- 2026-11-18 — Populate service registry and consumer usage declarations through the supplied starter-kit import only. Remove manual service and usage creation UI/API because hand-entered reads/writes do not include the field data types needed for reliable impact declarations and could imply unsupported precision.
- 2026-11-18 — Accept regular spec uploads only as UTF-8 files with `.yaml`, `.yml`, or `.json` suffixes, and require OpenAPI `3.0.3`; use the existing OpenAPI validator and local `$ref` checks rather than accepting unknown formats or loading remote references.
- 2026-11-18 — Store uploaded specs against the selected provider; after success, select the new record as the proposed version so it can be compared to any valid baseline for that same provider. Keep comparison identity based on internal record IDs, not version-string equality.
