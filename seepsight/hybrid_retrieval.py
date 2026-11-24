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


def retrieve_workspace_context(workspace, question, cases=None):
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
