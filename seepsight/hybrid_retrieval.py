"""Question-aware, bounded retrieval from the authenticated company workspace."""

import re

import pandas as pd


_TABLES = {
    "findings": ("findings", ("finding", "issue", "risk", "priority", "severity", "exposure", "problem")),
    "evidence": ("evidence", ("evidence", "proof", "invoice", "purchase order", "receipt", "delivery")),
    "exposure": ("exposure", ("supplier", "vendor", "spend", "exposure", "concentration", "top")),
    "monthly": ("monthly", ("trend", "monthly", "month", "over time", "delivery trend")),
    "supplier_month": ("supplier_month", ("supplier", "vendor", "monthly", "performance", "trend")),
    "risk_orders": ("risk", ("order", "orders", "late", "delay", "short", "risk", "delivery")),
    "explanations": ("explanations", ("explanation", "why", "reason", "cause", "model")),
    "scorecard": ("scorecard", ("scorecard", "score", "performance", "supplier rating", "kpi")),
}


_DATASET_HINTS = {
    "orders": [
        "order",
        "purchase order",
        "po",
        "purchasing"
    ],
    "receipts": [
        "receipt",
        "delivery",
        "deliver",
        "received",
        "goods"
    ],
    "invoices": [
        "invoice",
        "bill",
        "price discrepancy",
        "billing"
    ],
    "approvals": [
        "approval",
        "approver",
        "approval delay"
    ],
    "suppliers": [
        "supplier",
        "vendor",
        "exposure",
        "concentration",
        "supplier performance"
    ],
    "products": [
        "product",
        "item",
        "sku",
        "commodity"
    ],
    "inventory": [
        "inventory",
        "stock",
        "warehouse"
    ],
    "payments": [
        "payment",
        "paid",
        "remittance",
        "settlement"
    ],
    "requisitions": [
        "requisition",
        "requestor",
        "purchase request"
    ],
    "contracts": [
        "contract",
        "agreement"
    ],
    "quotations": [
        "quotation",
        "quote",
        "bid",
        "tender",
        "rfq"
    ],
    "returns": [
        "return",
        "dispute",
        "claim",
        "rejected",
        "credit note"
    ]
}


def _append_saved_dataset_context(sections, company_id, question, terms, broad):
    """Retrieve bounded normalized rows and mappings from this company's saved datasets."""
    from seepsight import firestore_db

    datasets = firestore_db.get_company_datasets(company_id)
    if not datasets:
        sections.append("Ingested datasets: no saved dataset metadata is available.")
        return

    q = question.casefold()
    selected_types = set()
    for dataset_type, triggers in _DATASET_HINTS.items():
        if any(trigger in q for trigger in triggers):
            selected_types.add(dataset_type)
    if broad:
        selected_types = {str(item.get("dataset_type") or "") for item in datasets}
    if not selected_types:
        for item in datasets:
            haystack = f"{item.get('dataset_type', '')} {item.get('filename', '')}".casefold()
            if any(term in haystack for term in terms):
                selected_types.add(str(item.get("dataset_type") or ""))
    if not selected_types:
        selected_types = {str(item.get("dataset_type") or "") for item in datasets[:3]}

    include_source = any(word in q for word in ("source row", "source data", "original row", "raw row", "raw data", "uploaded columns"))
    if include_source:
        sections.append("Source-row retrieval was explicitly requested. Original file bytes are never sent to Hybrid AI.")

    selected = [
        item for item in datasets
        if str(item.get("dataset_type") or "") in selected_types
    ]
    if not selected:
        sections.append("Ingested datasets: no saved dataset matches the question's procurement area.")
        return

    sections.append("Saved ingestion datasets and normalized procurement records:")
    for item in selected[:12]:
        dataset_id = str(item.get("id") or item.get("dataset_id") or "").strip()
        dataset_type = str(item.get("dataset_type") or "Unclassified")
        filename = str(item.get("filename") or "Filename not recorded")
        sections.append(
            f"Dataset {dataset_type}: file={filename}; "
            f"normalized rows={item.get('record_count', item.get('normalized_record_count', 'not recorded'))}; "
            f"source rows={item.get('source_record_count', 'not recorded')}; "
            f"status={item.get('status', 'not recorded')}"
        )
        if not dataset_id:
            sections.append(f"{dataset_type}: dataset identifier is unavailable; records were not queried.")
            continue
        try:
            mapping = firestore_db.get_company_mapping(company_id, dataset_id)
            if isinstance(mapping, dict) and mapping:
                mapping_lines = [
                    f"{field} -> {str(details)[:160]}"
                    for field, details in list(mapping.items())[:24]
                ]
                sections.append(f"{dataset_type} confirmed field mapping: " + "; ".join(mapping_lines))
            normalized = firestore_db.search_dataset_records(
                company_id, dataset_id, terms if not broad else [],
                collection_name="records", limit=7, scan_limit=1500,
            )
            sections.append(
                f"{dataset_type} normalized rows (scanned {normalized['scanned_count']} of "
                f"{normalized['total_count']}):"
            )
            sections.append(_format_rows(f"{dataset_type} normalized records", normalized["records"]))
            if normalized.get("scan_limited"):
                sections.append(
                    f"{dataset_type}: retrieval scanned a bounded prefix only; later records may not be represented."
                )
            if include_source:
                source = firestore_db.search_dataset_records(
                    company_id, dataset_id, terms, collection_name="source_records",
                    limit=4, scan_limit=500,
                )
                sections.append(_format_rows(f"{dataset_type} source rows", source["records"]))
                if source.get("scan_limited"):
                    sections.append(f"{dataset_type}: source-row search was bounded and may not cover later records.")
        except (FileNotFoundError, RuntimeError, ValueError, PermissionError) as exc:
            sections.append(f"{dataset_type}: saved rows could not be retrieved ({str(exc)[:180]}).")


