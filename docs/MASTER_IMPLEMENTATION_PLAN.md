# Seepsight Master Implementation Plan

**Target branch:** `feature/company-auth` only  
**Protected branch:** `main` — do not modify, merge into, or push to it.  
**Purpose:** Deliver Seepsight as a secure, multi-company procurement intelligence platform. This plan records intended outcomes, implementation dependencies, verification evidence, and known gaps. A requirement is not complete merely because a page or module exists.

## Product outcome

A company should be able to create and securely access its own workspace; connect files and supported databases with unfamiliar schemas; validate and persist its procurement data; detect financial leakage and operational risks; inspect the evidence behind each finding; assign and track corrective actions; ask grounded questions; and produce reliable management dashboards and reports.

The system must keep each company's data isolated, distinguish confirmed discrepancies from predictive warnings, label potential exposure as an amount to review rather than a confirmed loss, and avoid inventing answers when source evidence is missing.

## Cross-cutting acceptance rules

- Tenant isolation is enforced server-side for every read, write, upload, query, report, case, and AI request.
- Authentication identity and company membership are verified from trusted identity claims, never from a user-editable company ID alone.
- Credentials and secrets are never stored in source code, Streamlit session state, logs, or client-side configuration.
- Uploads and generated artifacts use private storage, scoped object paths, access checks, retention rules, and safe file validation.
- Ingestion is repeatable and auditable: source, upload, mapping, validation, row counts, errors, and sync timestamps are traceable.
- All monetary calculations preserve currency and precision; no cross-currency aggregation without an explicit conversion basis.
- Findings expose calculation logic, affected records, source lineage, confidence/limitations, and review status.
- Predictions are labelled as warnings and are not represented as confirmed losses or findings without corroborating evidence.
- AI answers are grounded in authorized company data and cited records; if evidence is absent or ambiguous, the assistant says so.
- Every major capability has automated tests plus a documented manual acceptance path.
- Existing working application pages and Phase 7 deployment are preserved unless a verified defect requires a change.

## Phase 1 — Existing application and product foundation

**Intended effect:** Preserve a coherent application and stable data contract while extending the platform.

Work:
- Audit the Streamlit entry point, authentication flow, navigation, company context, workspace model, engine, and all nine pages.
- Preserve the existing nine-page experience: Overview, Connect Your Data, Findings, Suppliers, Cases and Actions, Ask Seepsight, Reports, Company Profile, and Settings.
- Document the canonical procurement data contract, dataset registry, identifiers, currencies, date conventions, and evidence schema.
- Separate demo/synthetic data from customer workspaces.

Acceptance:
- All nine pages load for an authenticated company.
- No customer page silently falls back to another company's data or demo data.
- Existing supported analysis outputs remain reproducible from the same inputs.

**Status:** Existing application and core engine are present; full regression audit remains outstanding.

## Phase 2 — Authentication and company workspaces

**Intended effect:** Every user sees only the company workspace and capabilities they are authorized to access.

Work:
- Verify Firebase authentication and trusted identity-token validation in the Streamlit backend.
- Establish company membership, roles, invitations/onboarding, and account lifecycle.
- Enforce company scope for datasets, uploads, findings, suppliers, cases, chat history, reports, and settings.
- Define owner/admin/analyst/viewer permissions and deny-by-default behavior.
- Handle sign-out, expired sessions, revoked membership, and account deletion safely.

Acceptance:
- Cross-company access tests fail closed for every resource type.
- Role tests verify allowed and denied operations.
- A missing, expired, or invalid identity cannot access customer data.

**Status:** The company identity and workspace foundation is implemented on `feature/company-auth`: Firebase identity-token verification, company membership and role-aware access checks, company-scoped Firestore service boundaries, and authentication/session/membership/authorization regression tests are present. PR #18 consolidated the reviewed dataset-management, workspace-isolation, connection-placement, and Gemini evidence-review work into this branch. **Production acceptance remains pending:** live sign-in and verified-email behavior, membership/invitation lifecycle, the real-account role matrix, expired or revoked identity handling, and negative cross-company access tests against deployed Firestore resources. Code-level tests are not proof of live tenant isolation.

