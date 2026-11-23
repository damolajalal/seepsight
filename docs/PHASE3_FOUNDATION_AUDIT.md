# Phase 3 Foundation Audit

**Branch:** `feature/company-auth`  
**Audit basis:** source review of the current branch. This is not a live penetration test, successful test run, or deployment verification.

## Implemented in this branch

| Area | Current implementation | Remaining limitation |
|---|---|---|
| Firebase authentication | Email/password authentication; email verification; ID-token verification with revocation checks; refresh-token renewal; company membership is re-resolved from Firestore | Requires runtime verification against the configured Firebase project |
| Firestore tenant boundary | Company data helper resolves the current session token, checks UID and verified email, rejects revoked tokens, then resolves active company membership before returning a company reference | Public helper still accepts a company ID as a selector; service methods should progressively move to an explicit verified tenant context |
| Cloud Storage boundary | Upload, download and delete operations verify active company membership before accessing objects | A real uploads bucket is not provisioned in the current Spark/no-billing environment |
| Connect fallback | Connect can prepare a session-based workspace when no private uploads bucket is configured; metadata and confirmed mappings are saved in Firestore | Original file bytes and raw validated source records are not durable without private object storage; bucket existence/permissions still need a live test |
| User-facing privacy | Company Profile and Settings distinguish Firestore metadata from temporary uploads and analysis workspaces | Must be rechecked against the deployed app |
| Analysis workspace | Connect persists run metadata plus findings, supporting evidence and dashboard tables as bounded Firestore row documents; each save writes a separate revision and switches the active revision only after all rows complete; restoration reads rows in pages of 500 and supports legacy pre-revision workspaces | Raw source records/files are not yet persisted; case state and activity history now have company-scoped Firestore persistence, but automated failure/retry and live persistence tests are still needed; old analysis revisions need a retention/cleanup policy |
| Automated checks | Added authorization unit tests, adapted cloud-storage tests to mock the authorization boundary, and added a GitHub Actions test workflow | Workflow execution and test results have not yet been confirmed |

- Case history: Findings now load company-scoped case state and ordered activity events from Firestore; saving an investigation update persists case status, owner, notes and newly appended history events. The Cases and Actions page reads the same restored company case map.\n\n## Security design confirmed in source

- `auth.require_auth()` re-verifies the Firebase identity on each authenticated app rerun, checks revocation, refreshes an expired ID token where possible, and re-resolves the company and role.
- `firestore_db.verify_company_access()` verifies the ID token with revocation checking, checks UID consistency and verified email, and resolves the user's active company membership from Firestore.
- Dataset metadata, records, mappings, and analysis helpers obtain their company reference through the authorization boundary.
- Cloud Storage upload, download, and delete operations call the same authorization boundary.
- Firestore client rules remain deny-all; trusted backend Firebase Admin access bypasses client rules.
- Workspace and case data are additionally scoped by company ID inside the Streamlit session.
- Analysis persistence validates and normalises the payload before writes, applies an 800 KB per-row guard, writes rows in batches of 300 under a unique revision, marks that revision complete, and only then switches the active revision. A failed replacement therefore leaves the previous active revision intact. Restoration uses pages of 500 rows and supports legacy workspaces without revision pointers.

## Remaining Phase 3 work

### P0 — Finish tenant-context refactor and security verification
- Prefer passing a verified tenant context to data services rather than repeatedly accepting a free-form company ID.
- Add tests for missing user records, missing membership, inactive membership, suspended company, and revoked tokens; current authorization tests cover token/session identity, verified email, company mismatch and membership-email mismatch.
- Test cross-company access against mocked Firestore references for read, write, list and delete operations.
- Review authentication error handling so raw exception text and sensitive diagnostics are never shown to users.
- Confirm role-based authorization before adding member/admin operations.

### P1 — Private file storage
- Provision and verify a private object-storage bucket when billing/hosting constraints permit, or select an appropriate external object-storage provider after reviewing security, terms, location and free-tier limits.
- Verify least-privilege service identity, private object access, upload size/type limits, retention and deletion.
- Store object references and upload lifecycle metadata in Firestore.
- Do not claim durable original-file storage until an actual upload and retrieval test succeeds.

### P1 — Durable workspace and analysis persistence
- Connect the existing Firestore record and analysis helpers to the onboarding and analysis workflow.
- Persist validated source records and add bounded/paginated reads; analysis summaries, findings, evidence and dashboard tables are now persisted, but raw source records are not.
- Add a retention/cleanup policy for abandoned and superseded workspace revisions; test failure injection at each persistence stage.
- Add automated failure/retry tests for the new case state and append-only history persistence.
- Keep original-file storage labelled session-only until a real private-bucket upload/retrieval test succeeds.

### P1 — Data integrity and operational hardening
- Preserve exact financial precision; `_normalise()` currently converts `Decimal` values to binary floats and needs a lossless storage/rehydration strategy before financial source records are durably stored.
- Add bounded pagination to the remaining metadata/list endpoints and verify large record/finding reads under load.
- Handle partial batch failures, retries, duplicate ingestion and cleanup safely.
- Ensure connection diagnostics surface cleanup failures without exposing credentials.
- Remove duplicate dependencies and validate deployment configuration.

### P2 — External integrations
- Add secret-management lifecycle controls.
- Implement database adapters with TLS, timeouts, read-only access by default, parameterized queries, bounded previews and sanitized errors.
- Keep database passwords and service-account keys out of source control and client-visible state.

## Verification status

- Source edits are committed to `feature/company-auth`.
- GitHub Actions workflow file is present, but its run status has not been confirmed.
- Authorization test fixtures and cases were updated for verified-email binding. The GitHub Actions status for the latest commits has not yet been confirmed; no local test runtime was available in this session.
- No Firebase rules were loosened.
- No production deployment or successful live Cloud Storage test is claimed.

**Phase 3 status: in progress — tenant identity checks, revision-safe paginated dashboard analysis persistence, and company-scoped case/action history persistence are implemented in source. Automated failure/retry and live verification, raw source durability, revision retention, financial precision and remaining operational hardening are outstanding.**