_MAX_ROWS_PER_TABLE = 18
_MAX_ROW_CHARS = 900
_MAX_CONTEXT_CHARS = 12000


def _normalise_text(value):
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _frame_records(frame):
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return []
    return frame.to_dict("records")


def _row_text(row):
    return " ".join(f"{key} {_normalise_text(value)}" for key, value in row.items())


def _select_rows(frame, terms, limit=_MAX_ROWS_PER_TABLE):
    records = _frame_records(frame)
    if not records:
        return []
    if not terms:
        return records[:limit]
    scored = []
    for index, row in enumerate(records):
        haystack = _row_text(row).casefold()
        score = sum(1 for term in terms if term in haystack)
        if score:
            scored.append((score, -index, row))
    scored.sort(reverse=True, key=lambda item: (item[0], item[1]))
    return [item[2] for item in scored[:limit]] if scored else records[:limit]


def _format_rows(label, rows):
    if not rows:
        return f"{label}: no saved records available."
    lines = [f"{label} ({len(rows)} selected record(s)):"]
    for row in rows:
        parts = []
        for key, value in row.items():
            text = _normalise_text(value)
            if not text:
                continue
            text = re.sub(r"\s+", " ", text)[:240]
            parts.append(f"{key}={text}")
        line = "; ".join(parts)
        if line:
            lines.append("- " + line[:_MAX_ROW_CHARS])
    return "\n".join(lines)


