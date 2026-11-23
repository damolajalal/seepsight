# Phase 3 external connector configuration

The connector layer is optional and server-side. Streamlit state stores only a
Secret Manager resource reference such as
`projects/PROJECT_ID/secrets/SECRET_NAME/versions/latest`; it must never store
the secret payload or a database password.

## Secret payloads

Store one JSON object per database credential in Google Secret Manager.

- PostgreSQL: `host`, `port`, `database`, `username`, `password`, and optional `sslmode` (`require`, `verify-ca`, or `verify-full`) and `sslrootcert`.
- MySQL: `host`, `port`, `database`, `username`, `password`. The adapter requires certificate and hostname verification.
- SQL Server: `host`, `port`, `database`, `username`, `password`, and optional ODBC `driver`. The driver must be installed on the host; encryption and certificate validation are enabled.
- BigQuery: service-account JSON fields, preferably held in Secret Manager, with `project_id` and optional `maximum_bytes_billed`.

Use database principals that have SELECT-only grants. The adapters reject mutation
statements, use parameter binding, impose connection/query timeouts, cap returned
rows at 1,000, and enforce read-only transaction/session settings where the
provider supports them. BigQuery also applies a maximum bytes-billed cap.

## Optional runtime dependencies

Install only the connector dependencies required by the deployment:

```bash
pip install -r requirements-connectors.txt
```

The runtime identity also needs `secretmanager.versions.access` on only the
required secrets. Secret rotation is performed by adding a new Secret Manager
version and updating the stored reference; the application does not copy secret
values into Firestore or session state.

These modules are implemented and unit-tested, but live provider connections,
Secret Manager IAM, network allowlists, TLS certificates, and database
read-only grants must be configured and verified in the target environment.
