# Phase 3 Foundation Audit

**Branch:** `feature/company-auth`  
**Scope:** Authentication and tenant boundary, durable company persistence, source-record storage, financial precision, private object-storage code, audit trail, secret references, database adapter layer, retention and automated verification.  
**Verification boundary:** GitHub CI proves isolated unit and workflow checks only. It does not prove live Firebase, Firestore, Cloud Storage, Secret Manager, or external database connectivity.

## Implemented in source

| Area | Implementation | Remaining environment or product dependency |
|---|---|---|
| Firebase identity | Email/password auth, email verification, ID-token revocation checks, token refresh, re-resolution of active membership | Must be exercised against the configured Firebase project |
| Tenant authorization | Verified UID/email, user-profile UID, member UID/email, active membership and active company are checked before company-scoped Firestore access | No dedicated role-based admin/member actions exist yet; service methods still accept a company ID selector but independently authorize it |
| Firestore client boundary | Client rules remain deny-all; trusted Firebase Admin service performs company-scoped reads/writes | Live rules and service-account IAM review required |
| Company dataset metadata | Company-scoped metadata, mapping and validated procurement records are persisted from Connect; dataset metadata lists and record reads are paginated | Original uploaded file bytes require a provisioned private object bucket |
| Record durability | Normalized/mapped validated records for all supplied dataset types are written in batches of 400, each row is bounded to 800 KB, stable row IDs support retries for the same dataset ID, identical file re-submissions resolve to a deterministic upload ID, and saving/complete/failed states prevent incomplete reads; per-file and batch upload sizes and total record count are bounded | Changed file contents create a new dataset version; original file bytes still require private object storage |
| Financial precision | Decimal values are encoded as tagged exact decimal strings and restored as Python Decimal across metadata, mappings, source records, analysis results and workspace revisions | Historical values already stored as floats cannot be reconstructed exactly; pandas/engine conversions that occurred before persistence cannot be reversed |
| Analysis workspace | Revisioned dashboard tables, supporting evidence and run metadata are stored in Firestore; batches are bounded, row-size checked, restored in pages of 500, and the active revision/latest-analysis pointers switch in one transaction | Live Firestore failure-injection and restart tests remain |
| Revision retention | Successful saves retain the active revision and a recent recovery window; obsolete revisions are recursively deleted and cleanup is audited | Retention policy is currently code-defined (three recent revisions), not configurable from Settings |
| Cases and actions | Case state and append-only history are written in one Firestore transaction; stale concurrent updates fail instead of overwriting a newer history; history reads verify event counts | Live concurrent-user and transaction retry tests remain |
| Audit trail | Company-scoped append-only audit events cover dataset metadata, mappings, record save/read, analysis save/restore/pruning, case list/update and private file upload/download/delete | Live write/read permissions and retention policy must be checked in the target project |
| Private file storage | GCS upload/download/delete helpers enforce company paths, allowlisted file types, size limits, create-only upload, and generation preconditions; failures are sanitized | No bucket is provisioned in the current Spark/no-billing setup, so original files remain session-only |
| Secrets | Secret Manager helper accepts only secret-version resource references and fetches JSON server-side using ADC; secret values are not put in Streamlit state | Runtime service identity needs least-privilege Secret Manager access; rotation is by publishing a new version and updating its reference |
| Database adapters | Optional PostgreSQL, MySQL, SQL Server and BigQuery adapters use parameter binding, query validation, read-only settings, TLS where supported, timeouts and bounded result previews; saved profiles contain only Secret Manager references | Optional dependencies, ODBC driver, network access, read-only DB principals and live provider tests must be configured |
| Settings and connector administration | Owner-only Settings UI can add, list, test with a bounded SELECT 1 query, enable and disable company database profiles; server-side profile methods independently enforce owner membership | No general-purpose SQL query workbench or automatic external-database ingestion pipeline is exposed yet |\n| Error handling | Unknown Firebase errors and Connect ingestion/persistence errors shown to users are generic; Firestore diagnostic cleanup failures are surfaced | Operational logging/alerting and deployment smoke tests remain |

## Security and persistence invariants

- `firestore_db.verify_company_access()` verifies the Firebase ID token with revocation checking, binds token UID and verified email to the Streamlit session, and checks the authoritative user and membership records.
- `company_store.get_company_for_user()` verifies user UID, company status, member UID, active membership, member email and user-profile email.
- Every company data helper obtains its reference through `_company_ref()`; GCS helpers independently verify the company before touching an object.
- The client-side Firestore rules have not been loosened. Firebase Admin access is server-side.
- Dataset and analysis reads use bounded pagination. Record writes are validated before writes begin, use idempotent row IDs within a dataset ID, and mark partial failures as incomplete.
- Analysis revisions are written separately; only a complete revision can be activated. The analysis and company latest pointers are switched transactionally.
- Case activity events and case state are committed in a single Firestore transaction. A stale history length is rejected.
- Audit payloads are size-limited and strip credential-like keys before persistence. Audit writes are best-effort across separate Firestore/GCS operations and emit a static server warning if the audit sink is unavailable; they are not a distributed transaction.
- Database query helpers accept only a single SELECT/CTE statement, reject mutation/locking patterns, bind parameters, limit returned rows and apply timeouts. Database users must still be provisioned with read-only grants.
- No credential values or service-account JSON are committed to the repository.

## Automated verification

The Python security workflow covers authorization, company membership integrity, private storage boundaries, transactional case history, generic dataset-record persistence and retrieval, exact Decimal serialization, revision cleanup, audit event sanitization, and read-only connector validation/dispatch. The Phase 7 hybrid web workflow also passes on the same branch.

- Python security Run #78 passed on commit `6d29f55`: 53 tests passed.
- Phase 7 hybrid web Run #108 passed on the same commit.
- These checks are automated CI tests with mocked/isolated provider boundaries; no live Firebase, GCS, Secret Manager or external database connection was performed.

## External acceptance still required

1. Provision a private GCS bucket under an approved billing/storage arrangement; verify private upload, download, delete, generation preconditions, IAM and recovery. Until then, original file bytes are not durable.
2. Configure Firestore and Firebase Admin service-account IAM; run live sign-in, verification, revocation, tenant-isolation, persistence, restart, transaction and failure-injection tests.
3. Configure Secret Manager IAM and validate each database adapter against an actual provider with TLS certificates, timeouts, read-only grants and cleanup.
4. Decide and document audit-event retention and deletion policy.
5. Decide whether to introduce role-based admin/member actions; current application bootstrap creates one owner and no member-management actions are exposed.
6. If historical dataset version cleanup is required, define a retention policy for superseded uploads. The current Connect flow persists both raw source-table rows (including unmapped columns) and normalized rows; deterministic IDs make exact same-file retries idempotent. Original file bytes remain the authoritative original artifact when private object storage is enabled.

**Phase 3 status: implementation substantially complete; production acceptance is blocked on external Firebase/Firestore, GCS, Secret Manager and database-provider configuration and live verification.** Do not mark Phase 3 production-complete until those checks pass.
