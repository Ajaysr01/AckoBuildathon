# Decisions

- Build the product at the workspace root beside the starter kit, preserving the starter-kit files.
- Use FastAPI, React, and PostgreSQL, as selected by the product owner.
- Identify spec records by internal IDs; treat `info.version` as metadata. During starter-kit import, preserve duplicate version strings and report warnings. For regular uploads, reject version collisions without overwriting existing records.
- Keep invalid starter-kit specs as visible invalid records so imports can continue and report errors. Reject invalid regular uploads.
- Keep the provisional publish policy separate from change classification in `backend/app/policy.py`: findings describe changes, while policy determines whether publishing is allowed.
- Populate the service registry and consumer usage declarations only through the supplied starter-kit import. Do not provide manual service or usage creation UI/API: hand-entered reads and writes lack the field data types needed for reliable impact declarations and could imply unsupported precision.
- Accept regular spec uploads only as UTF-8 `.yaml`, `.yml`, or `.json` files with OpenAPI version `3.0.3`. Validate them with the existing OpenAPI validator and local `$ref` checks; do not accept unknown formats or load remote references.
- Associate uploaded specs with the selected provider. After a successful upload, select the new record as the proposed version for comparison with a valid baseline from that provider. Use internal record IDs—not version-string equality—to identify records in comparisons.