## Phase 3 — Database, durable storage, and security foundation

**Intended effect:** Customer data survives beyond a Streamlit session and is stored securely with company-level isolation.

Work:
- Firestore-only original upload storage using bounded company-scoped chunk documents, metadata and SHA-256 integrity verification.
- Firestore metadata for companies, datasets, upload jobs, mappings, schema versions, sync state, and artifact references.
- Secret Manager integration for database credentials; store secret references, not secret values, in application metadata.
- Database adapters for PostgreSQL, MySQL, SQL Server, and BigQuery with safe connection handling, TLS where supported, query timeouts, read-only access by default, and secret rotation.
- Workspace persistence and retrieval with authorization checks at the service boundary.
- Audit events for upload, connection, mapping, sync, deletion, and access-sensitive operations.
- Retention/deletion lifecycle and safe cleanup of abandoned uploads.

Acceptance:
- Upload and analysis artifacts can be retrieved after a new session or app restart by the same authorized company.
- Another company cannot list, read, overwrite, or delete those artifacts.
- Credentials never appear in logs, UI state, exception messages, or repository files.
- Adapter tests cover success, invalid credentials, timeout, unavailable database, permission denial, and cleanup.
- Storage failure does not create a false success state.

**Status:** Phase 3 code foundation implemented on `feature/company-auth`: company-scoped Firebase/Firestore authorization; durable dataset metadata, raw source rows and normalized records; exact Decimal serialization; revisioned analysis workspaces with transactional activation and retention; transactional case history; company audit events; bounded/idempotent ingestion and retry-safe deletion; Firestore chunked original-file storage; Secret Manager references; and read-only PostgreSQL, MySQL, SQL Server and BigQuery adapters. The Settings page now provides owner-only connection profile creation, testing and enable/disable controls, enforced again in server-side service methods. Python security Run #139 passed 81 tests and hybrid web Run #169 passed on implementation commit `b64842a`. Production acceptance remains pending live Firebase/Firestore, Secret Manager IAM, database network/TLS/read-only credentials and live restart/failure-injection verification. Original upload bytes are stored as Firestore chunks; live byte-field persistence and recovery still require deployment verification. See `docs/PHASE3_FOUNDATION_AUDIT.md` and `docs/PHASE3_CONNECTORS.md`.

## Phase 4 — Universal ingestion and Connect Your Data

**Intended effect:** Different companies can bring their own procurement records without having to rename columns or adopt one rigid template.

Work:
- Support CSV/TSV, Excel workbooks and worksheets, JSON, and supported relational/warehouse sources.
- Multi-file uploads with file safety checks, encoding/delimiter handling, duplicate detection, size/row limits, and clear error reporting.
- Dataset recognition and user-confirmed mapping for all registered dataset types.
- Normalization of numbers, currencies, dates, identifiers, and text with ambiguity warnings rather than silent guesses.
- Relationship validation across orders, suppliers, invoices, receipts, payments, products, inventory, and approvals where those datasets are supplied.
- Persist source files, mapping decisions, schema versions, validation reports, and ingestion job state.
- Database discovery, connection test, table selection, bounded preview, table-to-dataset mapping, and repeatable incremental/full sync.
- Explain which detector families can and cannot run from the available fields.

Acceptance:
- A user can ingest multiple heterogeneous files, review mappings, correct them, validate relationships, and rerun the same job without duplicate records.
- A partial or invalid dataset reports missing requirements and does not claim full coverage.
- A database sync is repeatable, auditable, and bounded by safe limits.

**Status (code):** Dataset registry, file onboarding, schema mapping, dataset grouping/management, normalized-record persistence, Firestore-backed dataset services, and read-only PostgreSQL/MySQL/SQL Server/BigQuery adapter foundations are present on `feature/company-auth`. Dataset-management and ingestion tests were integrated through PR #18; database adapters and Firestore persistence have automated coverage. **Still unverified in production:** live database credentials/network/TLS, repeatable scheduled or incremental sync, restart/recovery under live Firebase/Firestore, and failure-injection behavior. Do not describe production sync or durable customer onboarding as fully accepted until those checks pass.

## Phase 5 — Procurement intelligence and leakage detection

