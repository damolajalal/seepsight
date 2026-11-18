"""
Seepsight - Universal onboarding + detection engine
-------------------------------------------------
Connect ANY company's order data (CSV, Excel or JSON) with its own column names and
formats. The engine:
  1. reads the file safely (encoding, delimiter, Excel sheets, JSON),
  2. matches the company's columns to the Seepsight data contract (names + content checks,
     optionally AI-assisted), and shows you the mapping to confirm or correct,
  3. cleans numbers, dates and names (currency symbols, thousands separators, decimal
     commas, dd/mm vs mm/dd, spacing and capitalisation),
  4. reports data quality and says which detectors can run (and which cannot, and why),
  5. runs the four leak detectors with thresholds you can change.

Nothing is guessed silently: low-confidence matches are listed as "needs your choice",
and detectors whose data is missing are skipped with the reason.
All sample data is SIMULATED.

Quick use (Colab):
    import traceiq_universal as tq
    result = tq.onboard("company_file.xlsx", config={"currency": "KES"})
    result["findings"]      # the findings register
    result["quality"]       # data-quality report
Correct a wrong match:
    result = tq.onboard("file.csv", overrides={"received_date": "Delivered On"})
"""
import io
import json
import os
import re
from difflib import SequenceMatcher
from itertools import permutations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- data contract
# One row per purchase order. Only the first five fields are required to start.
CONTRACT = {
    "po_id": dict(kind="text", required=True, desc="Order / purchase order number",
                  names=["po", "poid", "pono", "ponumber", "poref", "orderno", "ordernumber", "orderid", "orderref",
                         "purchaseorder", "purchaseorderno", "reference", "ref", "order", "docno", "documentno"]),
    "supplier": dict(kind="text", required=True, desc="Supplier / vendor name",
                     names=["supplier", "suppliername", "vendor", "vendorname", "seller", "payee", "creditor",
                            "contractor", "supplierid", "vendorid", "vendorcode", "suppliercode"]),
    "po_date": dict(kind="date", required=True, desc="Date the order was placed",
                    names=["podate", "orderdate", "orderdt", "orderedon", "dateordered", "purchasedate", "dateoforder",
                           "createdon", "createddate", "orderplaced", "placedon", "dateraised"]),
    "ordered_qty": dict(kind="number", required=True, desc="Quantity ordered",
                        names=["qty", "quantity", "qtyordered", "orderedqty", "orderqty", "qtyord", "quantityordered",
                               "orderedquantity", "ordered", "units", "unitsordered"]),
    "po_unit_price": dict(kind="number", required=True, desc="Agreed unit price on the order",
                          names=["unitprice", "pounitprice", "unitcost", "orderprice", "agreedprice", "contractprice",
                                 "price", "costperunit", "rate", "orderedprice", "poprice", "agreedrate"]),
    "branch": dict(kind="text", required=False, desc="Branch / site / location",
                   names=["branch", "site", "location", "plant", "warehouse", "depot", "store", "outlet", "region",
                          "center", "centre", "branchname", "sitename"]),
    "department": dict(kind="text", required=False, desc="Department / cost centre",
                       names=["dept", "department", "costcenter", "costcentre", "division", "unit", "team"]),
    "product": dict(kind="text", required=False, desc="Item / product",
                    names=["product", "item", "itemdescription", "description", "sku", "material", "goods", "itemname",
                           "productname"]),
    "promised_date": dict(kind="date", required=False, desc="Promised / due delivery date",
                          names=["promiseddate", "promiseddelivery", "expecteddelivery", "duedate", "deliverydue",
                                 "requireddate", "needbydate", "scheduleddelivery", "eta", "expecteddate", "promised",
                                 "deliverydate expected", "duedelivery"]),
    "received_date": dict(kind="date", required=False, desc="Date goods were received",
                          names=["receiveddate", "datereceived", "deliverydate", "grndate", "receiptdate",
                                 "actualdelivery", "dateofreceipt", "received", "goodsreceived", "goodsreceivedon",
                                 "receivedon", "deliveredon", "delivered", "dateofdelivery"]),
    "received_qty": dict(kind="number", required=False, desc="Quantity actually received",
                         names=["qtyreceived", "receivedqty", "quantityreceived", "qtyrcvd", "grnqty", "deliveredqty",
                                "qtydelivered", "received", "delivered", "quantitydelivered", "receivedquantity",
                                "qtygrn"]),
    "invoice_qty": dict(kind="number", required=False, desc="Quantity billed on the invoice",
                        names=["invoicedqty", "billedqty", "qtybilled", "invoicequantity", "invoiceqty", "qtyinvoiced",
                               "invoicedquantity", "billedquantity", "quantitybilled", "quantityontheinvoice", "quantityoninvoice"]),
    "invoice_unit_price": dict(kind="number", required=False, desc="Unit price billed on the invoice",
                               names=["invoiceprice", "invoiceunitprice", "billedprice", "billedunitprice",
                                      "invoicedunitprice", "invoicerate", "invoicedprice", "unitpriceinvoiced",
                                      "billedrate", "invoiceunitcost"]),
    "invoice_date": dict(kind="date", required=False, desc="Invoice date",
                         names=["invoicedate", "invdate", "invdt", "billingdate", "billdate", "dateinvoiced",
                                "invoicedon", "dateofinvoice"]),
    "approval_stage": dict(kind="text", required=False, desc="Approval stage / level (separate approvals table only)",
                           names=["stage", "approvalstage", "level", "step", "approvallevel", "approver role", "role"]),
    "approval_requested_at": dict(kind="date", required=False, desc="When final/finance approval was requested",
                                  names=["approvalrequested", "submittedon", "raisedon", "requestedon", "approvalstart",
                                         "submitted", "submissiondate", "approvalsubmitted", "raised", "requestdate",
                                         "approvalrequest", "sentforapproval", "submitteddate", "senton", "sentdate", "sentat",
                                         "requestedat", "submittedat", "raisedat", "datesubmitted", "approvalsent"]),
    "approval_completed_at": dict(kind="date", required=False, desc="When final/finance approval was given",
                                  names=["financesignoff", "financeapproved", "approvedon", "approvalcompleted",
                                         "approvaldate", "signoffdate", "approved", "finalapproval", "financeapproval",
                                         "approveddate", "signedoff", "approvedat", "signoff", "completedon", "completeddate",
                                         "completedat", "completed", "datecompleted", "dateapproved", "closedon", "whenapprovalwasgiven", "approvalgiven"]),
}
REQUIRED = [f for f, s in CONTRACT.items() if s["required"]]
FLAT_FIELDS = [f for f in CONTRACT if f != "approval_stage"]      # fields for a one-row-per-order file
TABLE_FIELDS = {   # fields expected in each file when a company sends separate files
    "orders": ["po_id", "supplier", "po_date", "ordered_qty", "po_unit_price", "branch", "department", "product",
               "promised_date"],
    "receipts": ["po_id", "received_date", "received_qty"],
    "invoices": ["po_id", "invoice_qty", "invoice_unit_price", "invoice_date"],
    "approvals": ["po_id", "approval_stage", "approval_requested_at", "approval_completed_at"],
}

