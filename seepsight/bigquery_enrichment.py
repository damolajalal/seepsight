"""Optional, read-only BigQuery enrichment for Ask Seepsight.

This module is deliberately dormant unless an owner configures a dedicated
read-only service account and explicitly allowlists the authenticated company.
It queries only fixed, curated views; it never accepts model/user-supplied SQL.
"""
import json
import re

import streamlit as st


_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]{1,1024}$")
_MAX_BYTES_BILLED_DEFAULT = 50_000_000
_MAX_ROWS = 12


def _settings(company_id):
    """Return validated settings only for an explicitly allowlisted company."""
    try:
        config = st.secrets.get("bigquery_enrichment", {})
    except Exception:
        return None
    if not isinstance(config, dict) or not config.get("enabled"):
        return None
    allowed = config.get("allowed_company_ids", [])
    if isinstance(allowed, str):
        allowed = [allowed]
    if not isinstance(allowed, (list, tuple, set)) or str(company_id or "") not in {
        str(value) for value in allowed
    }:
        return None

    project_id = str(config.get("project_id", "")).strip()
    dataset_id = str(config.get("dataset_id", "traceiq")).strip()
    if not _IDENTIFIER.fullmatch(project_id) or not _IDENTIFIER.fullmatch(dataset_id):
        raise ValueError("BigQuery project or dataset configuration is invalid.")

    credentials_info = config.get("service_account_json")
    if isinstance(credentials_info, str):
        credentials_info = json.loads(credentials_info)
    if not isinstance(credentials_info, dict):
        raise ValueError("A dedicated BigQuery read-only service-account JSON is required.")

    try:
        maximum_bytes_billed = int(
            config.get("maximum_bytes_billed", _MAX_BYTES_BILLED_DEFAULT)
        )
    except (TypeError, ValueError):
        maximum_bytes_billed = _MAX_BYTES_BILLED_DEFAULT
    if not 1_000_000 <= maximum_bytes_billed <= 100_000_000:
        raise ValueError("BigQuery maximum_bytes_billed must be between 1 MB and 100 MB.")

    return {
        "project_id": project_id,
        "dataset_id": dataset_id,
        "credentials_info": credentials_info,
        "maximum_bytes_billed": maximum_bytes_billed,
    }


def _query_for_question(question, project_id, dataset_id):
    """Map a procurement question to one fixed, bounded SELECT over a curated view."""
    text = str(question or "").casefold()
    prefix = f"`{project_id}.{dataset_id}."
    suffix = "`"

    if any(term in text for term in ("short deliver", "under deliver", "under-deliver", "not received", "receipt shortage")):
        view = "v_short_delivery"
        sql = (
            f"SELECT v.po_id, v.supplier_id, s.supplier_name, v.invoice_date, "
            f"v.invoiced_qty, v.received_qty, v.units_short, v.leakage_ngn "
            f"FROM {prefix}v_short_delivery{suffix} AS v "
            f"LEFT JOIN {prefix}suppliers{suffix} AS s USING (supplier_id) "
            "ORDER BY v.leakage_ngn DESC LIMIT 12"
        )
    elif any(term in text for term in ("price", "overpay", "overpriced", "invoice discrepancy", "price variance")):
        view = "v_price_variance"
        sql = (
            f"SELECT v.po_id, v.supplier_id, s.supplier_name, v.invoice_date, "
            f"v.po_unit_price, v.invoice_unit_price, v.pct_over, v.leakage_ngn "
            f"FROM {prefix}v_price_variance{suffix} AS v "
            f"LEFT JOIN {prefix}suppliers{suffix} AS s USING (supplier_id) "
            "ORDER BY v.leakage_ngn DESC LIMIT 12"
        )
    elif any(term in text for term in ("approval", "approvals", "approval delay", "approval time")):
        view = "v_slow_approvals"
        sql = (
            f"SELECT v.po_id, v.branch_id, v.supplier_id, s.supplier_name, "
            f"v.po_total, v.approval_days FROM {prefix}v_slow_approvals{suffix} AS v "
            f"LEFT JOIN {prefix}suppliers{suffix} AS s USING (supplier_id) "
            "ORDER BY v.approval_days DESC LIMIT 12"
        )
    elif any(term in text for term in ("supplier", "vendor")) and any(
        term in text for term in ("trend", "performance", "deteriorat", "reliab", "late", "fill rate", "declin")
    ):
        view = "v_supplier_deterioration"
        sql = (
            f"SELECT v.supplier_id, s.supplier_name, v.early_days_late, "
            f"v.recent_days_late, v.worsening_days, v.early_fill_rate, "
            f"v.recent_fill_rate FROM {prefix}v_supplier_deterioration{suffix} AS v "
            f"LEFT JOIN {prefix}suppliers{suffix} AS s USING (supplier_id) "
            "ORDER BY v.worsening_days DESC LIMIT 12"
        )
    elif any(term in text for term in ("monthly", "month by month", "over time", "supplier trend")):
        view = "v_supplier_month"
        sql = (
            f"SELECT v.supplier_id, s.supplier_name, v.month, v.deliveries, "
            f"v.avg_days_late, v.late_rate, v.fill_rate "
            f"FROM {prefix}v_supplier_month{suffix} AS v "
            f"LEFT JOIN {prefix}suppliers{suffix} AS s USING (supplier_id) "
            "ORDER BY v.month DESC, v.late_rate DESC LIMIT 12"
        )
    elif any(term in text for term in ("finding", "exposure", "leakage", "risk", "issue", "investigate", "what did you find")):
        view = "v_findings_register"
        sql = (
            f"SELECT finding_id, finding_type, entity, severity, affected_orders, "
            f"leakage_ngn, orders_held_ngn, first_seen, last_seen, evidence "
            f"FROM {prefix}v_findings_register{suffix} "
            "ORDER BY leakage_ngn DESC LIMIT 12"
        )
    else:
        return None, None

    return view, sql


def enrich_question(question, company_id):
    """Return bounded BigQuery reference rows, or a safe no-op/fallback status."""
    try:
        settings = _settings(company_id)
        if settings is None:
            return {"status": "disabled"}
        view, sql = _query_for_question(
            question, settings["project_id"], settings["dataset_id"]
        )
        if not sql:
            return {"status": "not_relevant"}

        from google.cloud import bigquery
        from google.oauth2 import service_account

        credentials = service_account.Credentials.from_service_account_info(
            settings["credentials_info"],
            scopes=["https://www.googleapis.com/auth/bigquery"],
        )
        client = bigquery.Client(
            project=settings["project_id"],
            credentials=credentials,
        )
        job_config = bigquery.QueryJobConfig(
            use_legacy_sql=False,
            use_query_cache=True,
            maximum_bytes_billed=settings["maximum_bytes_billed"],
        )
        job = client.query(sql, job_config=job_config, timeout=8)
        rows = list(job.result(max_results=_MAX_ROWS, timeout=8))
        columns = [field.name for field in job.schema]
        records = [dict(row.items()) for row in rows]
        if not records:
            return {
                "status": "empty",
                "view": view,
                "project_id": settings["project_id"],
                "dataset_id": settings["dataset_id"],
            }
        rendered = json.dumps(records, ensure_ascii=False, default=str, indent=2).replace("`", "\\u0060")
        return {
            "status": "ok",
            "view": view,
            "project_id": settings["project_id"],
            "dataset_id": settings["dataset_id"],
            "row_count": len(records),
            "columns": columns,
            "records_text": rendered[:8000],
        }
    except Exception:
        # BigQuery must never prevent the existing workspace answer from rendering.
        return {"status": "unavailable"}