**Intended effect:** Detect actionable procurement anomalies and quantify potential exposure with explainable evidence.

Core detector families to preserve and verify:
- Short delivery / under-delivery: compare ordered, invoiced, and received quantities and identify the amount potentially requiring review.
- Invoice overbilling: compare invoice quantities and amounts with supported receipt/order evidence.
- Purchase-order price violations: compare invoiced unit prices with approved purchase-order prices and authorized changes.
- Slow approvals: identify approval delays using configured thresholds and explain the affected orders and value held up.
- Supplier performance decline: compare comparable historical delivery and fulfilment performance, accounting for adequate sample size and time windows.

Additional coverage, only where the source datasets and business rules support it:
- Duplicate invoices/payments, unmatched invoices, payment anomalies, contract/price variance, inventory/reorder risks, supplier concentration, and other procurement controls explicitly defined in the product requirements.

Work:
- Keep detector logic modular, deterministic where possible, and independently testable.
- Define thresholds, exclusions, null handling, duplicate handling, currency rules, and date windows.
- Link every finding to affected source records and calculation evidence.
- Prevent double-counting across detector families and aggregate exposure.
- Calibrate predictive models on held-out data; publish precision/recall and limitations; keep predictions separate from verified discrepancies.
- Preserve the known late/short-delivery model evaluation only after reproducing its metrics on the current code and test data.

Acceptance:
- Synthetic fixtures cover true positives, true negatives, edge cases, missing data, duplicates, reversals, and boundary thresholds.
- Every displayed total can be recomputed from evidence rows.
- Amounts are described as potential exposure / amount to review unless confirmed by an authorized review process.
- No detector claims coverage when required source fields are absent.

**Status:** The current engine and plain-language layer implement four established detector families: short delivery, price creep/overbilling, slow approvals, and supplier-performance decline. The codebase includes detector and regression tests, but the full nine-page audit, complete source-row reconciliation for every displayed exposure, expanded detector coverage, and independent reproduction of previously reported model metrics remain outstanding. Do not present predictive warnings as confirmed losses.

## Phase 6 — Ask Seepsight and AI explanations

**Intended effect:** Users can ask natural-language questions and receive clear, accurate explanations based on authorized company evidence.

Work:
- Intent classification and question routing against the current company workspace.
- Grounded answers for findings, exposure, suppliers, approval delays, delivery performance, cases, and reports.
- Evidence references for numeric answers; verify calculations against source rows.
- Gemini classification and NVIDIA NIM explanation integration where configured and justified.
- Consent and policy controls for cloud inference; local/on-device path where supported.
- Prompt-injection and data-exfiltration protections; do not treat uploaded content as instructions.
- Clear uncertainty, refusal, and “not enough data” responses.
- Audit and privacy controls for conversation storage and model requests.

Acceptance:
- Questions with known answers match independently calculated expected results.
- Questions outside available data are not guessed.
- Cross-company and unauthorized records cannot be retrieved through prompts.
- Numeric answers are traceable to authorized source records.
- Provider outage, timeout, invalid response, and consent denial degrade safely.

**Status:** A grounded Ask workflow is now integrated in `pages/ask.py` with deterministic `ask_engine.py` answers, question-aware `hybrid_retrieval.py` context, company-workspace scoping, bounded Firestore retrieval, and the native Hybrid AI request handoff. PR #18 integrated the Ask workspace and retrieval-coverage tests; PR #19 capped retrieval to 10 returned records and a 5,000-record scan budget to avoid unbounded reads/context. Remaining acceptance: broader expected-answer fixtures, cross-tenant negative tests across every retrieval path, evidence-reference validation, and live end-to-end behavior under realistic company datasets.

## Phase 7 — Firebase Hybrid AI companion

**Intended effect:** Provide a secure hybrid AI experience without bypassing company authorization or privacy controls.

Work:
- Preserve Firebase project `seepsight-hybrid-ai`, Hosting deployment, App Check registration, and existing companion.
- Verify on-device inference and explicit-consent cloud fallback.
- Verify Gemini Developer API through Firebase AI Logic, error handling, model availability, and data minimization.
- Ensure companion requests receive only the minimum authorized evidence required for the task.
- Verify no secrets or customer records are exposed in client bundles, browser storage, or logs.

