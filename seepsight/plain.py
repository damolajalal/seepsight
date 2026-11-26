"""Everyday-English wording for every finding, column and check."""
import re
import pandas as pd

FIELD_LABELS = {
    "po_id": "Order number", "supplier": "Supplier name", "po_date": "Order date", "ordered_qty": "Quantity ordered",
    "po_unit_price": "Agreed price per unit", "branch": "Branch or site", "department": "Department", "product": "Product or item",
    "promised_date": "Promised delivery date", "received_date": "Date goods were received", "received_qty": "Quantity received",
    "invoice_qty": "Quantity on the invoice", "invoice_unit_price": "Price per unit on the invoice", "invoice_date": "Invoice date",
    "approval_requested_at": "When approval was requested", "approval_completed_at": "When approval was given",
}
REQUIRED = ["po_id", "supplier", "po_date", "ordered_qty", "po_unit_price"]
CHECK_LABELS = {"Short delivery": "Goods not fully received", "Invoice price above PO price": "Invoices above the agreed price",
                "Slow approvals": "Orders waiting too long for approval", "Late delivery": "Confirmed late deliveries",
                "Overdue order awaiting receipt confirmation": "Overdue orders awaiting receipt confirmation",
                "Supplier performance decline": "Suppliers becoming less reliable"}
EVIDENCE_LABELS = {"po_id": "Order number", "supplier": "Supplier", "branch": "Branch", "product": "Product", "po_date": "Order date",
                   "ordered_qty": "Quantity ordered", "received_qty": "Quantity received", "invoice_qty": "Quantity invoiced",
                   "po_unit_price": "Agreed price", "invoice_unit_price": "Invoiced price", "approval_days": "Days waiting for approval",
                   "days_late": "Days late", "promised_date": "Promised date", "received_date": "Received date",
                   "po_total": "Order value", "exposure": "Amount to review"}
EVIDENCE_COLUMNS = {"Short delivery": ["po_id", "supplier", "po_date", "ordered_qty", "invoice_qty", "received_qty", "exposure"],
                    "Invoice price above PO price": ["po_id", "supplier", "po_date", "po_unit_price", "invoice_unit_price", "exposure"],
                    "Slow approvals": ["po_id", "branch", "po_date", "approval_days", "po_total"],
                    "Late delivery": ["po_id", "supplier", "promised_date", "received_date", "days_late"],
                    "Overdue order awaiting receipt confirmation": ["po_id", "supplier", "promised_date", "received_date"],
                    "Supplier performance decline": ["po_id", "supplier", "po_date", "days_late", "ordered_qty"]}
DRIVERS = {"lead_days": "the supplier's usual lead time", "prior_late_rate_90d": "recent late deliveries",
           "prior_fill_rate_90d": "recent incomplete deliveries", "prior_deliveries_90d": "recent delivery volume",
           "ordered_qty": "the order quantity", "log_po_total": "the order value", "fin_approval_days": "the finance approval wait",
           "supplier_profile": "the supplier's track record", "branch_profile": "the branch's track record", "branch_id": "the branch",
           "supplier_id": "the supplier's track record"}
WHY = {"Short delivery": "The company may have ordered or paid for goods that were not fully received.",
       "Invoice price above PO price": "The company may have paid more than it agreed to pay, even when the difference is small.",
       "Slow approvals": "Slow approvals can hold up deliveries and tie up money.",
       "Late delivery": "A confirmed delivery delay can disrupt schedules, production or stock availability.",
       "Overdue order awaiting receipt confirmation": "The promised date has passed, but Seepsight has no receipt date to confirm whether the goods arrived. Verify the goods-received records before calling this a late delivery.",
       "Supplier performance decline": "Late or incomplete deliveries can disrupt operations and stock levels."}
CAUSE = {"Short delivery": "Receiving records not updated, partial deliveries not recorded, or invoices paid without matching the goods received.",
         "Invoice price above PO price": "Out-of-date price lists, price changes nobody approved, or invoices not checked against the order price.",
         "Slow approvals": "A backlog of approvals, unclear approval limits, or too few people able to approve at that branch.",
         "Late delivery": "Supplier capacity, transport delays, dispatch problems or inaccurate promised dates.",
         "Overdue order awaiting receipt confirmation": "The goods-received record may be missing, delayed or stored in a separate file that has not been linked to the purchase order.",
         "Supplier performance decline": "Capacity problems at the supplier, changed terms, or transport difficulties."}
