# Phase 3 Foundation Audit

**Branch inspected:** `feature/company-auth`  
**Audit basis:** repository source at the branch during this audit. This is a source review, not a live penetration test or deployment verification.

## Existing components confirmed

| Component | Existing behaviour | Remaining concern |
|---|---|---|
| `seepsight/auth.py` | Firebase email/password registration and login through Identity Toolkit; checks email verification; stores UID, company ID, role, ID token and refresh token in Streamlit session state | `require_auth()` trusts the session dictionary and does not visibly verify token expiry/revocation or refresh the identity before allowing access |
| `seepsight/company_store.py` | Firestore transactional creation/retrieval of company, user and active membership records; resolves a user's company from UID | Membership lookup exists, but callers must consistently use it as the authorization source |
| `seepsight/firestore_db.py` | Firebase Admin initialization; Firestore dataset metadata, record, mapping and analysis persistence helpers; normalization and batch writes | Most data helpers accept a caller-supplied `company_id` directly. They do not independently prove that the current UID is an active member of that company |
| `seepsight/workspace.py` | Rejects a workspace in Streamlit session state when its company ID differs from the current session's company ID | Active workspace and case data remain session-state based; no durable workspace hydration path is shown |
| `pages/connect.py` | Multi-file onboarding, dataset recognition, mapping and quality checks | Explicitly warns that uploaded records and results are session-based and not permanently stored |
| `requirements.txt` | Firebase Admin and Firestore dependencies are present | Google Cloud Storage and Secret Manager client dependencies are not currently listed |

## Critical Phase 3 gaps

### P0 — Establish a trusted tenant authorization boundary
- Verify the Firebase ID token server-side using Firebase Admin on every protected request/rerun, including expiry and revocation handling where supported.
- Do not treat `st.session_state["seepsight_auth"]`, its `company_id`, or its `role` as independently trusted authorization evidence.
- Resolve the active UID's company and membership from Firestore after token verification.
- Require a verified tenant context in storage, database, case, report, and AI service methods.
- Do not accept an arbitrary company ID from a page or client as sufficient authorization.
- Fail closed on missing, invalid, expired, revoked, disabled, or inactive membership.

### P0 — Remove sensitive exception disclosure
- Login currently displays the exception text when company workspace loading fails. Replace raw exception display with a safe user-facing message and structured server-side diagnostic logging that excludes tokens, credentials, and customer records.
- Review all storage and connection errors for credential or query leakage.

### P1 — Durable private file storage
- Implement a private GCS adapter with company-scoped object paths, safe generated object names, content/type/size validation, and least-privilege IAM.
- Store object references and metadata in Firestore, not file bytes in session state.
- Add upload state transitions, retention, deletion, and cleanup for incomplete uploads.
- Add signed download access only after tenant authorization, with short expiry and safe content disposition.

### P1 — Harden Firestore persistence
- Make tenant context mandatory for every company data operation.
- Verify company membership at the service boundary rather than relying on callers to remember it.
- Keep all reads/writes beneath the authorized company document.
- Add pagination and bounded reads for record retrieval.
- Make ingestion writes idempotent and track partial/batch failure state so incomplete uploads are never marked complete.
- Revisit numeric normalization: avoid converting financial `Decimal` values to binary floats when exact currency precision is required; store minor units or canonical decimal strings with explicit currency/scale.
- Scope connection diagnostics to a dedicated system health record and ensure cleanup failures are surfaced safely.

### P1 — Secrets and external database connections
- Add Secret Manager-backed secret references and lifecycle controls.
- Implement PostgreSQL, MySQL, SQL Server and BigQuery adapters with TLS, timeouts, read-only access by default, parameterized queries, bounded previews, and sanitized errors.
- Never put database passwords or service-account private keys in source control or client-visible session state.

### P2 — Workspace persistence and audit trail
- Persist dataset, mapping, validation, analysis, findings, evidence, cases and refresh-job metadata under the authorized company.
- Rehydrate the workspace on a new session/app restart.
- Add auditable events for upload, mapping change, sync, analysis, report export, case assignment/status change, and deletion.
- Add retention and deletion workflows.

## Required tests before Phase 3 can be marked complete

- Invalid/expired/revoked token and missing membership are denied.
- Active user from company A cannot read/write/list/delete company B data, even if a forged company B ID is passed to a service.
- Inactive membership and suspended company are denied.
- Firestore read/write failures, partial batch failures, retries, and duplicate ingestion behave safely.
- GCS object paths and download authorization are tenant-scoped.
- Secret values never appear in UI, logs, tracebacks, test output, or repository content.
- Database adapter failures return sanitized messages and close connections.
- Workspace reload after a new session restores only the authenticated company's data.

## Recommended implementation order

1. Introduce a verified identity/tenant context and harden `auth.require_auth()`.
2. Refactor Firestore operations to require that context, not a free-form company ID.
3. Add unit tests with mocked Firebase Admin and Firestore clients.
4. Implement private GCS persistence and upload metadata lifecycle.
5. Add Secret Manager and read-only database adapters.
6. Integrate durable persistence into Connect Your Data and workspace loading.
7. Run cross-tenant and failure-mode tests before moving to broader Phase 4 work.

**Status:** Audit complete at source-review level. No Phase 3 production changes are claimed by this document.