Acceptance:
- Build and tests pass; App Check and authentication are enforced as designed.
- Consent denial prevents cloud inference.
- On-device failure and cloud fallback are observable and safe.
- Every answer remains evidence-grounded and tenant-scoped.

**Status:** The Firebase AI Logic companion includes explicit `ONLY_ON_DEVICE` behavior by default, per-request cloud-fallback consent, SDK-reported inference-route checks, App Check initialization, evidence-bounded prompts, and a numeric-consistency guardrail. The user confirmed on 2026-11-25 that on-device inference succeeded on a compatible desktop laptop. The user also tested from Android with cloud fallback explicitly selected and received an `IN_CLOUD` response; Chrome on Android is not supported by the documented Prompt API local-inference path. The numbered-Markdown-list false positive in the numeric guard was fixed in PR #23 (`35109a3`) with regression tests; PR-head hybrid web tests/build, Python security tests, and detection/regression tests passed. A Firebase Hosting deployment workflow is present on this branch. **Still outstanding:** verify the post-merge Hosting deployment, App Check enforcement on the exact deployed domain, consent-denied behavior (no cloud request), repeatable inference on the supported laptop, and the complete authenticated Streamlit-to-companion journey. The standalone companion currently does not persist its prompts or generated answers to Firestore; do not treat its Firebase-ready indicator as proof of Firestore persistence.

## Product pages and workflows

### Overview
- Show trustworthy company-specific procurement KPIs, exposure, trends, priority risks, and data freshness.
- Explain coverage and data-quality limitations.
- No simulated customer metrics.

### Findings
- Show finding type, severity, amount to review, affected entities/orders, evidence, calculation, confidence/limitations, owner, and review status.
- Support filtering, drill-down, export, and status history.

### Suppliers
- Show supplier identity, spend/exposure, delivery and fulfilment performance, price variance, trend, and supporting orders.
- Normalize supplier identity across source datasets without merging distinct suppliers incorrectly.

### Cases and Actions
- Convert findings into cases, assign owners, due dates, actions, notes, evidence, and statuses.
- Preserve a full audit trail and company-level access control.

### Reports
- Generate reproducible, date-scoped reports with filters, currency labels, methodology, source coverage, and export.
- Ensure report totals reconcile to findings and evidence.

### Company Profile
- Manage verified company details, workspace configuration, and membership with role-based permissions.
- Keep company profile changes auditable.

### Settings
- Manage integrations, data refresh, notifications, access, privacy, retention, and AI consent.
- Never display secret values after saving.

### Connect Your Data
- Guide users through connection, preview, classification, mapping, validation, persistence, sync, and detector coverage.
- Clearly distinguish connected, validated, synced, and analyzed states.

## Integrations, automation, and operations

**Intended effect:** Keep data current and make routine procurement monitoring dependable.

Work:
- Scheduled and manual refresh with job status, retry policy, idempotency, and failure alerts.
- Integration lifecycle for supported cloud databases and file sources.
- Notifications for new high-priority findings, failed syncs, and assigned actions, respecting user preferences.
- Operational logging, metrics, trace IDs, health checks, and incident diagnostics without leaking sensitive data.

Acceptance:
- Jobs can be retried safely and do not duplicate records or findings.
- Failed refreshes are visible and do not overwrite good data with partial data.
- Notifications link to authorized resources and respect role/access changes.

## Final quality, security, and release gate

Before declaring the platform complete:
- Run unit, integration, regression, security, dependency, and end-to-end tests.
- Test all nine pages with empty, valid, incomplete, and large company datasets.
- Test tenant isolation and role permissions across every service and page.
- Test ingestion formats, mapping corrections, sync retries, database failures, and storage failures.
- Reconcile dashboard, findings, supplier, case, and report totals.
- Test AI grounding, consent, prompt injection, privacy, provider outages, and unsupported questions.
- Check accessibility, responsive layout, loading/error/empty states, performance, and deployment configuration.
- Verify Firebase companion and Streamlit application as one user journey.
- Document deployment, environment variables, secrets setup, migrations, backup/restore, retention, and rollback.

## Immediate execution order