ACTION = {"Short delivery": "Compare ordered, received and invoiced quantities for this order, then resolve any unsupported difference.",
          "Invoice price above PO price": "Check this invoice against the original order and any approved price changes before payment.",
          "Slow approvals": "Review this approval and clear the outstanding step.",
          "Late delivery": "Confirm the agreed delivery date, record the actual receipt date and agree a recovery plan with the supplier.",
          "Overdue order awaiting receipt confirmation": "Check the goods-received note or delivery record and link it to the purchase order. Only classify it as late if the actual receipt date is after the promised date.",
          "Supplier performance decline": "Review the supplier's recent deliveries and agree a plan to improve them."}


def title(f):
    t, e = f["finding_type"], f["entity"]
    return {"Short delivery": f"{e}: goods not fully received",
            "Invoice price above PO price": f"{e}: invoice price exceeds the agreed price",
            "Slow approvals": f"{e}: approvals exceeded the permitted time",
            "Late delivery": f"{e}: confirmed late deliveries",
            "Overdue order awaiting receipt confirmation": f"{e}: overdue orders awaiting receipt confirmation",
            "Supplier performance decline": f"{e} has become less reliable"}.get(t, f"{t}: {e}")


def what_we_found(f, ev, cur):
    t, n = f["finding_type"], int(f["affected_orders"]) if pd.notna(f["affected_orders"]) else None
    supplier_count = int(f.get("supplier_count", 1) or 1)
    supplier_phrase = (
        f"across {supplier_count:,} suppliers"
        if supplier_count > 1 else f"from {f['entity']}"
    )
    if t == "Short delivery":
        units = float((ev["ordered_qty"] - ev["received_qty"]).clip(lower=0).sum()) if len(ev) and {"ordered_qty", "received_qty"}.issubset(ev.columns) else 0
        if len(ev) and "invoice_qty" in ev.columns:
            units = max(units, float((ev["invoice_qty"] - ev["received_qty"]).clip(lower=0).sum()))
        return (f"{n:,} purchase order(s) {supplier_phrase} have a combined quantity shortfall "
                f"of {units:g} unit(s). Estimated value to review: {cur} {float(f['identified_exposure']):,.2f}.")
    if t == "Invoice price above PO price":
        pct = (ev["invoice_unit_price"] / ev["po_unit_price"] - 1).mean() * 100 if len(ev) else 0
        return (f"{n:,} purchase order(s) {supplier_phrase} show invoice prices above the agreed rate "
                f"(average difference {pct:.4f}%). Potential extra cost to review: {cur} {float(f['identified_exposure']):,.2f}.")
    if t == "Slow approvals":
        d = ev["approval_days"].mean() if len(ev) else 0
        return (f"{n:,} purchase order(s) {supplier_phrase} exceeded the finance approval time limit "
                f"(average wait {d:.2f} days). Order value awaiting attention: {cur} {float(f['order_value_held_up']):,.2f}.")
    if t == "Late delivery":
        days = pd.to_numeric(ev["days_late"], errors="coerce").dropna() if len(ev) and "days_late" in ev else pd.Series(dtype=float)
        detail = f" The longest recorded delay is {days.max():g} day(s)." if len(days) else ""
        return (f"{n:,} purchase order(s) {supplier_phrase} have confirmed receipt dates later "
                f"than their promised dates.{detail}")
    if t == "Overdue order awaiting receipt confirmation":
        return (f"{n:,} purchase order(s) {supplier_phrase} are past their promised delivery dates, "
                "but no actual receipt date is recorded. These are unconfirmed overdue orders, "
                "not confirmed late deliveries. Check the goods-received records.")
    m = re.search(r"rose from ([\d.]+) to ([\d.]+) days", str(f["evidence"]))
    if m:
        return f"Deliveries from {f['entity']} are arriving later. The average delay rose from {m.group(1)} to {m.group(2)} days."
    return str(f["evidence"])


def driver_text(s):
    names = re.findall(r"([A-Za-z_][A-Za-z_0-9=]*)", str(s))
    out = [DRIVERS.get(n, n.replace("_", " ")) for n in names]
    return ", ".join(dict.fromkeys(out))


def warning_level(p):
    return "Very high" if p >= 0.95 else "High" if p >= 0.8 else "Raised"
