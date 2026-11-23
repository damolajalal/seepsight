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
| Analysis workspace | Connect persists run metadata plus findings, supporting evidence and dashboard tables as bounded Firestore row documents; latest completed analysis ID is stored on the company record and restored for the authenticated company in a fresh session | Raw source records/files and cases/action history are not yet persisted; table reads are currently unpaginated; partial-write and runtime behavior need tests |
| Automated checks | Added authorization unit tests, adapted cloud-storage tests to mock the authorization boundary, and added a GitHub Actions test workflow | Workflow execution and test results have not yet been confirmed |

## Security design confirmed in source

- `auth.require_auth()` re-verifies the Firebase identity on each authenticated app rerun, checks revocation, refreshes an expired ID token where possible, and re-resolves the company and role.
- `firestore_db.verify_company_access()` verifies the ID token with revocation checking, checks UID consistency and verified email, and resolves the user's active company membership from Firestore.
- Dataset metadata, records, mappings, and analysis helpers obtain their company reference through the authorization boundary.
- Cloud Storage upload, download, and delete operations call the same authorization boundary.
- Firestore client rules remain deny-all; trusted backend Firebase Admin access bypasses client rules.
- Workspace and case data are additionally scoped by company ID inside the Streamlit session.
- Analysis persistence writes each dashboard table to separate row documents, applies an 800 KB per-row guard, batches writes/deletes, and marks the analysis complete only after table writes finish. Restoration uses the latest analysis pointer on the authenticated company document.

## Remaining Phase 3 work

### P0 — Finish tenant-context refactor and security verification
- Prefer passing a verified tenant context to data services rather than repeatedly accepting a free-form company ID.
- Add tests for missing user records, missing membership, inactive membership, suspended company, and revoked tokens.
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
- Add pagination to workspace table restoration and stronger recovery/cleanup for interrupted writes.
- Persist cases and action history with an audit trail.
- Keep original-file storage labelled session-only until a real private-bucket upload/retrieval test succeeds.

### P1 — Data integrity and operational hardening
- Preserve exact financial precision; avoid silently converting currency `Decimal` values to binary floats.
- Add pagination and bounded reads for record retrieval.
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
- Unit tests have not been executed in a local runtime in this session.
- No Firebase rules were loosened.
- No production deployment or successful live Cloud Storage test is claimed.

**Phase 3 status: in progress — tenant checks and dashboard analysis persistence implemented in source; automated/live verification, raw source durability, case history and operational hardening remain outstanding.**
