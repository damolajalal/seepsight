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
    """Retrieve all matching normalized rows and mapped fields from saved company datasets."""
    from seepsight import firestore_db

    datasets = firestore_db.get_company_datasets(company_id)
    if not datasets:
        sections.append("Ingested datasets: no saved dataset metadata is available.")
        return

    q = question.casefold()
    case_only = any(word in q for word in ("case", "cases", "investigation", "assigned", "owner")) and not any(
        trigger in q for triggers in _DATASET_HINTS.values() for trigger in triggers
    )
    if case_only:
        sections.append("Ingested datasets: not queried because this question is about case ownership or activity.")
        return

    selected_types = set()
    for dataset_type, triggers in _DATASET_HINTS.items():
        if any(trigger in q for trigger in triggers):
            selected_types.add(dataset_type)
    if any(word in q for word in ("supplier", "vendor", "exposure", "concentration", "spend")):
        selected_types.update({"suppliers", "orders", "invoices", "payments"})
    if any(word in q for word in ("late", "delivery", "deliver", "short", "receipt")):
        selected_types.update({"orders", "receipts"})
    if any(word in q for word in ("invoice", "bill", "price", "discrepancy")):
        selected_types.update({"orders", "invoices"})
    if any(word in q for word in ("approval", "approver")):
        selected_types.update({"orders", "approvals"})
    if any(word in q for word in ("payment", "paid", "remittance")):
        selected_types.update({"payments", "invoices"})
    if any(word in q for word in ("product", "item", "stock", "inventory")):
        selected_types.update({"products", "inventory", "orders"})
    if any(word in q for word in ("contract", "agreement", "quotation", "quote", "bid", "tender")):
        selected_types.update({"contracts", "quotations"})
    if any(word in q for word in ("return", "dispute", "claim", "rejected")):
        selected_types.update({"returns", "invoices"})
    if broad:
        selected_types = {str(item.get("dataset_type") or "") for item in datasets}
    if not selected_types:
        for item in datasets:
            haystack = f"{item.get('dataset_type', '')} {item.get('filename', '')}".casefold()
            if any(term in haystack for term in terms):
                selected_types.add(str(item.get("dataset_type") or ""))
    if not selected_types:
        selected_types = {str(item.get("dataset_type") or "") for item in datasets[:3]}

    if any(word in q for word in ("supplier", "vendor", "exposure", "concentration", "spend")):
        terms.extend(["supplier", "vendor", "po_id", "payment_amount"])
    if any(word in q for word in ("late", "delivery", "deliver", "short", "receipt")):
        terms.extend(["supplier", "promised_date", "received_date", "ordered_qty", "received_qty", "po_id"])
    if any(word in q for word in ("invoice", "bill", "price", "discrepancy")):
        terms.extend(["supplier", "invoice", "invoice_unit_price", "po_unit_price", "invoice_qty", "po_id"])
    if any(word in q for word in ("approval", "approver")):
        terms.extend(["approval", "approval_requested_at", "approval_completed_at", "po_id"])
    terms = list(dict.fromkeys(terms))
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
                    for field, details in mapping.items()
                ]
                sections.append(f"{dataset_type} confirmed field mapping: " + "; ".join(mapping_lines))
            normalized = firestore_db.search_dataset_records(
                company_id, dataset_id, terms if not broad else [],
                collection_name="records", limit=250000,
            )
            sections.append(
                f"{dataset_type} normalized rows: scanned {normalized['scanned_count']} records; "
                f"{normalized.get('match_count', len(normalized['records']))} matched; "
                f"{len(normalized['records'])} included in context; "
                f"coverage {'complete' if normalized.get('coverage_complete', not normalized.get('scan_limited', False)) else 'incomplete'}.
            )
            sections.append(_format_rows(f"{dataset_type} normalized records", normalized["records"]))
            if not normalized.get("coverage_complete", not normalized.get("scan_limited", False)):
                sections.append(
                    f"{dataset_type}: retrieval reached its read budget; later records may not be represented. "
                    "Do not conclude that no matching risk exists."
                )
            elif not normalized.get("match_count", len(normalized["records"])):
                sections.append(
                    f"{dataset_type}: no records matched the search terms in the complete normalized dataset scan."
                )
            if include_source:
                source_terms = [
                    term for term in terms
                    if term not in {"source", "data", "raw", "original", "row", "rows", "uploaded", "columns", "orders", "order", "purchase", "po"}
                ]
                source = firestore_db.search_dataset_records(
                    company_id, dataset_id, source_terms, collection_name="source_records",
                    limit=2, scan_limit=250,
                )
                sections.append(_format_rows(f"{dataset_type} source rows", source["records"]))
                if not source.get("coverage_complete", not source.get("scan_limited", False)):
                    sections.append(f"{dataset_type}: source-row search was bounded and may not cover later records.")
        except (FileNotFoundError, RuntimeError, ValueError, PermissionError) as exc:
            sections.append(f"{dataset_type}: saved rows could not be retrieved because the data source was unavailable or incomplete.")