DEFAULT_CONFIG = dict(
    currency="NGN",
    price_tolerance=0.02,        # invoice price must exceed PO price by more than this share
    approval_limit_days=5,       # approvals slower than this are "slow"
    late_days=3,                 # delivery later than this many days counts as late
    min_pattern=5,               # minimum orders before a pattern is reported
    decline_days=2.0,            # supplier delay must worsen by more than this many days
    decline_window=3,            # compare the first and last N months
    min_months=6,                # months of history needed for the decline detector
    accept_score=0.60,           # minimum confidence to accept a column match automatically
)

DETECTORS = {   # fields each detector needs
    "Short delivery": ["supplier", "received_qty", "invoice_qty", "invoice_unit_price"],
    "Invoice price above PO price": ["supplier", "po_unit_price", "invoice_unit_price", "invoice_qty"],
    "Slow approvals": ["approval_requested_at", "approval_completed_at"],
    "Supplier performance decline": ["supplier", "po_date", "promised_date", "received_date"],
}

# ---------------------------------------------------------------- reading files
def read_any(path, sheet=None):
    """Read CSV / Excel / JSON into a table of raw values, whatever the delimiter or encoding."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xlsm", ".xls"):
        with pd.ExcelFile(path) as xl:
            if sheet is None:   # choose the sheet with the most rows
                sheet = max(xl.sheet_names, key=lambda s: len(xl.parse(s, header=None)))
            df = xl.parse(sheet, dtype=object)
    elif ext == ".json":
        with open(path, "rb") as fh:
            data = json.loads(fh.read().decode("utf-8-sig"))
        if isinstance(data, dict):
            data = next((v for v in data.values() if isinstance(v, list)), [data])
        df = pd.json_normalize(data).astype(object)
    else:
        with open(path, "rb") as fh:
            raw = fh.read()
        text = None
        for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        df = pd.read_csv(io.StringIO(text), sep=None, engine="python", dtype=object)
    df = _fix_header(df)
    df.columns = [str(c).strip() for c in df.columns]
    return df.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)


def _fix_header(df):
    """If the sheet has title rows above the real header, find the header row and use it."""
    unnamed = sum(str(c).startswith("Unnamed") for c in df.columns)
    if unnamed < max(2, len(df.columns) // 2):
        return df
    best, best_i = 0, None
    for i in range(min(15, len(df))):
        texty = sum(isinstance(v, str) for v in df.iloc[i])
        if texty >= 0.6 * len(df.columns) and texty > best:
            best, best_i = texty, i
    if best_i is None:
        return df
    out = df.iloc[best_i + 1:].copy()
    out.columns = [str(v).strip() if not _is_blank(v) else f"Unnamed {k}" for k, v in enumerate(df.iloc[best_i])]
    return out.reset_index(drop=True)


# ---------------------------------------------------------------- cleaning values
MISSING = {"", "n/a", "na", "nan", "-", "--", "null", "none", "nil", "#n/a", "tbc", "pending"}


def to_number(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return np.nan
    if isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool):
        return float(v)
    s = str(v).strip()
    if s.lower() in MISSING:
        return np.nan
    neg = s.startswith("(") and s.endswith(")")
    s = re.sub(r"[^\d,.\-]", "", s)         # drop currency symbols, letters and spaces
    if not re.search(r"\d", s):
        return np.nan
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", "") if re.fullmatch(r"-?\d{1,3}(,\d{3})+", s) else s.replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        x = float(s)
    except ValueError:
        return np.nan
    return -x if neg else x


DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d", "%d-%b-%Y", "%d %b %Y",
                "%d-%b-%y", "%b %d, %Y", "%d %B %Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S",
                "%d/%m/%Y %H:%M", "%m/%d/%Y %H:%M", "%d.%m.%Y %H:%M", "%d-%m-%Y %H:%M"]


def to_dates(series):
    """Parse dates in mixed formats. Prefers day-first when a format is ambiguous."""
    out = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    todo = pd.Series(False, index=series.index)
    for idx, v in series.items():
        if v is None or (isinstance(v, float) and np.isnan(v)):
            continue
        if isinstance(v, (pd.Timestamp, np.datetime64)) or hasattr(v, "year"):
            out.at[idx] = pd.Timestamp(v)
        elif isinstance(v, (int, float, np.integer, np.floating)) and 20000 < float(v) < 80000:
            out.at[idx] = pd.Timestamp("1899-12-30") + pd.Timedelta(days=float(v))   # Excel serial date
        else:
            s = str(v).strip()
            if s.lower() not in MISSING:
                todo.at[idx] = True
    if todo.any():
        strs = series[todo].astype(str).str.strip()
        rates = []
        for fmt in ["ISO8601"] + DATE_FORMATS:       # ISO8601 covers 2025-10-02T13:21:45.123456 and similar
            try:
                parsed = pd.to_datetime(strs, format=fmt, errors="coerce")
            except (ValueError, TypeError):
                continue
            rates.append((parsed.notna().mean(), -(["ISO8601"] + DATE_FORMATS).index(fmt), fmt, parsed))
        remaining = strs.index
        for rate, _, fmt, parsed in sorted(rates, key=lambda t: (t[0], t[1]), reverse=True):
            if rate == 0:
                break
            fill = parsed.reindex(remaining).dropna()
            if len(fill):
                out.loc[fill.index] = fill
                remaining = remaining.difference(fill.index)
            if len(remaining) == 0:
                break
    return out


def _is_blank(v):
    return v is None or v is pd.NA or (isinstance(v, float) and v != v)


def clean_text(series):
    def tidy(v):
        if _is_blank(v):
            return None
        t = " ".join(str(v).split())
        return None if t.lower() in MISSING else t
    return series.astype("object").map(tidy)


def canonical_names(series):
    """Treat 'ACME LTD ', 'Acme Ltd' and 'acme ltd' as one name (use the most common spelling)."""
    key = series.map(lambda v: None if _is_blank(v) else v.casefold())
    best = {}
    for k, grp in series.groupby(key):
        best[k] = grp.value_counts().idxmax()
    return key.map(lambda k: None if _is_blank(k) else best.get(k))


# ---------------------------------------------------------------- column matching
CURRENCY_WORDS = {"kes", "ngn", "usd", "eur", "gbp", "zar", "ghs", "tzs", "ugx", "inr", "naira", "shillings", "cedis"}


def _tokens(name):
    s = re.sub(r"[^a-z0-9]+", " ", str(name).lower())
    return [t for t in s.split() if t not in CURRENCY_WORDS]


def name_score(col, spec):
    toks = _tokens(col)
    n = "".join(toks)
    if not n:
        return 0.0
    best = 0.0
    reordered = {"".join(p) for p in permutations(toks)} if len(toks) <= 3 else set()
    for syn in spec["names"]:
        syn = syn.replace(" ", "")
        if n == syn:
            return 1.0
        if syn in reordered:
            best = max(best, 0.95)
        if syn in toks:
            best = max(best, 0.85)
        if len(syn) >= 5 and syn in n:
            best = max(best, 0.8 * len(syn) / len(n) + 0.15)
        elif len(n) >= 5 and n in syn:
            best = max(best, 0.7 * len(n) / len(syn) + 0.1)
        r = SequenceMatcher(None, n, syn).ratio()
        if r >= 0.8:
            best = max(best, 0.9 * r)
    return min(best, 0.95)


def content_fit(series, kind):
    """Share of non-empty values that look like the expected type (0 to 1)."""
    vals = series.dropna()
    vals = vals[~vals.astype(str).str.strip().str.lower().isin(MISSING)]
    if len(vals) == 0:
        return 0.0
    sample = vals.head(300)
    if kind == "number":
        return float(sample.map(to_number).notna().mean())
    if kind == "date":
        return float(to_dates(sample.reset_index(drop=True)).notna().mean())
    pure = sample.astype(str).str.fullmatch(r"[\s\d.,\-+()%]*\d[\s\d.,\-+()%]*").mean()
    return 0.4 if pure > 0.9 else 1.0     # names are rarely pure numbers (order ids may be)


def suggest_mapping(df, accept_score=0.60, fields=None):
    """Match columns to contract fields. Returns (mapping, unmapped_columns, needs_choice)."""
    fields = fields or FLAT_FIELDS
    cands = []
    for field in fields:
        spec = CONTRACT[field]
        for col in df.columns:
            ns = name_score(col, spec)
            if ns <= 0:
                continue
            fit = content_fit(df[col], spec["kind"])
            if spec["kind"] in ("number", "date") and fit < 0.7:
                score = ns * 0.3
            else:
                score = ns * (0.6 + 0.4 * fit)
            if field == "po_id" and spec["kind"] == "text":
                score = ns * 0.95 if fit > 0 else 0      # ids may be all digits
            if field == "approval_stage":
                score = ns * 0.9 if fit > 0.5 else 0
            cands.append((score, field, col, ns, fit))
    mapping, used_cols = {}, set()
    for score, field, col, ns, fit in sorted(cands, key=lambda t: -t[0]):
        if field in mapping or col in used_cols or score < accept_score:
            continue
        mapping[field] = dict(column=col, confidence=round(score, 2), source="name+content")
        used_cols.add(col)
    unmapped = [c for c in df.columns if c not in used_cols]
    needs_choice = [f for f in fields if f not in mapping]
    return mapping, unmapped, needs_choice


def nim_suggest_mapping(client, model, df, fields):
    """Optional: ask an LLM to propose matches for fields the rules could not match.
    Suggestions are only kept if the column exists and its content fits the field type."""
    samples = df.head(3).to_dict(orient="records")
    prompt = (
        "Map spreadsheet columns to these fields. Reply with JSON only: {field: column name or null}.\n"
        "Fields: " + json.dumps({f: CONTRACT[f]["desc"] for f in fields}) + "\n"
        "Columns: " + json.dumps(list(df.columns)) + "\nSample rows: " + json.dumps(samples, default=str)[:2500])
    try:
        resp = client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": prompt}], temperature=0, max_tokens=900)
        text = re.sub(r"<think>.*?</think>", "", resp.choices[0].message.content or "", flags=re.S)
        data = json.loads(text[text.find("{"): text.rfind("}") + 1])
    except Exception:
        return {}
    out = {}
    for field, col in data.items():
        min_fit = 0.4 if field == "po_id" else 0.7      # order numbers can be all digits
        if field in fields and col in df.columns and content_fit(df[col], CONTRACT[field]["kind"]) >= min_fit:
            out[field] = col
    return out


# ---------------------------------------------------------------- build the ledger
def apply_mapping(df, mapping):
    out = pd.DataFrame(index=df.index)
    for field, info in mapping.items():
        kind, s = CONTRACT[field]["kind"], df[info["column"]]
        if kind == "number":
            out[field] = s.map(to_number)
        elif kind == "date":
            out[field] = to_dates(s)
        else:
            t = clean_text(s)
            out[field] = canonical_names(t) if field in ("supplier", "branch", "product", "department") else t
    return out


def finalize_ledger(led):
    """Derive the measures the detectors use. Works on any table that already has contract field names."""
    led = led.copy()
    led["po_total"] = led["ordered_qty"] * led["po_unit_price"]
    led["po_month"] = led["po_date"].dt.to_period("M").astype(str)
    if {"received_date", "promised_date"} <= set(led.columns):
        led["days_late"] = (led["received_date"] - led["promised_date"]).dt.days
    if {"received_qty", "invoice_qty"} <= set(led.columns):
        led["short_units"] = (led["invoice_qty"] - led["received_qty"]).clip(lower=0)
    if {"invoice_unit_price", "po_unit_price"} <= set(led.columns):
        led["price_gap_pct"] = (led["invoice_unit_price"] - led["po_unit_price"]) / led["po_unit_price"]
    if {"approval_requested_at", "approval_completed_at"} <= set(led.columns):
        led["approval_days"] = (led["approval_completed_at"] - led["approval_requested_at"]).dt.total_seconds() / 86400
    return led


# ---------------------------------------------------------------- data quality
def quality_report(raw_rows, ledger, mapping, dropped, config):
    q = {"rows_in_file": raw_rows, "rows_used": len(ledger), "dropped": dropped, "fields": {}, "warnings": []}
    for f in CONTRACT:
        if f in ledger.columns:
            q["fields"][f] = round(float(ledger[f].notna().mean()), 3)
    for f in REQUIRED:
        if f not in ledger.columns:
            q["warnings"].append(f"Required field '{f}' is not mapped.")
        elif ledger[f].notna().mean() < 0.9:
            q["warnings"].append(f"Required field '{f}' is empty in {1 - ledger[f].notna().mean():.0%} of rows.")
    if {"po_date", "received_date"} <= set(ledger.columns):
        bad = int((ledger["received_date"] < ledger["po_date"]).sum())
        if bad:
            q["warnings"].append(f"{bad} orders show goods received BEFORE the order date.")
    for f in ("ordered_qty", "po_unit_price", "received_qty", "invoice_qty", "invoice_unit_price"):
        if f in ledger.columns and (ledger[f] < 0).any():
            q["warnings"].append(f"{int((ledger[f] < 0).sum())} negative values in '{f}'.")
    for f, info in mapping.items():
        if f in ledger.columns and info.get("column") is not None:
            pass
    q["detectors"] = {}
    for name, need in DETECTORS.items():
        missing = [f for f in need if f not in ledger.columns or ledger[f].notna().mean() < 0.3]
        q["detectors"][name] = "ready" if not missing else "skipped - needs: " + ", ".join(missing)
    return q


# ---------------------------------------------------------------- detectors
def _severity_by_share(amount, spend, high=0.003, medium=0.0005):
    share = amount / spend if spend else 0
    return "High" if share >= high else "Medium" if share >= medium else "Low"


def detect(led, config=None):
    """Run every detector whose data is available. Returns the findings register."""
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    spend = float(led["po_total"].sum())
    rows = []

    def ok(name):
        return all(f in led.columns and led[f].notna().mean() >= 0.3 for f in DETECTORS[name])

    if ok("Short delivery"):
        d = led[(led["invoice_qty"] > led["received_qty"]) & led["received_qty"].notna()].copy()
        d["leak"] = (d["invoice_qty"] - d["received_qty"]) * d["invoice_unit_price"]
        for sup, g in d.groupby("supplier"):
            if len(g) >= cfg["min_pattern"]:
                rows.append(dict(finding_type="Short delivery", entity=sup, affected_orders=len(g),
                                 leakage=round(g["leak"].sum()), orders_held=0.0,
                                 first_seen=g["invoice_date"].min() if "invoice_date" in g else g["po_date"].min(),
                                 last_seen=g["invoice_date"].max() if "invoice_date" in g else g["po_date"].max(),
                                 evidence=f"Invoiced for {int((g['invoice_qty'] - g['received_qty']).sum())} units that were never received",
                                 severity=_severity_by_share(g["leak"].sum(), spend)))
    if ok("Invoice price above PO price"):
        d = led[led["price_gap_pct"] > cfg["price_tolerance"]].copy()
        d["leak"] = (d["invoice_unit_price"] - d["po_unit_price"]) * d["invoice_qty"]
        for sup, g in d.groupby("supplier"):
            if len(g) >= cfg["min_pattern"]:
                rows.append(dict(finding_type="Invoice price above PO price", entity=sup, affected_orders=len(g),
                                 leakage=round(g["leak"].sum()), orders_held=0.0,
                                 first_seen=g["invoice_date"].min() if "invoice_date" in g else g["po_date"].min(),
                                 last_seen=g["invoice_date"].max() if "invoice_date" in g else g["po_date"].max(),
                                 evidence=f"Invoice prices averaged {g['price_gap_pct'].mean() * 100:.1f}% above agreed PO prices",
                                 severity=_severity_by_share(g["leak"].sum(), spend)))
    if ok("Slow approvals"):
        d = led[led["approval_days"] > cfg["approval_limit_days"]]
        group_col = "branch" if "branch" in led.columns else None
        groups = d.groupby(group_col) if group_col else [("company-wide", d)]
        for name, g in groups:
            if len(g) >= cfg["min_pattern"]:
                label = f"{name} branch finance approvals" if group_col else "Company-wide finance approvals"
                rows.append(dict(finding_type="Slow approvals", entity=label, affected_orders=len(g),
                                 leakage=0.0, orders_held=round(g["po_total"].sum()),
                                 first_seen=g["po_date"].min(), last_seen=g["po_date"].max(),
                                 evidence=f"Held orders waited {g['approval_days'].mean():.1f} days on average for finance approval",
                                 severity=_severity_by_share(g["po_total"].sum(), spend, high=0.05, medium=0.01)))
    if ok("Supplier performance decline"):
        has_fill = {"received_qty", "ordered_qty"} <= set(led.columns)
        for sup, g in led.dropna(subset=["days_late"]).groupby("supplier"):
            m = g.groupby("po_month").agg(delay=("days_late", "mean"),
                                          rec=("received_qty", "sum") if has_fill else ("days_late", "size"),
                                          ordq=("ordered_qty", "sum"))
            if len(m) < max(cfg["min_months"], 2 * cfg["decline_window"]):
                continue
            w = cfg["decline_window"]
            early, recent = m["delay"].iloc[:w].mean(), m["delay"].iloc[-w:].mean()
            if recent - early > cfg["decline_days"]:
                ev = f"Average delivery delay rose from {early:.1f} to {recent:.1f} days"
                if has_fill:
                    fe = m["rec"].iloc[:w].sum() / m["ordq"].iloc[:w].sum()
                    fr = m["rec"].iloc[-w:].sum() / m["ordq"].iloc[-w:].sum()
                    ev += f"; fill rate went from {fe:.3f} to {fr:.3f}"
                rows.append(dict(finding_type="Supplier performance decline", entity=sup, affected_orders=None,
                                 leakage=0.0, orders_held=0.0, first_seen=None, last_seen=None, evidence=ev,
                                 severity="High" if recent - early >= 5 else "Medium"))
    cols = ["finding_id", "finding_type", "entity", "severity", "affected_orders", "leakage", "orders_held",
            "first_seen", "last_seen", "evidence"]
    if not rows:
        return pd.DataFrame(columns=cols)
    f = pd.DataFrame(rows).sort_values(["leakage", "orders_held"], ascending=False).reset_index(drop=True)
    f.insert(0, "finding_id", [f"TRQ-{i + 1:03d}" for i in range(len(f))])
    return f[cols]


def to_trace(findings, config=None):
    """Convert findings to the decision_trace layout used by the NIM explanation script."""
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    method = {
        "Short delivery": "Rule: invoiced quantity exceeds received quantity; reported when "
                          f"{cfg['min_pattern']} or more orders show the pattern",
        "Invoice price above PO price": f"Rule: invoice unit price more than {cfg['price_tolerance']:.0%} above PO price; "
                                        f"reported when {cfg['min_pattern']} or more orders show the pattern",
        "Slow approvals": f"Rule: finance approval took more than {cfg['approval_limit_days']} days; reported when "
                          f"{cfg['min_pattern']} or more orders show the pattern",
        "Supplier performance decline": f"Rule: average delivery delay rose by more than {cfg['decline_days']:g} days "
                                        f"between the first and last {cfg['decline_window']} months",
    }
    t = pd.DataFrame({
        "trace_id": [f"TR-{i + 1:05d}" for i in range(len(findings))],
        "source": "RULE_ENGINE", "record_ref": findings["finding_id"], "entity": findings["entity"],
        "decision": findings["finding_type"], "method": findings["finding_type"].map(method),
        "evidence": findings["evidence"], "severity": findings["severity"], "risk_score": np.nan,
        "key_drivers": None,
        "amount": np.where(findings["leakage"] > 0, findings["leakage"],
                               np.where(findings["orders_held"] > 0, findings["orders_held"], np.nan)),
        "amount_basis": np.where(findings["leakage"] > 0, "leakage",
                                 np.where(findings["orders_held"] > 0, "orders held", None)),
        "later_outcome": pd.NA, "affected_orders": findings["affected_orders"], "currency": cfg["currency"]})
    return t


# ---------------------------------------------------------------- per-company risk model (ML)
def _prior_history(led, cfg, window_days=90):
    """For each order: how this supplier's EARLIER deliveries went (only orders that arrived before this one
    was placed, so the model never sees the future)."""
    n = len(led)
    po = led["po_date"].values.astype("datetime64[D]")
    rec = led["received_date"].values.astype("datetime64[D]") if "received_date" in led else np.full(n, np.datetime64("NaT"))
    late = (led["days_late"].values > cfg["late_days"]) if "days_late" in led else np.full(n, np.nan)
    fill = (led["received_qty"] / led["ordered_qty"]).values if "received_qty" in led else np.full(n, np.nan)
    pl, pf, pn = np.full(n, np.nan), np.full(n, np.nan), np.zeros(n)
    sup = led["supplier"].values
    for s_name in pd.unique(sup):
        pos = np.where(sup == s_name)[0]
        for i in pos:
            m = ~np.isnat(rec[pos]) & (rec[pos] < po[i]) & (rec[pos] >= po[i] - np.timedelta64(window_days, "D"))
            sel = pos[m]
            pn[i] = len(sel)
            if len(sel):
                with np.errstate(all="ignore"):
                    pl[i] = np.nanmean(late[sel].astype(float)) if not np.all(np.isnan(late[sel].astype(float))) else np.nan
                    pf[i] = np.nanmean(fill[sel]) if not np.all(np.isnan(fill[sel])) else np.nan
    return pl, pf, pn


def risk_model(led, config=None, top_n=8):
    """Train a simple, explainable model on this company's own history to predict which orders will arrive
    late or short, test it on the most recent orders, and explain each high-risk order."""
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    out = dict(metrics=None, scored=pd.DataFrame(), skipped=None)
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        out["skipped"] = "scikit-learn is not installed (pip install scikit-learn)"
        return out
    led = led.sort_values("po_date").reset_index(drop=True)
    parts = []
    if "days_late" in led:
        parts.append(led["days_late"] > cfg["late_days"])
    if {"received_qty", "ordered_qty"} <= set(led.columns):
        parts.append(led["received_qty"] < 0.95 * led["ordered_qty"])
    known = (led["received_date"].notna() if "received_date" in led else False) | \
            (led["received_qty"].notna() if "received_qty" in led else False)
    if not parts or not np.any(known):
        out["skipped"] = "needs delivery results (received date with promised date, or received quantity)"
        return out
    label = parts[0].fillna(False) if len(parts) == 1 else (parts[0].fillna(False) | parts[1].fillna(False))
    led["label"] = np.where(known, label.astype(int), np.nan)
    pl, pf, pn = _prior_history(led, cfg)
    X = pd.DataFrame({"ordered_qty": led["ordered_qty"], "log_po_total": np.log1p(led["po_total"]),
                      "prior_deliveries_90d": pn})
    if "days_late" in led:
        X["prior_late_rate_90d"] = pl
    if "received_qty" in led:
        X["prior_fill_rate_90d"] = pf
    if "approval_days" in led and led["approval_days"].notna().mean() > 0.3:
        X["fin_approval_days"] = led["approval_days"]
    for cat, name in (("supplier", "supplier"), ("branch", "branch")):
        if cat in led and 1 < led[cat].nunique() <= 40:
            X = X.join(pd.get_dummies(led[cat], prefix=name, prefix_sep="=").astype(float))
    lab = led["label"]
    cutoff = led["po_date"].quantile(0.75)
    train = lab.notna() & (led["po_date"] < cutoff)
    test = lab.notna() & (led["po_date"] >= cutoff)
    if lab.notna().sum() < 300 or lab[train].sum() < 25 or lab[test].sum() < 5 or lab[train].nunique() < 2:
        out["skipped"] = (f"not enough history ({int(lab.notna().sum())} orders with results, "
                          f"{int(lab[train].sum())} problem orders in training); needs about 300 orders and 25 problems")
        return out
    med = X[train].median()
    X = X.fillna(med).fillna(0)
    sc = StandardScaler().fit(X[train])
    Xs = pd.DataFrame(sc.transform(X), columns=X.columns, index=X.index)
    model = LogisticRegression(class_weight="balanced", max_iter=2000).fit(Xs[train], lab[train].astype(int))
    prob = model.predict_proba(Xs[test])[:, 1]
    y = lab[test].astype(int).values
    pred = (prob >= 0.5).astype(int)
    metrics = dict(
        trained_on=int(train.sum()), tested_on=int(test.sum()), test_from=str(cutoff.date()),
        problem_rate_test=round(float(y.mean()), 3), precision=round(float(precision_score(y, pred, zero_division=0)), 3),
        recall=round(float(recall_score(y, pred, zero_division=0)), 3), accuracy=round(float(accuracy_score(y, pred)), 3),
        auc=round(float(roc_auc_score(y, prob)), 3) if len(set(y)) > 1 else None)
    contrib = Xs[test] * model.coef_[0]
    groups = {}
    for c in contrib.columns:
        key = "supplier_profile" if c.startswith("supplier=") else "branch_profile" if c.startswith("branch=") else c
        groups.setdefault(key, []).append(c)
    gc = pd.DataFrame({k: contrib[v].sum(axis=1) for k, v in groups.items()})
    drivers = gc.apply(lambda r: ", ".join(f"{k} ({v:.2f})" for k, v in r.nlargest(3).items() if v > 0), axis=1)
    scored = led.loc[test, [c for c in ("po_id", "supplier", "branch", "po_date", "ordered_qty") if c in led]].copy()
    scored["risk_score"], scored["key_drivers"], scored["actual_problem"] = prob, drivers.values, y
    out.update(metrics=metrics, scored=scored.sort_values("risk_score", ascending=False).reset_index(drop=True))
    flagged = out["scored"][out["scored"]["risk_score"] >= 0.5]
    # show a spread of suppliers (best 2 per supplier), not just the single worst one
    out["top"] = flagged.groupby("supplier").head(2).sort_values("risk_score", ascending=False).head(top_n)
    return out


def ml_trace(top, cutoff_text, start=1, metrics=None):
    rows = []
    metrics = metrics or {}
    for i, r in enumerate(top.itertuples(), start=start):
        branch = f", {r.branch} branch" if hasattr(r, "branch") and isinstance(r.branch, str) else ""
        rows.append(dict(trace_id=f"TR-{i:05d}", source="ML_MODEL", record_ref=r.po_id, entity=r.supplier,
                         decision="Predicted late or short delivery",
                         method=f"ML: logistic regression trained on this company's orders before {cutoff_text}",
                         evidence=f"Order of {r.ordered_qty:g} units{branch}, placed {r.po_date.date()}",
                         severity="High" if r.risk_score >= 0.8 else "Medium", risk_score=float(r.risk_score),
                         key_drivers=r.key_drivers, amount=np.nan, amount_basis=None, later_outcome=int(r.actual_problem),
                         affected_orders=np.nan, model_precision=metrics.get("precision"),
                         model_recall=metrics.get("recall")))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- the pipelines
def _map_table(raw, fields, cfg, overrides=None, label=""):
    mapping, unmapped, needs = suggest_mapping(raw, cfg["accept_score"], fields)
    for field, col in (overrides or {}).items():            # your corrections always win
        if col is None:
            mapping.pop(field, None)
        elif col in raw.columns:
            mapping = {f: i for f, i in mapping.items() if i["column"] != col or f == field}
            mapping[field] = dict(column=col, confidence=1.0, source="you")
        else:
            print(f"  note: column '{col}' (for {label}{field}) is not in the file; ignored")
    return mapping


def _ai_fill(raw, mapping, fields, client, model):
    gaps = [f for f in fields if f not in mapping]
    free = raw[[c for c in raw.columns if c not in {i["column"] for i in mapping.values()}]]
    if gaps and len(free.columns) and client is not None and model:
        for field, col in nim_suggest_mapping(client, model, free, gaps).items():
            mapping[field] = dict(column=col, confidence=0.7, source="AI suggestion - please confirm")
    return mapping


def _analyze(typed, shown_mapping, unmapped, needs, raw_rows, dropped, cfg, verbose, with_ml, extra_warnings=()):
    missing_required = [f for f in REQUIRED if f not in typed.columns]
    if missing_required:
        report = quality_report(raw_rows, typed, shown_mapping, dropped, cfg)
        report["warnings"] = list(extra_warnings) + report["warnings"]
        if verbose:
            print_summary(shown_mapping, unmapped, needs, report, None)
        return dict(mapping=shown_mapping, unmapped=unmapped, needs_choice=needs, quality=report, ledger=typed,
                    findings=pd.DataFrame(), trace_all=pd.DataFrame(), risk=None,
                    stopped=f"Required fields not mapped: {missing_required}")
    typed = typed.dropna(subset=["po_date", "ordered_qty", "po_unit_price"]).reset_index(drop=True)
    led = finalize_ledger(typed)
    report = quality_report(raw_rows, led, shown_mapping, dropped, cfg)
    report["warnings"] = list(extra_warnings) + report["warnings"]
    findings = detect(led, cfg)
    trace = to_trace(findings, cfg) if len(findings) else pd.DataFrame()
    risk = None
    if with_ml:
        risk = risk_model(led, cfg)
        if risk["metrics"] and len(risk.get("top", [])):
            mt = ml_trace(risk["top"], risk["metrics"]["test_from"], start=len(trace) + 1, metrics=risk["metrics"])
            mt["currency"] = cfg["currency"]
            trace = pd.concat([trace, mt], ignore_index=True)
    result = dict(mapping=shown_mapping, unmapped=unmapped, needs_choice=needs, quality=report, ledger=led,
                  findings=findings, trace_all=trace, risk=risk, config=cfg)
    if verbose:
        print_summary(shown_mapping, unmapped, needs, report, findings, cfg, risk)
    return result


def onboard(path=None, df=None, sheet=None, overrides=None, config=None, client=None, model=None,
            verbose=True, with_ml=True):
    """ONE file with one row per order. Read -> match columns -> clean -> quality -> detect -> ML risk."""
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    raw = df if df is not None else read_any(path, sheet)
    mapping = _map_table(raw, FLAT_FIELDS, cfg, overrides)
    mapping = _ai_fill(raw, mapping, FLAT_FIELDS, client, model)
    unmapped = [c for c in raw.columns if c not in {i["column"] for i in mapping.values()}]
    needs = [f for f in FLAT_FIELDS if f not in mapping]
    typed = apply_mapping(raw, mapping)
    dropped = {}
    if "po_id" in typed.columns:
        n0 = len(typed)
        typed = typed[typed["po_id"].notna()]
        dropped["rows_without_order_number"] = n0 - len(typed)
        n1 = len(typed)
        typed = typed.drop_duplicates(subset="po_id", keep="first")
        dropped["duplicate_orders_removed"] = n1 - len(typed)
    return _analyze(typed, mapping, unmapped, needs, len(raw), dropped, cfg, verbose, with_ml)


def _id_key(series):
    """Join key for order numbers: ignores case, spaces, dashes and leading zeros ('PO-0012' = 'po0012')."""
    def k(v):
        if _is_blank(v):
            return None
        t = re.sub(r"[^A-Za-z0-9]", "", str(v)).upper()
        return t.lstrip("0") if t.isdigit() else t
    return series.map(k)


def onboard_tables(files, sheets=None, overrides=None, config=None, client=None, model=None, verbose=True, with_ml=True):
    """SEVERAL files (orders, receipts, invoices, approvals). files = {"orders": path, ...}; only "orders" is
    required. Receipts, invoices and approvals are matched to orders by order number and summarised per order."""
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    if "orders" not in files:
        raise ValueError("files must include an 'orders' file, e.g. {'orders': 'orders.csv', 'receipts': 'grn.csv'}")
    shown, unmapped_all, warnings, dropped = {}, [], [], {}
    typed_tables = {}
    for name in ("orders", "receipts", "invoices", "approvals"):
        if name not in files:
            continue
        raw = files[name] if isinstance(files[name], pd.DataFrame) else read_any(files[name], (sheets or {}).get(name))
        fields = TABLE_FIELDS[name]
        mp = _map_table(raw, fields, cfg, (overrides or {}).get(name), label=f"{name}.")
        mp = _ai_fill(raw, mp, fields, client, model)
        for f, i in mp.items():
            shown[f if name == "orders" else f"{name}.{f}"] = i
        unmapped_all += [f"{name}: {c}" for c in raw.columns if c not in {i['column'] for i in mp.values()}]
        t = apply_mapping(raw, mp)
        if "po_id" not in t.columns:
            warnings.append(f"The {name} file has no order-number column matched; it cannot be joined (use overrides).")
            continue
        t["_key"] = _id_key(t["po_id"])
        t = t[t["_key"].notna()]
        typed_tables[name] = t
        if name == "orders":
            raw_rows = len(raw)
    if "orders" not in typed_tables:
        return dict(mapping=shown, unmapped=unmapped_all, needs_choice=["po_id"], quality=dict(
            rows_in_file=0, rows_used=0, dropped={}, fields={}, detectors={}, warnings=warnings),
            ledger=pd.DataFrame(), findings=pd.DataFrame(), trace_all=pd.DataFrame(), risk=None,
            stopped="The orders file has no matched order-number column")
    o = typed_tables["orders"]
    n0 = len(o)
    o = o.drop_duplicates(subset="_key", keep="first")
    dropped["duplicate_orders_removed"] = n0 - len(o)
    order_keys = set(o["_key"])
    if "receipts" in typed_tables and {"received_date", "received_qty"} & set(typed_tables["receipts"].columns):
        r = typed_tables["receipts"]
        agg = {}
        if "received_date" in r:
            agg["received_date"] = ("received_date", "min")
        if "received_qty" in r:
            agg["received_qty"] = ("received_qty", "sum")
        o = o.merge(r.groupby("_key").agg(**agg).reset_index(), on="_key", how="left")
    if "invoices" in typed_tables:
        v = typed_tables["invoices"].copy()
        agg = {}
        if "invoice_qty" in v:
            agg["invoice_qty"] = ("invoice_qty", "sum")
        if "invoice_date" in v:
            agg["invoice_date"] = ("invoice_date", "min")
        if {"invoice_qty", "invoice_unit_price"} <= set(v.columns):
            v["_val"] = v["invoice_qty"] * v["invoice_unit_price"]
            agg["_val"] = ("_val", "sum")
        elif "invoice_unit_price" in v:
            agg["invoice_unit_price"] = ("invoice_unit_price", "mean")
        g = v.groupby("_key").agg(**agg).reset_index()
        if "_val" in g:
            g["invoice_unit_price"] = g["_val"] / g["invoice_qty"].where(g["invoice_qty"] > 0)
            g = g.drop(columns="_val")
        o = o.merge(g, on="_key", how="left")
    if "approvals" in typed_tables and {"approval_requested_at", "approval_completed_at"} <= set(typed_tables["approvals"].columns):
        a = typed_tables["approvals"].copy()
        if "approval_stage" in a and a["approval_stage"].astype(str).str.contains("financ", case=False, na=False).any():
            a = a[a["approval_stage"].astype(str).str.contains("financ", case=False, na=False)]
        a = a.sort_values("approval_completed_at").groupby("_key").tail(1)
        o = o.merge(a[["_key", "approval_requested_at", "approval_completed_at"]], on="_key", how="left")
    for name, t in typed_tables.items():       # do the order numbers actually line up?
        if name != "orders":
            keys = set(t["_key"])
            share = len(keys & order_keys) / max(len(keys), 1)
            if share < 0.8:
                warnings.append(f"Only {share:.0%} of order numbers in the {name} file were found in the orders file. "
                                f"Check that the order-number format matches.")
    o = o.drop(columns=["_key"])
    o = o[o["po_id"].notna()]
    needs = [f for f in TABLE_FIELDS["orders"] if f not in shown]
    return _analyze(o, shown, unmapped_all, needs, raw_rows, dropped, cfg, verbose, with_ml, warnings)


def save_outputs(result, folder="traceiq_output"):
    """Write everything to CSV/JSON so it can be uploaded to BigQuery or shared."""
    os.makedirs(folder, exist_ok=True)
    paths = []
    for name in ("ledger", "findings", "trace_all"):
        df = result.get(name)
        if df is not None and len(df):
            path = os.path.join(folder, f"{name}.csv")
            df.to_csv(path, index=False)
            paths.append(path)
    meta = dict(mapping={k: v["column"] for k, v in result["mapping"].items()}, quality=result["quality"],
                ml=(result.get("risk") or {}).get("metrics"))
    path = os.path.join(folder, "run_summary.json")
    with open(path, "w") as fh:
        json.dump(meta, fh, indent=2, default=str)
    return paths + [path]


def print_summary(mapping, unmapped, needs, report, findings, cfg=None, risk=None):
    print("\nCOLUMN MATCHES (confirm these):")
    for f, i in mapping.items():
        flag = "" if i["confidence"] >= 0.8 else "   <-- check"
        print(f"  {f:28s} <- {i['column']!r:30s} confidence {i['confidence']:.2f} ({i['source']}){flag}")
    still = [f for f in needs if f in CONTRACT and CONTRACT[f]["required"]]
    if still:
        print("\nREQUIRED FIELDS STILL NEEDING YOUR CHOICE:", ", ".join(still))
    if unmapped:
        print("Columns not used:", ", ".join(map(str, unmapped)))
    print(f"\nDATA QUALITY: {report['rows_used']} of {report['rows_in_file']} rows used; {report['dropped']}")
    for w in report["warnings"]:
        print("  warning:", w)
    print("DETECTORS:")
    for k, v in report["detectors"].items():
        print(f"  {k:32s} {v}")
    if findings is not None:
        cur = (cfg or {}).get("currency", "")
        print(f"\nFINDINGS ({len(findings)}):")
        for _, r in findings.iterrows():
            amt = f"{cur} {r['leakage']:,.0f} leakage" if r["leakage"] else (
                f"{cur} {r['orders_held']:,.0f} orders held" if r["orders_held"] else "")
            n = "" if pd.isna(r["affected_orders"]) else f"{int(r['affected_orders'])} orders, "
            print(f"  {r['finding_id']} [{r['severity']}] {r['finding_type']}: {r['entity']} - {n}{amt}")
            print(f"           {r['evidence']}")
    if risk is not None:
        print("\nRISK MODEL (predicts late or short deliveries; trained on this company's own history):")
        if risk["metrics"]:
            m = risk["metrics"]
            print(f"  trained on {m['trained_on']} orders, tested on {m['tested_on']} orders from {m['test_from']} onward "
                  f"({m['problem_rate_test']:.0%} were problems)")
            print(f"  precision {m['precision']}, recall {m['recall']}, accuracy {m['accuracy']}, AUC {m['auc']}")
        else:
            print("  skipped:", risk["skipped"])


# ---------------------------------------------------------------- dashboard data pack
ENGINE_VERSION = "1.1"

# Answer keys for the simulated test companies (the leaks that were planted on purpose).
ANSWER_KEYS = {
    "company_a": [("Short delivery", "Sahel Agro Inputs Ltd"), ("Invoice price above PO price", "CleanWave Chemicals Ltd"),
                  ("Slow approvals", "Kano branch finance approvals"), ("Supplier performance decline", "Trans-Niger Equipment Ltd")],
    "company_b": [("Short delivery", "Mombasa Grain Traders"), ("Invoice price above PO price", "Rift Valley Cleaning Co"),
                  ("Slow approvals", "Kisumu branch finance approvals"), ("Supplier performance decline", "Nyali Handling Equipment")],
}
EVIDENCE_COLUMNS = ["po_id", "supplier", "branch", "product", "po_date", "ordered_qty", "received_qty", "invoice_qty",
                    "po_unit_price", "invoice_unit_price", "approval_days", "days_late", "po_total"]


def build_evidence(led, findings, cfg):
    """The actual orders behind every finding (one row per order per finding)."""
    parts = []
    cols = [c for c in EVIDENCE_COLUMNS if c in led.columns]
    for f in findings.itertuples():
        if f.finding_type == "Short delivery":
            d = led[(led["supplier"] == f.entity) & (led["invoice_qty"] > led["received_qty"]) & led["received_qty"].notna()].copy()
            d["exposure"] = (d["invoice_qty"] - d["received_qty"]) * d["invoice_unit_price"]
            basis = "identified exposure"
        elif f.finding_type == "Invoice price above PO price":
            d = led[(led["supplier"] == f.entity) & (led["price_gap_pct"] > cfg["price_tolerance"])].copy()
            d["exposure"] = (d["invoice_unit_price"] - d["po_unit_price"]) * d["invoice_qty"]
            basis = "identified exposure"
        elif f.finding_type == "Slow approvals":
            d = led[led["approval_days"] > cfg["approval_limit_days"]].copy()
            if "branch" in led.columns and f.entity.endswith(" branch finance approvals"):
                d = d[d["branch"] == f.entity[: -len(" branch finance approvals")]]
            d["exposure"] = d["po_total"]
            basis = "order value held up"
        else:   # supplier performance decline: the late orders in the most recent months
            g = led[(led["supplier"] == f.entity) & led["days_late"].notna()]
            months = sorted(g["po_month"].unique())[-cfg["decline_window"]:]
            d = g[g["po_month"].isin(months) & (g["days_late"] > cfg["late_days"])].copy()
            d["exposure"] = 0.0
            basis = "late orders in the most recent months"
        d = d[cols + ["exposure"]].copy()
        d.insert(0, "exposure_basis", basis)
        d.insert(0, "finding_id", f.finding_id)
        parts.append(d)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["finding_id", "exposure_basis"] + cols + ["exposure"])


def scorecard(findings, key):
    """Compare the leaks that were planted with the leaks that were found."""
    found = set(zip(findings["finding_type"], findings["entity"])) if len(findings) else set()
    planted = set(key)
    rows = [dict(finding_type=t, entity=e, planted=True, found=(t, e) in found) for t, e in key]
    rows += [dict(finding_type=t, entity=e, planted=False, found=True) for t, e in sorted(found - planted)]
    detail = pd.DataFrame(rows)
    summary = dict(planted=len(planted), found=len(planted & found), missed=len(planted - found),
                   false_alarms=len(found - planted))
    return summary, detail


def build_data_pack(result, company, source_file="", answer_key=None, explanations=None, out_dir=None, zip_it=True):
    """Save everything the dashboard needs for ONE company: findings, the orders behind each finding, a detection
    scorecard (when an answer key exists), trends, risky orders and a run log. Returns the folder path."""
    import shutil
    from datetime import datetime, timezone
    if result.get("stopped") or "config" not in result:
        raise ValueError(f"Cannot build a pack yet: {result.get('stopped', 'the engine did not finish')}. "
                         "Fix the column matches first (use overrides) and run onboard again.")
    cfg, led, findings = result["config"], result["ledger"], result["findings"].copy()
    slug = re.sub(r"[^a-z0-9]+", "_", company.lower()).strip("_")
    out_dir = out_dir or f"seepsight_pack_{slug}"
    os.makedirs(out_dir, exist_ok=True)
    cur = cfg["currency"]

    # 1. findings (confirmed discrepancies), with case-tracking columns the dashboard fills in
    findings.insert(2, "category", "Confirmed discrepancy")
    findings = findings.rename(columns={"leakage": "identified_exposure", "orders_held": "order_value_held_up"})
    findings["currency"] = cur
    findings["status"], findings["owner"], findings["note"] = "Open", "", ""
    findings.to_csv(os.path.join(out_dir, "findings.csv"), index=False)

    # 2. evidence: the orders behind each finding (and a check that the counts agree)
    ev = build_evidence(led, result["findings"], cfg)
    ev.to_csv(os.path.join(out_dir, "evidence.csv"), index=False)
    counts_ok = True
    for f in result["findings"].itertuples():
        if pd.notna(f.affected_orders) and int((ev["finding_id"] == f.finding_id).sum()) != int(f.affected_orders):
            counts_ok = False

    # 3. exposure by supplier
    leak = ev[ev["exposure_basis"] == "identified exposure"]
    if len(leak):
        leak = leak.merge(result["findings"][["finding_id", "finding_type"]], on="finding_id")
        (leak.pivot_table(index="supplier", columns="finding_type", values="exposure", aggfunc="sum", fill_value=0)
             .assign(total=lambda t: t.sum(axis=1)).sort_values("total", ascending=False).reset_index()
             .to_csv(os.path.join(out_dir, "exposure_by_supplier.csv"), index=False))

    # 4. trends
    def agg(g):
        known = g["received_qty"].notna() if "received_qty" in g else pd.Series(False, index=g.index)
        return pd.Series(dict(
            orders=len(g), spend=g["po_total"].sum(),
            avg_days_late=g["days_late"].mean() if "days_late" in g else np.nan,
            late_rate=(g["days_late"] > cfg["late_days"]).mean() if "days_late" in g else np.nan,
            fill_rate=(g.loc[known, "received_qty"].sum() / g.loc[known, "ordered_qty"].sum()) if known.any() else np.nan,
            avg_approval_days=g["approval_days"].mean() if "approval_days" in g else np.nan))
    pd.DataFrame([dict(po_month=k, **agg(g).to_dict()) for k, g in led.groupby("po_month")]) \
        .to_csv(os.path.join(out_dir, "monthly_trend.csv"), index=False)
    pd.DataFrame([dict(supplier=k[0], po_month=k[1], **agg(g).to_dict()) for k, g in led.groupby(["supplier", "po_month"])]) \
        .to_csv(os.path.join(out_dir, "supplier_month.csv"), index=False)

    # 5. predicted risk (kept separate from confirmed findings)
    tr = result.get("trace_all")
    metrics = (result.get("risk") or {}).get("metrics")
    if tr is not None and len(tr) and (tr["source"] == "ML_MODEL").any():
        ml = tr[tr["source"] == "ML_MODEL"].copy()
        ml["key_drivers"] = ml["key_drivers"].astype(str).map(lambda s: ", ".join(re.findall(r"([A-Za-z_][A-Za-z_0-9=]*)\s*\(", s)))
        ml[["record_ref", "entity", "severity", "risk_score", "key_drivers", "evidence", "later_outcome",
            "model_precision", "model_recall"]].rename(columns={"record_ref": "po_id", "later_outcome": "actual_problem"}) \
            .assign(category="Predicted risk", currency=cur).to_csv(os.path.join(out_dir, "risk_orders.csv"), index=False)

    # 6. detection scorecard (only when we know the planted leaks)
    score = None
    key = ANSWER_KEYS.get(answer_key) if isinstance(answer_key, str) else answer_key
    if key:
        score, detail = scorecard(result["findings"], key)
        detail.to_csv(os.path.join(out_dir, "scorecard.csv"), index=False)

    # 7. optional AI explanations
    if explanations is not None:
        ex = pd.read_csv(explanations) if isinstance(explanations, str) else explanations
        ex.to_csv(os.path.join(out_dir, "explanations.csv"), index=False)

    # 8. run log
    log = dict(
        company=company, source_file=os.path.basename(source_file), analysed_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        engine_version=ENGINE_VERSION, currency=cur, rows_in_file=result["quality"]["rows_in_file"],
        rows_used=result["quality"]["rows_used"], dropped=result["quality"]["dropped"],
        warnings=result["quality"]["warnings"], detectors=result["quality"]["detectors"],
        thresholds={k: cfg[k] for k in ("price_tolerance", "approval_limit_days", "late_days", "min_pattern", "decline_days", "decline_window")},
        column_matches={k: dict(column=v["column"], confidence=v["confidence"], source=v["source"]) for k, v in result["mapping"].items()},
        findings=len(findings), evidence_rows=len(ev), evidence_counts_match_findings=counts_ok,
        total_identified_exposure=float(findings["identified_exposure"].sum()) if len(findings) else 0.0,
        total_order_value_held_up=float(findings["order_value_held_up"].sum()) if len(findings) else 0.0,
        risk_model=metrics, scorecard=score,
        note="Amounts are identified exposure, not recovered money, until the business confirms recovery.")
    with open(os.path.join(out_dir, "run_log.json"), "w") as fh:
        json.dump(log, fh, indent=2, default=str)

    print(f"\nDATA PACK for {company} -> {out_dir}/")
    print(f"  findings: {len(findings)} | evidence rows: {len(ev)} | counts agree with findings: {counts_ok}")
    print(f"  identified exposure: {cur} {log['total_identified_exposure']:,.0f} | order value held up: {cur} {log['total_order_value_held_up']:,.0f}")
    if score:
        print(f"  scorecard: {score['planted']} planted, {score['found']} found, {score['missed']} missed, {score['false_alarms']} false alarms")
    else:
        print("  scorecard: no answer key for this company (normal for real data)")
    print("  files:", ", ".join(sorted(os.listdir(out_dir))))
    if zip_it:
        zip_path = shutil.make_archive(out_dir, "zip", out_dir)
        print(f"  zipped: {zip_path}")
        try:
            from google.colab import files
            files.download(zip_path)
        except ImportError:
            pass
    return out_dir
