# Decisions

This log follows the order in which decisions were made during discovery, design, and implementation. Timestamps are from the OpenCode session transcript (`transcripts/ackoBuildathon.json`) and shown in the workspace's local time (UTC+05:30). Later implementation changes are recorded where they superseded an earlier choice.

1. **2026-11-18 17:02 — Define Contract Guard as a pre-publish safety gate.** The product is an interface and service that compares API contract versions, explains changes and their likely consequences, identifies affected callers, and prevents risky changes from being published. The goal is to catch consumer-impacting incompatibilities before release, not diagnose production failures after the fact.

2. **2026-11-18 17:17 — Use the supplied OpenAPI extensions when present, but do not require them.** Interpret `x-internal` as marking internal-use API elements and `x-sunset` as an end-of-life date. The Claims specs do not contain these extensions, so their absence must not invalidate a spec; they are optional metadata supported where supplied.

3. **2026-11-18 17:39 — Limit impact and publish decisions to declared consumers.** Only consumer usage represented in the imported declarations is known to the product. Impact results therefore describe declared consumers and must not claim that no other consumers exist. This keeps the analysis grounded in evidence available to the tool.

4. **2026-11-18 17:39 — Initially use OpenAPI version strings for version identification and warn about duplicates.** This was the simplest understandable approach for selecting versions. The initial overwrite-on-confirm idea was later revised because replacing an existing version could erase history and create ambiguous comparisons; see the collision decisions below.

5. **2026-11-18 17:39 — Bootstrap the registry from the supplied starter kit while still supporting spec uploads.** Import the provided specs and consumer declarations to make the product usable with the exercise data. The import is not a substitute for normal YAML/JSON spec upload through the product's UI and API.

6. **2026-11-18 17:39 — Prioritize core requirements and defer optional integrations.** Focus first on registry, validation, comparison, declared-consumer impact, publishing checks, history, UI, and metrics. Notifications, CI integration, and AI-generated migration guidance were treated as later/optional work.

7. **2026-11-18 17:39 — Use the selected stack: FastAPI, React, and PostgreSQL.** The product owner selected Python/FastAPI for the backend and React for the UI, with PostgreSQL if persistence is needed. These technologies support the required API/UI workflow and durable registry and audit history.

8. **2026-11-18 17:44 (confirmed 17:46) — Keep severity classification separate from publish policy and make policy provisional.** Initially, block only changes that break a service; treat deprecation and sunset as affecting publishing after expiry. Keep those checks replaceable so product-owner requirements can change without rewriting comparison logic. The user confirmed the sunset rule should block only when a declared consumer still uses the affected element.

9. **2026-11-18 17:51 — Never overwrite existing version records.** The initial duplicate-version proposal allowed a user to accept an overwrite, but this was reconsidered because it could destroy history and compromise comparisons/auditability. New collisions should warn and be rejected without replacing data; users can correct the proposed version or cancel.

10. **2026-11-18 17:54 — Separate record identity from `info.version` to handle supplied duplicate versions safely.** Give every spec record an internal ID and retain its original version string and source filename. Import every starter-kit file—including duplicate version labels—without changing source files; warn and distinguish duplicates by filename. Permit explicit comparison by record ID. For regular uploads, reject a provider/version collision and never overwrite an existing record. This superseded the earlier version-string-only identity choice while preserving version strings as display metadata.

11. **2026-11-18 18:00 — Build the product beside the starter kit and preserve the supplied kit.** Add the application at the workspace root rather than replacing starter-kit components; keep the provided specs, consumer declarations, and webhook receiver unchanged as source inputs. Proceed incrementally from the approved design and verify each milestone.

12. **2026-11-18 18:02 — Keep the supplied invalid import visible without aborting the rest of import.** The Claims starter kit contains a spec with an unresolved local `$ref`. Preserve it as an invalid record with validation details so users can see the problem and the other records still import. In contrast, reject invalid regular uploads so bad data cannot enter as a proposed version.

13. **2026-11-18 18:41 — Load dashboard sections independently.** A failing metrics request had caused the whole dashboard to show “Load failed,” even though services and publish history were available. Handle each request independently and report the failing section so one endpoint does not hide the rest of the dashboard.

14. **2026-11-18 18:53 — Explain publish-policy blockers separately from change severity.** A finding can be classified as non-breaking while publishing is still blocked by another policy rule, such as an expired `x-sunset` element used by a declared consumer. Keep classification and policy separate, and show the policy reason/blocker count so the outcome is understandable. Preserve each publish attempt and expose the full audit list rather than implying the history stops after a short initial list.

15. **2026-11-18 18:58 — Keep the import confirmation concise and remove the redundant refresh control.** Replace the large inline import report with a short “Upload Successful” confirmation, keeping the UI uncluttered while import details remain available through persisted run data/API. Remove the top-right refresh button because it added no useful value to the workflow.

16. **2026-11-18 19:05 — Make container setup explicit and reproducible.** Add Dockerfiles for the backend and frontend, use locked/pinned dependencies, build the frontend for Nginx serving, and wire the services through Compose. This makes the required app dependencies and runtime setup explicit and supports a consistent Compose startup.

17. **2026-11-18 20:19 — Remove manual service and consumer-usage creation.** The manual form captured `reads`/`sends` paths but not field data types. Such partial declarations could imply more precise impact analysis than the data supports. Keep registry and usage data from starter-kit import, which retains the provided declarations, but remove the manual creation UI and write routes.

18. **2026-11-18 20:24 — Restrict regular uploads to compatible, validated OpenAPI files and make upload-to-compare direct.** Accept UTF-8 `.yaml`, `.yml`, and `.json` files only, require OpenAPI `3.0.3`, validate local references, and do not silently parse unknown suffixes as YAML. Attach a successful upload to the selected provider and select it as the proposed version so it can be compared with any valid baseline for that same provider. Keep comparison identity based on record IDs and reject cross-provider comparisons.

19. **2026-11-18 20:28 — Update project documentation to reflect implemented behavior and actual checks.** Keep the root status/design documents aligned with the code, including the import-only registry workflow, upload constraints, comparison flow, and Docker verification. Documentation should describe what is implemented rather than leave superseded behavior as current.
