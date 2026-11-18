# Decisions

- 2026-11-18 — Build the product beside the starter kit at the workspace root; preserve starter-kit files.
- 2026-11-18 — Use FastAPI, React, and PostgreSQL as selected by the product owner.
- 2026-11-18 — Spec records have internal IDs; `info.version` is metadata. Import preserves duplicate version strings with warnings; new upload collisions are rejected and never overwrite records.
- 2026-11-18 — Keep invalid starter-kit specs as visible invalid records so import can continue and report them; reject invalid regular uploads.
- 2026-11-18 — Apply the provisional publish policy from PLAN.md through a separate configurable policy module.
