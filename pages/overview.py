"""Seepsight company procurement overview."""

import pandas as pd
import streamlit as st

from seepsight import plain, ui, workspace


# =========================================================
# 1. COMPANY WORKSPACE
# =========================================================

w = workspace.current(allow_empty=True)

if w is None:
    account = st.session_state.get("seepsight_auth", {})
    company_name = (
        account.get("company_name")
        or account.get("company")
        or "your company"
    ).strip()
    display_company = company_name.title()

    ui.page_header(
        f"Welcome to {display_company}",
        "Your procurement intelligence workspace is ready. "
        "Connect your company's data to get started.",
    )

    with st.container(border=True):
        st.caption("YOUR NEXT STEP")
        st.subheader("Bring your procurement data into focus.")
        st.write(
            "Connect your purchasing records to let Seepsight analyse "
            "procurement activity, uncover potential financial leakage, "
            "identify supplier risks and highlight opportunities for improvement."
        )
        st.page_link(
            "pages/connect.py",
            label="Connect your procurement data",
            icon=":material/database_upload:",
            use_container_width=True,
        )

    st.markdown("### How Seepsight works")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**01 · Connect**")
        st.write("Upload procurement files or connect your company's database.")
    with col2:
        st.markdown("**02 · Analyse**")
        st.write("Let Seepsight examine purchasing records and identify potential risks.")
    with col3:
        st.markdown("**03 · Take action**")
        st.write("Review supporting evidence, investigate findings and track corrective actions.")

    st.info(
        "Your procurement dashboard will populate with your company's actual "
        "analysis results after data is connected."
    )
    st.stop()


# =========================================================
# 2. NORMALISE AVAILABLE WORKSPACE TABLES
# =========================================================

cur = w.get("cur", "NGN")
f = w.get("findings")
mo = w.get("monthly")
evidence = w.get("evidence")
risk = w.get("risk")
supplier_exposure = w.get("exposure")

for name, frame in (
    ("findings", f),
    ("monthly", mo),
    ("evidence", evidence),
    ("risk", risk),
    ("exposure", supplier_exposure),
):
    if frame is None:
        if name == "findings":
            f = pd.DataFrame()
        elif name == "monthly":
            mo = pd.DataFrame()
        elif name == "evidence":
            evidence = pd.DataFrame()
        elif name == "risk":
            risk = pd.DataFrame()
        else:
            supplier_exposure = pd.DataFrame()

company_name = w.get("name", "Your company")


# =========================================================
# 3. EXECUTIVE HEADER
# =========================================================

st.markdown(
    """
    <div class="sp-dashboard-hero">
      <div class="sp-dashboard-eyebrow">PROCUREMENT INTELLIGENCE</div>
      <div class="sp-dashboard-title">Your procurement at a glance</div>
      <div class="sp-dashboard-copy">
        A clear view of purchasing activity, financial exposure and supplier performance.
      </div>
    </div>
    <style>
      .sp-dashboard-hero {
        background: linear-gradient(118deg, #142B3B 0%, #203E50 72%, #47796B 140%);
        border-radius: 16px;
        padding: 25px 28px;
        margin: 0 0 22px 0;
        color: #FFFFFF;
        box-shadow: 0 8px 24px rgba(20,43,59,.10);
      }
      .sp-dashboard-eyebrow {
        color: #B9D9CE;
        font-size: 10px;
        font-weight: 750;
        letter-spacing: 1.7px;
        margin-bottom: 9px;
      }
      .sp-dashboard-title {
        color: #FFFFFF;
        font-size: clamp(22px, 3vw, 30px);
        font-weight: 760;
        letter-spacing: -.8px;
        line-height: 1.2;
        margin-bottom: 8px;
      }
      .sp-dashboard-copy {
        color: #D7E3E5;
        font-size: 14px;
        line-height: 1.6;
      }
      .sp-section-kicker {
        color: #47796B;
        font-size: 10px;
        font-weight: 750;
        letter-spacing: 1.4px;
        text-transform: uppercase;
        margin: 4px 0 5px 0;
      }
      @media (max-width: 768px) {
        .sp-dashboard-hero { padding: 20px 18px; border-radius: 12px; }
      }
    </style>
    """,
    unsafe_allow_html=True,
)
st.caption(f"ACTIVE WORKSPACE  ·  {company_name}")


