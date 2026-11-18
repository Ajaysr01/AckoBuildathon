# Final Self-Review — Contract Guard

Status checked 2026-11-18 against Option 1 (Contract Guard) in the supplied problem statement.

## Requirement assessment

| Must-have | Status | Result |
| --- | --- | --- |
| Service and specification registry | **Partial** | Supplied provider/consumer services and specs import correctly; OpenAPI YAML/JSON uploads are available through UI/API. Manual registration of arbitrary services/owners was removed at the user's request, so the statement's registration behavior is absent. |
| Shared components and `$ref` behavior | **Met for local refs** | Local refs are validated and resolved for comparison; external refs are explicitly unsupported. Component rearrangement behavior has regression coverage. |
| Compare specification versions | **Partial** | Common endpoint, parameter, schema, requiredness, type, enum and response changes are tested. This is not complete coverage of all OpenAPI constructs/change types. |
| Classify risk and explain | **Partial** | Findings give plain-language summaries and a heuristic breaking/non-breaking label. Classification is not comprehensive or a proof of runtime compatibility. |
| Consumer registration | **Partial** | The four supplied consumer declarations are imported. Manual consumer or usage registration is not available, intentionally, because the user asked to remove the controls that only captured untyped reads/writes. |
| Impact by affected consumer | **Met within imported declarations** | Findings identify matching declared consumers and relevant changes. Undeclared consumers cannot be inferred. |
| Safe publishing gate | **Met within current policy** | Publishing is blocked for breaking findings affecting declared consumers and expired sunset elements still used. The policy is provisional, not a human approval process. |
| Changelog and publish history | **Met** | Pairwise comparison yields a change list; every publish attempt outcome is persisted and listed. |
| UI | **Met for imported-registry workflow** | Browser smoke check rendered imported providers and versions without console errors; upload, compare and publish interactions also have backend/integration coverage. |
| Metrics and runnable setup | **Met in tested environment** | Compose configuration/build/start, health checks, endpoints, clean-volume import and metrics were verified. |

**Verdict:** good to demonstrate the imported starter-kit workflow with limitations disclosed; **not a complete pass of every must-have and not production-ready**. The explicit manual-registration requirement is unmet by design. The classifier is bounded, and the final frontend dependency audit found high-severity issues.

## Final verification actually run

- `.venv/bin/pytest -q backend/tests`: **25 passed**, with one warning that the local Python SSL build uses LibreSSL while urllib3 2 expects OpenSSL.
- `npm run build` in `frontend`: passed.
- `docker compose config --quiet`: passed.
- `docker compose up --build -d`: images built; PostgreSQL, API and web were healthy.
- Running app check: API health, services, and metrics returned success; frontend returned HTTP 200. Chromium showed imported provider/version controls and no console errors. This was a browser smoke check, not exhaustive click-through acceptance testing.
- Clean isolated Compose test: imported 12 specs (one retained invalid), four consumer declarations, and seven services; API and frontend responded. The isolated test project and volume were removed.
- Removed manual write routes: `POST /api/services` returned 405 and `POST /api/services/1/usages` returned 404.
- Upload-then-compare, unsupported extension/OpenAPI version rejection, duplicate handling and consumer impact are covered by tests.
- `npm audit --json`: **4 high-severity findings**, including a `picomatch` ReDoS advisory in the Vite toolchain (exit code 1). No dependency upgrade was made in this final audit; this should block production deployment pending remediation and re-test.

## Other submission caveats and limitations

- The problem statement says AI transcripts must be included under `transcripts/`; no such directory/export was found. Provide the genuine OpenCode export for that assessment requirement. Do not fabricate a transcript.
- The current `PLAN.md` is an as-built, descriptive plan requested later by the user. It is not the unchanged Gate 1 plan described in the problem statement; this is a process/submission deviation.
- No authentication, authorization, formal human approvals, external `$ref` loading, notifications or CI integration are implemented.
- Publish policy is provisional and impacts only imported declarations. Less-common OpenAPI changes may be missed or misclassified.
- The UI permits publishing a valid imported version as a proposed version; there is no separate draft approval lifecycle.

## AI mistakes / corrections recorded

- Initial test setup omitted `httpx` and used an incorrect test path; both were corrected and tests rerun.
- Initial route matching treated placeholder renames as endpoint removal/addition; it was changed to normalize route shapes and report renames separately.
- Initial consumer matching did not handle supplied list-item/object schema shapes; matching and tests were updated.

## Go-forward recommendation

- **Buildathon/demo:** go, provided the import-only registration deviation and heuristic policy are stated clearly.
- **Production:** no-go until the high-severity frontend dependency findings are reviewed/remediated, security and approval needs are addressed, and OpenAPI classification limits are accepted and tested.
