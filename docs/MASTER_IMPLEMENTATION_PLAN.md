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

**Status:** Company-aware session workspace checks exist; durable backend authorization and full isolation tests need verification.

## Phase 3 — Database, durable storage, and security foundation

**Intended effect:** Customer data survives beyond a Streamlit session and is stored securely with company-level isolation.

Work:
- Private Google Cloud Storage service for raw uploads and generated artifacts, using company-scoped object paths and least-privilege access.
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

**Status:** Phase 3 code foundation implemented on `feature/company-auth`: company-scoped Firebase/Firestore authorization; durable dataset metadata, raw source rows and normalized records; exact Decimal serialization; revisioned analysis workspaces with transactional activation and retention; transactional case history; company audit events; bounded/idempotent ingestion and retry-safe deletion; private GCS helpers; Secret Manager references; and read-only PostgreSQL, MySQL, SQL Server and BigQuery adapters. The Settings page now provides owner-only connection profile creation, testing and enable/disable controls, enforced again in server-side service methods. Python security Run #133 passed 81 tests and hybrid web Run #163 passed on implementation commit `d649c84`. Production acceptance remains pending live Firebase/Firestore, private GCS bucket, Secret Manager IAM, database network/TLS/read-only credentials and live restart/failure-injection verification. Original upload bytes remain session-only until a private bucket is provisioned. See `docs/PHASE3_FOUNDATION_AUDIT.md` and `docs/PHASE3_CONNECTORS.md`.

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

**Status:** Current Connect page and engine support file onboarding, mappings, quality checks, and a 12-dataset registry. The page states that uploads/results remain session-based; database persistence/synchronisation and production durability remain outstanding. The current findings engine documents four established detector families.

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

**Status:** Existing engine and plain-language layer implement four established detector families. Full audit, detector expansion, end-to-end evidence checks, and reproduction of prior model metrics remain outstanding. A previously mentioned 42-test suite was not recovered and must not be assumed to exist.

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

**Status:** Current Ask page has deterministic, limited question patterns and an optional link to the Phase 7 companion. A complete grounded assistant service was not found at the previously checked path; broader AI integration and security tests remain outstanding.

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

**Status:** Companion was previously deployed and its Vite tests/build passed; inference, consent, evidence-grounding, and end-to-end privacy verification remain to be completed.

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

1. Reconfirm current `feature/company-auth` head and audit authentication/company identity implementation.
2. Define the storage/metadata interfaces and tenant authorization contract before wiring persistence into pages.
3. Implement Phase 3 storage and metadata services with tests and a local/fake backend for deterministic testing.
4. Add private cloud storage and Firestore adapters with configuration and failure handling.
5. Add Secret Manager-backed database connection adapters.
6. Integrate persistent upload/job state into Connect Your Data, then implement Phase 4 sync.
7. Reconcile and expand Phase 5 detectors and evidence tests.
8. Build the grounded Ask service and connect the Phase 7 companion.
9. Complete page-level integration, security review, and end-to-end release gate.

## Evidence and status discipline

For every task, record:
- requirement and intended user/business effect;
- files/modules changed;
- tests added and exact command/results;
- manual verification performed;
- remaining limitations;
- commit SHA on `feature/company-auth`.

Do not label work “complete”, “secure”, “production-ready”, or “deployed” without the corresponding evidence. This document is the master plan; it does not itself mean the listed work has been implemented.