# =========================================================
# 4. KEY PROCUREMENT METRICS
# =========================================================

spend = (
    pd.to_numeric(mo["spend"], errors="coerce").sum()
    if "spend" in mo.columns else 0
)
exposure = (
    pd.to_numeric(f["identified_exposure"], errors="coerce").sum()
    if "identified_exposure" in f.columns else 0
)
issue_count = len(f)
held_value = (
    pd.to_numeric(f["order_value_held_up"], errors="coerce").sum()
    if "order_value_held_up" in f.columns else 0
)

st.markdown('<div class="sp-section-kicker">Executive summary</div>', unsafe_allow_html=True)
st.markdown("### Key procurement indicators")

# Two-by-two layout keeps the figures readable on mobile screens.
kpi_row_one = st.columns(2, gap="medium")
kpi_row_two = st.columns(2, gap="medium")

kpi_row_one[0].metric(
    "Purchasing spend reviewed",
    ui.money(cur, spend),
    help="Total purchasing value represented in the connected records.",
)
kpi_row_one[1].metric(
    "Potential cost exposure",
    ui.money(cur, exposure),
    help=(
        "Potential overpayments or value associated with delivery discrepancies. "
        "These are amounts to investigate, not confirmed losses."
    ),
)
kpi_row_two[0].metric(
    "Issues identified",
    f"{issue_count:,}",
    help="Findings identified by Seepsight's procurement checks.",
)
kpi_row_two[1].metric(
    "Orders awaiting attention",
    ui.money(cur, held_value),
    help="Value associated with orders flagged for further attention.",
)


# =========================================================
# 5. PURCHASING ACTIVITY CHARTS
# =========================================================

st.markdown('<div class="sp-section-kicker">Spend and activity</div>', unsafe_allow_html=True)
st.markdown("### Purchasing performance")

left, right = st.columns(2, gap="large")

with left:
    with st.container(border=True):
        st.markdown("**Monthly purchasing spend**")
        if not mo.empty and {"po_month", "spend"}.issubset(mo.columns):
            spend_chart = mo[["po_month", "spend"]].copy()
            spend_chart["spend"] = pd.to_numeric(spend_chart["spend"], errors="coerce")
            spend_chart = spend_chart.dropna(subset=["spend"]).sort_values("po_month")
            if not spend_chart.empty:
                st.bar_chart(
                    spend_chart.set_index("po_month")[["spend"]],
                    height=250,
                    color="#47796B",
                )
                st.caption(f"Total reviewed across available months: {ui.money(cur, spend)}")
            else:
                st.caption("Spend values are not available for charting.")
        else:
            st.caption("Monthly spend information is not available in the connected records.")

with right:
    with st.container(border=True):
        st.markdown("**Monthly purchase orders**")
        if not mo.empty and {"po_month", "orders"}.issubset(mo.columns):
            orders_chart = mo[["po_month", "orders"]].copy()
            orders_chart["orders"] = pd.to_numeric(orders_chart["orders"], errors="coerce")
            orders_chart = orders_chart.dropna(subset=["orders"]).sort_values("po_month")
            if not orders_chart.empty:
                st.bar_chart(
                    orders_chart.set_index("po_month")[["orders"]],
                    height=250,
                    color="#D18A58",
                )
                st.caption(f"{int(orders_chart['orders'].sum()):,} orders represented in the monthly trend.")
            else:
                st.caption("Order counts are not available for charting.")
        else:
            st.caption("Monthly order information is not available in the connected records.")