_MAX_ROWS_PER_TABLE = 18
_MAX_ROW_CHARS = 500
_MAX_CONTEXT_CHARS = 40000


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
            text = re.sub(r"\s+", " ", text)
            parts.append(f"{key}={text}")
        line = "; ".join(parts)
        if line:
            lines.append("- " + line)
    return "\n".join(lines)


def retrieve_workspace_context(workspace, question, cases=None, company_id=None):
    """Return relevant saved records and transparent coverage notes for one question."""
    if not isinstance(workspace, dict):
        raise ValueError("The authenticated company workspace is unavailable.")
    question = _normalise_text(question)
    if not question:
        raise ValueError("Enter a question before asking Hybrid AI.")

    raw_terms = [
        term for term in re.findall(r"[a-z0-9₦$%_-]{3,}", question.casefold())
        if term not in {"the", "and", "for", "with", "from", "what", "which", "does", "about", "this", "that", "are", "how", "can", "our", "your"}
    ]
    terms = list(raw_terms)
    for term in raw_terms:
        if term.endswith("ies") and len(term) > 4:
            terms.append(term[:-3] + "y")
        elif term.endswith("s") and len(term) > 4:
            terms.append(term[:-1])
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
    comprehensive = broad or any(phrase in q for phrase in ("compare", "versus", " vs ", "entire dataset", "whole dataset", "all records", "all data", "all suppliers"))
    if broad:
        selected_names = [(key, value[0]) for key, value in _TABLES.items()]

    company = _normalise_text(workspace.get("name")) or "Authenticated company"
    currency = _normalise_text(workspace.get("cur")) or "NGN"
    sections = [
        f"Authenticated company workspace: {company}",
        f"Reporting currency: {currency}",
        f"User question: {question}",
        "Retrieval scope: current active company workspace. Relevant workspace tables and matching normalized dataset records are retrieved across available rows and fields; the context-size limit may still omit lower-priority content, which is reported below.",
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
        rows = _select_rows(frame, terms, limit=(len(frame) if comprehensive and isinstance(frame, pd.DataFrame) else (3 if broad else 10)))
        sections.append(_format_rows(key.replace("_", " ").title(), rows))

    if "findings" in available:
        finding_frame = workspace.get("findings")
        evidence_frame = workspace.get("evidence")
        ids = set()
        if isinstance(finding_frame, pd.DataFrame) and "finding_id" in finding_frame.columns:
            ids = set(finding_frame["finding_id"].dropna().astype(str))
        if isinstance(evidence_frame, pd.DataFrame) and "finding_id" in evidence_frame.columns and ids:
            linked = evidence_frame[evidence_frame["finding_id"].astype(str).isin(ids)]
            evidence_rows = _select_rows(linked, terms, limit=6)
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
    if len(result) <= _MAX_CONTEXT_CHARS:
        return result
    suffix = (
        "\n\nContext limit reached: some lower-priority records were omitted. "
        "Ask a more specific question to retrieve a narrower set of evidence."
    )
    return result[:_MAX_CONTEXT_CHARS - len(suffix)] + suffix
