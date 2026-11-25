"""Grounded procurement Q&A for the authenticated company workspace.

This module deliberately answers from the current workspace tables only.
It does not invent facts or silently treat skipped detectors as clean results.
"""
import re

import pandas as pd

from seepsight import plain


def _frame(value):
    return value if isinstance(value, pd.DataFrame) else pd.DataFrame()


def _money(currency, value):
    try:
        return f"{currency} {float(value):,.2f}"
    except (TypeError, ValueError):
        return f"{currency} 0.00"


def _contains(text, patterns):
    return any(re.search(pattern, text) for pattern in patterns)


def _evidence_for(evidence, finding_id):
    if evidence.empty or "finding_id" not in evidence.columns:
        return evidence.iloc[0:0]
    return evidence[evidence["finding_id"].astype(str) == str(finding_id)]


def answer_question(workspace, question):
    """Return an evidence-grounded answer and optional supporting table."""
    q = str(question or "").strip()
    if not q:
        return {"answer": "Please enter a procurement question.", "table": None}

    text = q.casefold()
    currency = workspace.get("cur", "NGN")
    findings = _frame(workspace.get("findings"))
    evidence = _frame(workspace.get("evidence"))
    exposure = _frame(workspace.get("exposure"))
    monthly = _frame(workspace.get("monthly"))
    log = workspace.get("log") or {}
    detectors = log.get("detectors") or {}
    skipped = [name for name, status in detectors.items() if str(status).casefold() != "ready"]

    def finish(message, table=None):
        if skipped:
            message += (
                "\n\nCoverage note: this analysis has checks that did not run: "
                + ", ".join(skipped)
                + ". Treat the results as incomplete until those checks are resolved."
            )
        return {"answer": message, "table": table}

    if findings.empty:
        if skipped:
            return finish(
                "I can't confirm that procurement is clear. No findings were saved, "
                "and some checks could not run. Resolve the missing data or mappings "
                "and rerun the analysis."
            )
        if detectors:
            return finish(
                "The recorded checks completed without producing a qualifying finding. "
                "That conclusion applies only to the checks and fields listed in this analysis."
            )
        return finish(
            "There is no completed procurement analysis in this workspace yet. "
            "Connect the source files and run the checks first."
        )

    # Supplier-specific questions should be scoped to the named supplier.
    supplier_names = []
    if "supplier" in findings.columns:
        supplier_names = sorted(
            {str(x) for x in findings["supplier"].dropna().unique()},
            key=len,
            reverse=True,
        )
    matched_supplier = next((name for name in supplier_names if name.casefold() in text), None)

    # List/count questions about the full set of findings.
    if _contains(text, [r"how many", r"number of", r"count", r"all findings", r"list (?:the )?(?:issues|findings)", r"what did you find"]):
        counts = (
            findings.groupby(["finding_type", "severity"], dropna=False)
            .size().reset_index(name="count")
            .sort_values(["count", "severity"], ascending=[False, True])
        )
        message = f"I found {len(findings)} procurement finding(s) in this analysis."
        return finish(message, counts)

    # Highest exposure / supplier comparison.
    if _contains(text, [r"which supplier", r"top supplier", r"supplier.*(?:highest|most|largest)", r"who.*(?:cost|exposure|overpay)"]):
        if matched_supplier:
            subset = findings[findings["supplier"].astype(str).str.casefold() == matched_supplier.casefold()]
            amount = pd.to_numeric(subset.get("identified_exposure", 0), errors="coerce").fillna(0).sum()
            return finish(
                f"{matched_supplier} has {len(subset)} finding(s) in this analysis, with "
                f"{_money(currency, amount)} in potential cost exposure to review. "
                "This is an investigation amount, not a confirmed loss."
            )
        if not exposure.empty and {"supplier", "total"}.issubset(exposure.columns):
            table = exposure[["supplier", "total"]].copy()
            table["total"] = pd.to_numeric(table["total"], errors="coerce").fillna(0)
            table = table.sort_values("total", ascending=False).head(10)
            if table.empty:
                return finish("The analysis does not show supplier-level cost exposure.")
            top = table.iloc[0]
            return finish(
                f"{top['supplier']} has the highest recorded potential cost exposure at "
                f"{_money(currency, top['total'])}. The table shows the leading suppliers. "
                "These amounts need invoice and purchase-order review; they are not confirmed losses.",
                table.rename(columns={"supplier": "Supplier", "total": "Potential exposure"}),
            )
        return finish("Supplier-level exposure is not available in the saved analysis.")

    # Monthly purchasing-spend trend from the saved analysis table.
    if _contains(text, [r"spend.*(?:over time|trend|month|change)", r"how.*spend.*change", r"purchas(?:ing|e).*spend.*(?:trend|change|over time)", r"monthly spend"]):
        if monthly.empty:
            return finish("The saved analysis does not contain a monthly purchasing-spend table, so I can't establish a spend trend. Re-run the analysis with dated purchase-order records.")
        month_col = next((col for col in ("po_month", "month", "period", "month_start", "date") if col in monthly.columns), None)
        spend_col = next((col for col in ("spend", "total_spend", "purchasing_spend", "amount") if col in monthly.columns), None)
        if not month_col or not spend_col:
            return finish("The saved monthly table is missing a recognized month or spend field. I can't safely calculate a purchasing-spend trend from it.")
        trend = monthly[[month_col, spend_col]].copy()
        trend[spend_col] = pd.to_numeric(trend[spend_col], errors="coerce")
        trend["_period"] = pd.to_datetime(trend[month_col], errors="coerce")
        trend = trend.dropna(subset=["_period", spend_col]).sort_values("_period")
        if trend.empty:
            return finish("The saved monthly table contains no valid month-and-spend values, so I can't establish a trend.")
        trend = trend.groupby("_period", as_index=False)[spend_col].sum().sort_values("_period")
        trend[month_col] = trend["_period"].dt.strftime("%Y-%m")
        trend = trend[[month_col, spend_col]].rename(columns={month_col: "Month", spend_col: "Purchasing spend"})
        first = float(trend.iloc[0]["Purchasing spend"])
        latest = float(trend.iloc[-1]["Purchasing spend"])
        first_month = str(trend.iloc[0]["Month"])
        latest_month = str(trend.iloc[-1]["Month"])
        if len(trend) == 1:
            message = f"The saved analysis contains purchasing spend for {latest_month} only: {_money(currency, latest)}. One month is not enough to establish whether spend increased or decreased over time."
        else:
            change = latest - first
            if first != 0:
                pct = (change / abs(first)) * 100
                direction = "increased" if change > 0 else "decreased" if change < 0 else "remained unchanged"
                message = f"Purchasing spend {direction} by {_money(currency, abs(change))} ({abs(pct):.1f}%) between {first_month} and {latest_month}, from {_money(currency, first)} to {_money(currency, latest)}. This compares the first and latest months in the saved analysis; it does not by itself explain why spend changed."
            else:
                message = f"Purchasing spend changed by {_money(currency, change)} between {first_month} and {latest_month}, from {_money(currency, first)} to {_money(currency, latest)}. The first month's spend is zero, so a percentage change is not meaningful."
        return finish(message, trend)

    # Total financial exposure and spend.
    if _contains(text, [r"how much", r"total.*(?:exposure|overpay|saving|spend|cost)", r"(?:exposure|overpayment).*(?:total|amount)", r"financial impact"]):
        amount = pd.to_numeric(findings.get("identified_exposure", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
        held = pd.to_numeric(findings.get("order_value_held_up", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
        spend = pd.to_numeric(monthly.get("spend", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
        return finish(
            f"The analysis reviewed {_money(currency, spend)} in purchasing spend. "
            f"It identified {_money(currency, amount)} in potential cost exposure and "
            f"{_money(currency, held)} associated with orders awaiting attention. "
            "These figures are different: potential exposure is not confirmed savings or recovered cash."
        )

    # Priorities.
    if _contains(text, [r"high priority", r"urgent", r"most serious", r"critical", r"what should.*first", r"where should.*start"]) and not _contains(text, [r"recommend", r"what should", r"next step", r"action plan", r"fix this"]):
        high = findings[findings.get("severity", pd.Series(index=findings.index, dtype=str)).astype(str).str.casefold().eq("high")]
        if high.empty:
            return finish("There are no findings labelled High priority in this analysis.")
        table = high[[c for c in ["finding_type", "supplier", "po_id", "severity", "identified_exposure"] if c in high.columns]].copy()
        message = f"There are {len(high)} High-priority finding(s). Start by checking the supporting purchase orders and invoices for these items."
        return finish(message, table)

    # Slow approval questions.
    if _contains(text, [r"approv", r"waiting for approval", r"approval delay"]):
        subset = findings[findings.get("finding_type", pd.Series(index=findings.index, dtype=str)).astype(str).eq("Slow approvals")]
        if subset.empty:
            status = detectors.get("Slow approvals")
            if status and str(status).casefold() != "ready":
                return finish(f"Slow-approval detection did not run successfully ({status}). I cannot conclude that approvals were timely.")
            return finish("No slow-approval findings were recorded. This means no approval delay crossed the configured threshold in the available records.")
        rows = []
        for _, row in subset.iterrows():
            ev = _evidence_for(evidence, row.get("finding_id"))
            rows.append(plain.what_we_found(row, ev, currency))
        return finish("Slow-approval findings:\n" + "\n".join(f"• {line}" for line in rows))

    # Late delivery.
    if _contains(text, [r"late deliver", r"delivery delay", r"arriv(?:e|ed) late", r"delayed order"]):
        subset = findings[findings.get("finding_type", pd.Series(index=findings.index, dtype=str)).astype(str).eq("Late delivery")]
        if subset.empty:
            return finish("No late-delivery findings were recorded in this analysis.")
        rows = [plain.what_we_found(row, _evidence_for(evidence, row.get("finding_id")), currency) for _, row in subset.iterrows()]
        return finish(f"I found {len(rows)} late-delivery finding(s):\n" + "\n".join(f"• {line}" for line in rows))

    # Short delivery.
    if _contains(text, [r"short deliver", r"quantity short", r"missing quantit", r"not fully receiv", r"under.?deliver"]):
        subset = findings[findings.get("finding_type", pd.Series(index=findings.index, dtype=str)).astype(str).eq("Short delivery")]
        if subset.empty:
            return finish("No short-delivery findings were recorded in this analysis.")
        rows = [plain.what_we_found(row, _evidence_for(evidence, row.get("finding_id")), currency) for _, row in subset.iterrows()]
        return finish(f"I found {len(rows)} short-delivery finding(s):\n" + "\n".join(f"• {line}" for line in rows))

    # Invoice price / overbilling.
    if _contains(text, [r"invoice", r"overpric", r"overbill", r"charged", r"price discrep"]):
        subset = findings[findings.get("finding_type", pd.Series(index=findings.index, dtype=str)).astype(str).eq("Invoice price above PO price")]
        if subset.empty:
            return finish("No invoice-price-above-order findings were recorded in this analysis.")
        rows = [plain.what_we_found(row, _evidence_for(evidence, row.get("finding_id")), currency) for _, row in subset.iterrows()]
        return finish(f"I found {len(rows)} invoice-price finding(s):\n" + "\n".join(f"• {line}" for line in rows))

    # Supplier performance and actions.
    if matched_supplier:
        subset = findings[findings.get("supplier", pd.Series(index=findings.index, dtype=str)).astype(str).str.casefold().eq(matched_supplier.casefold())]
        if subset.empty:
            return finish(f"No findings are currently associated with {matched_supplier}.")
        table = subset[[c for c in ["finding_type", "po_id", "severity", "identified_exposure"] if c in subset.columns]].copy()
        amount = pd.to_numeric(subset.get("identified_exposure", 0), errors="coerce").fillna(0).sum()
        return finish(
            f"{matched_supplier} has {len(subset)} finding(s), with {_money(currency, amount)} in potential cost exposure to review. "
            "Open each finding to inspect the source records before contacting the supplier.",
            table,
        )

    # General recommendations grounded in the findings actually present.
    if _contains(text, [r"recommend", r"what should", r"next step", r"how can.*(?:improv|reduce|prevent)", r"action plan", r"fix this"]):
        types = set(findings.get("finding_type", pd.Series(dtype=str)).dropna().astype(str))
        actions = []
        for kind in sorted(types):
            if kind in plain.ACTION:
                actions.append(f"• {kind}: {plain.ACTION[kind]}")
        return finish(
            "Recommended investigation steps based on the current findings:\n"
            + "\n".join(actions)
            + "\n\nAssign an owner and record the outcome in Cases and actions. Do not classify an amount as recovered until finance confirms it."
        )

    # Explicit confidence / model reliability questions.
    if _contains(text, [r"model", r"prediction", r"early warning", r"accuracy", r"precision", r"recall", r"reliable"]):
        metrics = log.get("risk_model") or {}
        if not metrics:
            return finish("This saved analysis does not contain model-validation metrics, so I can't make a reliability claim about predictive warnings.")
        return finish(
            f"The saved model evaluation reports precision of {float(metrics.get('precision', 0)):.0%} "
            f"and recall of {float(metrics.get('recall', 0)):.0%}. Precision describes how often its warnings were correct in the evaluation; "
            "recall describes how many known problem cases it caught. These are test results, not a guarantee about future orders."
        )

    examples = (
        "Try asking: Which supplier has the highest potential exposure? "
        "How many invoice discrepancies were found? Which issues are high priority? "
        "Show me the short deliveries. What should we investigate first?"
    )
    return finish(
        "I couldn't match that question to a supported analysis in this workspace. "
        "I can answer questions about supplier exposure, findings, invoice prices, short deliveries, "
        "late deliveries, approval delays, model evaluation and recommended next steps. "
        + examples
    )