# =========================================================
# 6. DELIVERY AND APPROVAL PERFORMANCE
# =========================================================

st.markdown("### Delivery and approval performance")
delivery_col, approval_col = st.columns(2, gap="large")

with delivery_col:
    with st.container(border=True):
        st.markdown("**Average delivery delay**")
        if not mo.empty and {"po_month", "avg_days_late"}.issubset(mo.columns):
            delivery = mo[["po_month", "avg_days_late"]].copy()
            delivery["avg_days_late"] = pd.to_numeric(delivery["avg_days_late"], errors="coerce")
            delivery = delivery.dropna(subset=["avg_days_late"]).sort_values("po_month")
            if not delivery.empty:
                st.line_chart(
                    delivery.set_index("po_month")[["avg_days_late"]],
                    height=230,
                    color="#47796B",
                )
                st.caption("Average days late by purchase-order month.")
            else:
                st.caption("Delivery delay values are not available for charting.")
        else:
            st.caption("Delivery trend information is not available in the connected records.")

with approval_col:
    with st.container(border=True):
        st.markdown("**Average approval turnaround**")
        if not mo.empty and {"po_month", "avg_approval_days"}.issubset(mo.columns):
            approval = mo[["po_month", "avg_approval_days"]].copy()
            approval["avg_approval_days"] = pd.to_numeric(approval["avg_approval_days"], errors="coerce")
            approval = approval.dropna(subset=["avg_approval_days"]).sort_values("po_month")
            if not approval.empty:
                st.line_chart(
                    approval.set_index("po_month")[["avg_approval_days"]],
                    height=230,
                    color="#D18A58",
                )
                st.caption("Average elapsed approval days by purchase-order month.")
            else:
                st.caption("Approval turnaround values are not available for charting.")
        else:
            st.caption("Approval trend information is not available in the connected records.")


# =========================================================
# 7. SUPPLIER EXPOSURE AND FINDINGS MIX
# =========================================================

st.markdown('<div class="sp-section-kicker">Where to focus</div>', unsafe_allow_html=True)
st.markdown("### Exposure and findings")

supplier_col, finding_col = st.columns(2, gap="large")

with supplier_col:
    with st.container(border=True):
        st.markdown("**Potential exposure by supplier**")
        if (
            not supplier_exposure.empty
            and {"supplier", "total"}.issubset(supplier_exposure.columns)
        ):
            supplier_chart = supplier_exposure[["supplier", "total"]].copy()
            supplier_chart["total"] = pd.to_numeric(supplier_chart["total"], errors="coerce")
            supplier_chart = supplier_chart.dropna(subset=["total"])
            supplier_chart = supplier_chart[supplier_chart["total"] > 0].sort_values(
                "total", ascending=False
            ).head(8)
            if not supplier_chart.empty:
                st.bar_chart(
                    supplier_chart.set_index("supplier")[["total"]],
                    height=250,
                    color="#47796B",
                    horizontal=True,
                )
                st.caption("Highest supplier exposure from identified discrepancy evidence.")
            else:
                st.caption("No supplier exposure values are currently available.")
        else:
            st.caption("Supplier-level exposure is not available in the connected records.")

with finding_col:
    with st.container(border=True):
        st.markdown("**Findings by type**")
        if not f.empty and "finding_type" in f.columns:
            finding_mix = (
                f["finding_type"].fillna("Other").astype(str)
                .value_counts()
                .rename_axis("finding_type")
                .reset_index(name="findings")
            )
            st.bar_chart(
                finding_mix.set_index("finding_type")[["findings"]],
                height=250,
                color="#D18A58",
                horizontal=True,
            )
            st.caption("Count of findings by discrepancy type.")
        else:
            st.caption("There are no findings to break down by type.")


# =========================================================
# 8. PRIORITY FINDINGS
# =========================================================

