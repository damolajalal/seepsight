# Optional BigQuery enrichment for Ask Seepsight

This integration is **off by default**. It reads from the existing `traceiq-514409.traceiq` dataset and does not upload, modify, or delete procurement data.

## Security and isolation

- Create a dedicated service account for this integration. Do not reuse the Firebase Admin service account.
- Grant the service account **BigQuery Job User** on project `traceiq-514409`.
- Grant **BigQuery Data Viewer** on dataset `traceiq` only (dataset-level access, not project-wide data access).
- The application runs fixed, read-only `SELECT` statements against an allowlist of curated views.
- The current authenticated company must be explicitly listed in `allowed_company_ids`. This is important because the existing BigQuery dataset does not contain a company/tenant ID column.
- Results are supplementary reference data. They are clearly labelled as coming from BigQuery and are not represented as part of the current session upload.
- Query processing is capped at 50 MB by default (configurable up to 100 MB) and results are limited to 12 rows.
- If configuration, authentication, permissions, or a query fails, Ask Seepsight silently retains its existing workspace-only answer.

## Configure Google Cloud access

1. In Google Cloud Console, open project `traceiq-514409`.
2. Open **IAM & Admin → Service Accounts** and create a dedicated service account, for example `seepsight-ask-reader`.
3. Grant it **BigQuery Job User** on project `traceiq-514409`.
4. Open BigQuery, select dataset `traceiq`, open **Sharing / Permissions**, and grant the service account **BigQuery Data Viewer** on that dataset only.
5. Create a JSON key for this dedicated service account. Keep the downloaded key private. Never paste it into chat, GitHub, or source code.

These IAM steps do not require activating a billing account. BigQuery Sandbox restrictions still apply; the code uses read-only queries and a maximum-bytes-billed cap.

## Configure Streamlit secrets

In Streamlit Community Cloud, open the Seepsight app's **Manage app → Settings → Secrets**. Add the following TOML, replacing the placeholders. Paste the entire downloaded service-account JSON as the value of `service_account_json`.

```toml
[bigquery_enrichment]
enabled = true
project_id = "traceiq-514409"
dataset_id = "traceiq"
allowed_company_ids = ["PASTE_THE_COMPANY_ID_SHOWN_IN_ASK_SEEPSIGHT"]
maximum_bytes_billed = 50000000
service_account_json = """PASTE_THE_COMPLETE_SERVICE_ACCOUNT_JSON_HERE"""
```

Save the secrets and allow Streamlit to restart the app. The feature remains disabled until this configuration is present and the current company ID matches the allowlist.

## Views currently queried

- `v_findings_register`
- `v_short_delivery`
- `v_price_variance`
- `v_slow_approvals`
- `v_supplier_deterioration`
- `v_supplier_month`

The view is selected from the question category. User-entered text is never inserted into SQL.

## Important data-retention note

The current BigQuery Explorer screenshot showed object expiration dates in January 2027. Check the dataset's retention/expiration settings before depending on these records long-term. This integration does not change those settings.
