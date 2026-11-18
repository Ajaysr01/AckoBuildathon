# Self-review

## What works

- The app imports the supplied provider specs and consumer declarations without modifying the starter kit. Duplicate imported version strings remain separate records, and invalid imports are reported without preventing the rest of the import.
- Spec uploads are parsed and validated, including local `$ref` resolution; duplicate provider/version uploads are rejected rather than overwritten.
- The comparison flow resolves component references, reports common contract changes, matches findings to registered consumer paths, and offers a provisional publish gate with persistent outcomes.
- The React interface covers import, service selection, comparison, upload, impact review, publish outcome, history, and metrics.

## What does not work / limitations

- This is a buildathon implementation, not a production-grade OpenAPI compatibility engine. More schema constructs and classifier rules need tests and review.
- Docker startup could not be verified because the Docker daemon was unavailable in this environment.
- Authentication/authorization, formal approvals, notifications, and CI integration are not implemented.
- The UI currently allows publishing imported valid records as proposals; a more explicit draft/published lifecycle may be needed for a production workflow.
- Metrics and policy need review against product-owner answers; impact only represents declared consumers.

## AI mistakes / corrections

- Initial test setup missed `httpx` and a test path was wrong; both were corrected and tests rerun.
- Initial route matching treated renamed path placeholders as endpoint removal/addition. It was changed to compare equivalent route shapes and report the placeholder rename separately.
- A first consumer matcher did not account for the same schema being represented as a list item in one operation and an object in another. The matching logic and tests were updated for the supplied kit's usage patterns.

## What I would do next

- Start Docker Compose and exercise the full UI against PostgreSQL.
- Review policy semantics and supported change classifications with the product owner.
- Add stricter OpenAPI edge-case tests and API/UI acceptance tests, then improve accessibility and error recovery.
