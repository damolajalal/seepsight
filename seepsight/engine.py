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
    # Extended procurement entities. These fields are optional in a flat order export;