def retrieve_workspace_context(workspace, question, cases=None, company_id=None):
    """Return relevant saved records and transparent coverage notes for one question."""
    if not isinstance(workspace, dict):
        raise ValueError("The authenticated company workspace is unavailable.")
    question = _normalise_text(question)
    if not question:
        raise ValueError("Enter a question before asking Hybrid AI.")

    terms = [
        term for term in re.findall(r"[a-z0-9₦$%_-]{3,}", question.casefold())
        if term not in {"the", "and", "for", "with", "from", "what", "which", "does", "about", "this", "that", "are", "how", "can", "our", "your"}
    ]
    q = question.casefold()
    selected_names = []
    for key, (pack_key, triggers) in _TABLES.items():
        if any(trigger in q for trigger in triggers):
            selected_names.append((key, pack_key))
    if not selected_names:
        selected_names = [(key, value[0]) for key, value in _TABLES.items()]

    # Broad questions receive a compact cross-workspace view; specific questions
    # receive only tables whose subject matches the question.
    broad = any(word in q for word in ("overview", "summarise", "summary", "all risks", "overall", "across", "workspace"))
    if broad:
        selected_names = [(key, value[0]) for key, value in _TABLES.items()]

    company = _normalise_text(workspace.get("name")) or "Authenticated company"
    currency = _normalise_text(workspace.get("cur")) or "NGN"
    sections = [
        f"Authenticated company workspace: {company}",
        f"Reporting currency: {currency}",
        f"User question: {question}",
        "Retrieval scope: current active company workspace; selected rows only. This is not a complete export.",
    ]
    run_log = workspace.get("log") or {}
    detectors = run_log.get("detectors") or {}
    if isinstance(detectors, dict) and detectors:
        sections.append(
            "Detector coverage: " + "; ".join(
                f"{name}={status}" for name, status in detectors.items()
            )
        )
        incomplete = [
            str(name) for name, status in detectors.items()
            if str(status).casefold() != "ready"
        ]
        if incomplete:
            sections.append(
                "Coverage warning: checks not marked ready: "
                + ", ".join(incomplete)
                + ". Missing or incomplete checks must not be treated as clean results."
            )

    available = set()
    for key, pack_key in selected_names:
        frame = workspace.get(pack_key)
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            available.add(key)
        rows = _select_rows(frame, terms)
        sections.append(_format_rows(key.replace("_", " ").title(), rows))

    if "findings" in available:
        finding_frame = workspace.get("findings")
        evidence_frame = workspace.get("evidence")
        ids = set()
        if isinstance(finding_frame, pd.DataFrame) and "finding_id" in finding_frame.columns:
            ids = set(finding_frame["finding_id"].dropna().astype(str))
        if isinstance(evidence_frame, pd.DataFrame) and "finding_id" in evidence_frame.columns and ids:
            linked = evidence_frame[evidence_frame["finding_id"].astype(str).isin(ids)]
            evidence_rows = _select_rows(linked, terms, limit=12)
            sections.append(_format_rows("Linked evidence", evidence_rows))

    if cases is not None:
        case_lines = []
        if isinstance(cases, dict):
            for finding_id, case in list(cases.items())[:80]:
                if not isinstance(case, dict):
                    continue
                blob = " ".join([
                    str(finding_id), str(case.get("status", "")),
                    str(case.get("owner", "")), str(case.get("note", "")),
                    " ".join(str(x) for x in case.get("history", [])[-3:]),
                ])
                case_question = any(word in q for word in ("case", "action", "investigation", "owner", "assigned"))
                if broad or case_question or not terms or any(term in blob.casefold() for term in terms):
                    case_lines.append(
                        f"- Case {finding_id}: status={case.get('status', 'Unknown')}; "
                        f"owner={case.get('owner', '')}; note={str(case.get('note', ''))[:300]}; "
                        f"recent activity={' | '.join(str(x)[:180] for x in case.get('history', [])[-3:])}"
                    )
                if len(case_lines) >= 12:
                    break
        sections.append("Cases and actions:\n" + ("\n".join(case_lines) if case_lines else "No matching saved case records."))

    if company_id:
        _append_saved_dataset_context(sections, company_id, question, terms, broad)

    missing = [
        key.replace("_", " ") for key, pack_key in selected_names
        if not isinstance(workspace.get(pack_key), pd.DataFrame) or workspace.get(pack_key).empty
    ]
    if missing:
        sections.append("Coverage limitations: no saved records were available for " + ", ".join(missing) + ". Do not treat absent records as zero risk.")
    sections.append(
        "Evidence references: cite the table name and the record identifier (such as finding_id, supplier, order_id, or case ID) shown above. "
        "Do not invent identifiers or numeric facts. Distinguish observed records from recommendations."
    )
    result = "\n\n".join(sections)
    return result[:_MAX_CONTEXT_CHARS]