st.markdown('<div class="sp-section-kicker">Recommended attention</div>', unsafe_allow_html=True)
st.markdown("### Priority findings")

if f.empty:
    run_log = w.get("log", {}) or {}
    detector_status = run_log.get("detectors", {}) or {}
    skipped = {
        name: status for name, status in detector_status.items()
        if str(status).lower() != "ready"
    }

    if skipped:
        st.warning(
            "No findings are currently displayed, but this is an incomplete review "
            "because some checks could not run. See Findings for the missing data or mappings."
        )
        for name, status in skipped.items():
            st.caption(f"{name}: {status}")
    elif detector_status:
        st.info(
            "No qualifying discrepancies were identified by the checks that completed. "
            "This does not rule out issues outside the available data."
        )
    else:
        st.warning(
            "No findings are available and detector coverage was not recorded. "
            "Reconnect or reanalyse the data before treating this as a clear result."
        )
else:
    rank = {"High": 0, "Medium": 1, "Low": 2}
    ordered = f.copy()
    ordered["_priority"] = (
        ordered["severity"].map(rank).fillna(3)
        if "severity" in ordered.columns else 3
    )
    ordered["_exposure"] = (
        pd.to_numeric(ordered["identified_exposure"], errors="coerce").fillna(0)
        if "identified_exposure" in ordered.columns else 0
    )
    ordered = ordered.sort_values(["_priority", "_exposure"], ascending=[True, False])

    for _, row in ordered.head(5).iterrows():
        severity = str(row.get("severity", "Low"))
        kind = ui.SEV_KIND.get(severity, "blue")
        label = ui.SEV_LABEL.get(severity, "Review")
        finding_id = row.get("finding_id")

        if finding_id is not None and "finding_id" in evidence.columns:
            ev = evidence[evidence["finding_id"] == finding_id]
        else:
            ev = pd.DataFrame()

        with st.container(border=True):
            detail_col, action_col = st.columns([6, 1])
            detail_col.markdown(
                f"{ui.chip(label, kind)} &nbsp; **{plain.title(row)}**",
                unsafe_allow_html=True,
            )
            detail_col.write(plain.what_we_found(row, ev, cur))
            if action_col.button("Review", key=f"open_{finding_id}"):
                st.session_state["selected"] = finding_id
                st.switch_page("pages/findings.py")

st.page_link(
    "pages/findings.py",
    label="View all findings and supporting evidence",
    icon=":material/arrow_forward:",
)


# =========================================================
# 9. PROCUREMENT RISK SIGNALS
# =========================================================

with st.expander("Procurement risk signals"):
    st.caption(
        "These are orders flagged for further review. "
        "A risk signal is not proof of wrongdoing or a confirmed loss."
    )
    if risk.empty:
        st.write("No procurement risk signals are currently available.")
    else:
        display = pd.DataFrame()
        if "po_id" in risk.columns:
            display["Order number"] = risk["po_id"]
        if "entity" in risk.columns:
            display["Supplier"] = risk["entity"]
        if "risk_score" in risk.columns:
            display["Risk level"] = risk["risk_score"].map(plain.warning_level)
        if "key_drivers" in risk.columns:
            display["Why it was flagged"] = risk["key_drivers"].map(plain.driver_text)
        if not display.empty:
            st.dataframe(display, hide_index=True, width="stretch")
        else:
            st.caption("Risk records are available, but expected display fields were not found.")


# =========================================================
# 10. ANALYSIS CONTEXT
# =========================================================

with st.expander("About this procurement analysis"):
    st.write(
        "Seepsight analyses the procurement records connected to your company. "
        "Findings and risk signals support human review and informed business decisions."
    )
    st.write(
        "Potential financial exposure should not be interpreted as a confirmed loss "
        "until the underlying transactions and supporting evidence have been checked."
    )
    st.caption(
        "The analysis reflects the records available to Seepsight at the time of processing."
    )