1. Keep all work on `feature/company-auth`; keep `main` untouched and do not merge divergent historical feature branches wholesale.
2. Complete the production acceptance checks for Firebase/Firestore persistence, Secret Manager IAM, database credentials/network/TLS, and restart/recovery.
3. Reconcile every detector's displayed exposure to its source rows and reproduce the model evaluation on the current code.
4. Expand and run tenant-isolation and role-denial tests across datasets, findings, suppliers, cases, reports, exports, and AI retrieval.
5. Complete expected-answer, prompt-injection, unsupported-number, consent-denial, provider-failure, and live on-device/cloud route tests.
6. Exercise all nine pages with empty, valid, incomplete, and large workspaces; verify navigation, responsive states, and data freshness.
7. Verify the Firebase companion deployment, App Check enforcement, and the complete Streamlit-to-companion handoff.
8. Record exact test commands/results, live manual checks, limitations, and the final release/rollback decision.

## Evidence and status discipline

For every task, record:
- requirement and intended user/business effect;
- files/modules changed;
- tests added and exact command/results;
- manual verification performed;
- remaining limitations;
- commit SHA on `feature/company-auth`.

Do not label work “complete”, “secure”, “production-ready”, or “deployed” without the corresponding evidence. This document is the master plan; it does not itself mean the listed work has been implemented.


## Branch consolidation record — 2026-11-25

**Canonical working branch:** `feature/company-auth` (head at consolidation review: `35109a33b9d0c970c2d2572af22854943dc717a8`). **Protected branch:** `main` remains unchanged. There were no open pull requests at the time of this review.

The following reviewed work is already represented in the canonical branch through merged pull requests:
- PR #18 — dataset management, company/workspace isolation, connection placement, Gemini evidence-review workflow, and Ask workspace integration.
- PR #19 — bounded company-dataset retrieval (10 returned records; 5,000-record scan budget) and incomplete-coverage disclosure.
- PR #21 — enterprise interface styling refresh.
- PR #22 — master implementation plan/status documentation.
- PR #23 — numeric guard fix so numbered Markdown explanation lists are not mistaken for unsupported procurement figures; unsupported figures remain guarded.

Branch review and disposition:
- `integration/seepsight-unified-staging`: its dataset-management/company-isolation commit has the exact same Git tree as the PR #18 commit already on `feature/company-auth`; its two later retrieval-coverage/test commits also have unchanged trees. No missing application changes need to be merged from this branch.
- `test/hybrid-retrieval-coverage-signals` and `test/ask-hybrid-workspace-e2e-coverage`: their retrieval tests are older snapshots. The canonical branch already contains the later tests, including partial-scan coverage warnings and tenant-scoped retrieval checks. Do not replace the canonical tests with the older branch copies.
- `feature/dataset-management-and-connectors`, `feature/dataset-retrieval-coverage`, `feature/ask-hybrid-ai-workspace`, `feature/hybrid-ai-native-ask`, `feature/hybrid-ai-workspace-retrieval`, `feature/phase8-unified-hybrid-assistant`, `fix/ask-hybrid-ai-reliability`, and `fix/bounded-hybrid-retrieval`: these are historical/diverged work branches. Their relevant integrated work is represented by PRs #18 and #19; their branch snapshots predate later canonical fixes. Do not merge them wholesale over the canonical branch.
- `design/enterprise-refresh`, `design/enterprise-refresh-company-auth`, and `design/enterprise-refresh-validated`: earlier UI/prompt snapshots; the current styling and numeric-guard fixes are already in the canonical branch through PRs #21 and #23.
- `fix/hybrid-ai-list-number-guard`: pre-merge source branch for PR #23; its fix and regression tests are already in the canonical branch.
- `fix/engine-detection`: matches the historical `main` line and is substantially behind the canonical branch; it is not a source for consolidation.

**Consolidation outcome:** No additional application code was found that should be merged wholesale from the reviewed historical branches. The canonical branch contains the integrated feature work and subsequent fixes. Historical branches are intentionally left in place; this consolidation does not delete branches or change `main`. Future corrections should be made directly on `feature/company-auth`, with automated tests and the live acceptance evidence updated alongside the code.
