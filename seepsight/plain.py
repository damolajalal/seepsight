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
CHECK_LABELS = {"Short delivery": "Goods invoiced but not received", "Invoice price above PO price": "Invoices above the agreed price",
                "Slow approvals": "Orders waiting too long for approval", "Supplier performance decline": "Suppliers becoming less reliable"}
EVIDENCE_LABELS = {"po_id": "Order number", "supplier": "Supplier", "branch": "Branch", "product": "Product", "po_date": "Order date",
                   "ordered_qty": "Quantity ordered", "received_qty": "Quantity received", "invoice_qty": "Quantity invoiced",
                   "po_unit_price": "Agreed price", "invoice_unit_price": "Invoiced price", "approval_days": "Days waiting for approval",
                   "days_late": "Days late", "po_total": "Order value", "exposure": "Amount to review"}
EVIDENCE_COLUMNS = {"Short delivery": ["po_id", "supplier", "po_date", "invoice_qty", "received_qty", "exposure"],
                    "Invoice price above PO price": ["po_id", "supplier", "po_date", "po_unit_price", "invoice_unit_price", "exposure"],
                    "Slow approvals": ["po_id", "branch", "po_date", "approval_days", "po_total"],
                    "Supplier performance decline": ["po_id", "supplier", "po_date", "days_late", "ordered_qty"]}
DRIVERS = {"lead_days": "the supplier's usual lead time", "prior_late_rate_90d": "recent late deliveries",
           "prior_fill_rate_90d": "recent incomplete deliveries", "prior_deliveries_90d": "recent delivery volume",
           "ordered_qty": "the order quantity", "log_po_total": "the order value", "fin_approval_days": "the finance approval wait",
           "supplier_profile": "the supplier's track record", "branch_profile": "the branch's track record", "branch_id": "the branch",
           "supplier_id": "the supplier's track record"}
WHY = {"Short delivery": "The company may have paid for goods it did not receive.",
       "Invoice price above PO price": "The company may have paid more than it agreed to pay.",
       "Slow approvals": "Slow approvals can hold up deliveries and tie up money.",
       "Supplier performance decline": "Late or incomplete deliveries can disrupt operations and stock levels."}
CAUSE = {"Short delivery": "Receiving records not updated, partial deliveries not recorded, or invoices paid without matching the goods received.",
         "Invoice price above PO price": "Out-of-date price lists, price changes nobody approved, or invoices not checked against the order price.",
         "Slow approvals": "A backlog of approvals, unclear approval limits, or too few people able to approve at that branch.",
         "Supplier performance decline": "Capacity problems at the supplier, changed terms, or transport difficulties."}
ACTION = {"Short delivery": "Compare the delivery records with the invoices for the orders listed, then ask the supplier to explain any difference.",
          "Invoice price above PO price": "Check the invoices against the original orders and any approved price changes before the next payment.",
          "Slow approvals": "Review how approvals are handled at that branch and clear the orders that are waiting.",
          "Supplier performance decline": "Review the supplier's recent deliveries and agree a plan to improve them."}


def title(f):
    t, e = f["finding_type"], f["entity"]
    return {"Short delivery": f"{e} invoiced for goods that may not have arrived",
            "Invoice price above PO price": f"{e} charged more than the agreed prices",
            "Slow approvals": f"{e.replace(' finance approvals', '')}: orders waited too long for approval",
            "Supplier performance decline": f"{e} has become less reliable"}.get(t, f"{t}: {e}")


def what_we_found(f, ev, cur):
    t, n = f["finding_type"], int(f["affected_orders"]) if pd.notna(f["affected_orders"]) else None
    if t == "Short delivery":
        units = int((ev["invoice_qty"] - ev["received_qty"]).clip(lower=0).sum()) if len(ev) else 0
        return (f"In {n} orders, {f['entity']} invoiced for more goods than we recorded as received, about {units:,} units in total. "
                f"The potential extra cost to review is {cur} {f['identified_exposure']:,.0f}.")
    if t == "Invoice price above PO price":
        pct = (ev["invoice_unit_price"] / ev["po_unit_price"] - 1).mean() * 100 if len(ev) else 0
        return (f"In {n} orders, {f['entity']} charged more than the agreed price. On average the invoice price was {pct:.1f}% higher. "
                f"The potential extra cost to review is {cur} {f['identified_exposure']:,.0f}.")
    if t == "Slow approvals":
        d = ev["approval_days"].mean() if len(ev) else 0
        return (f"{n} orders waited on average {d:.1f} days for finance approval. These orders are worth {cur} {f['order_value_held_up']:,.0f}.")
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
