
"""Seepsight company procurement overview."""

import pandas as pd
import streamlit as st

from seepsight import plain, ui, workspace


# =========================================================
# 1. COMPANY WORKSPACE
# =========================================================

w = workspace.current(allow_empty=True)


# =========================================================
# 2. FIRST-TIME COMPANY EXPERIENCE
# =========================================================

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

    st.markdown("")

    with st.container(border=True):

        st.caption("YOUR NEXT STEP")

        st.subheader("Bring your procurement data into focus.")

        st.write(
            "Connect your purchasing records to let Seepsight "
            "analyse procurement activity, uncover potential "
            "financial leakage, identify supplier risks and "
            "highlight opportunities for improvement."
        )

        st.markdown("")

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
        st.write(
            "Upload procurement files or connect your company's "
            "database."
        )

    with col2:
        st.markdown("**02 · Analyse**")
        st.write(
            "Let Seepsight examine purchasing records and "
            "identify potential risks."
        )

    with col3:
        st.markdown("**03 · Take action**")
        st.write(
            "Review supporting evidence, investigate findings "
            "and track corrective actions."
        )

    st.info(
        "Your procurement dashboard will populate with your "
        "company's actual analysis results after data is connected."
    )

    st.stop()


# =========================================================
# 3. ACTIVE COMPANY ANALYTICS
# =========================================================

cur = w.get("cur", "NGN")

f = w.get("findings")
mo = w.get("monthly")
evidence = w.get("evidence")
risk = w.get("risk")

if f is None:
    f = pd.DataFrame()

if mo is None:
    mo = pd.DataFrame()

if evidence is None:
    evidence = pd.DataFrame()

if risk is None:
    risk = pd.DataFrame()

company_name = w.get("name", "Your company")

ui.page_header(
    "Procurement overview",
    f"Here is the latest view of procurement activity, "
    f"potential risks and opportunities across {company_name}.",
)


# =========================================================
# 4. KEY PROCUREMENT METRICS
# =========================================================

spend = (
    pd.to_numeric(mo["spend"], errors="coerce").sum()
    if "spend" in mo.columns
    else 0
)

exposure = (
    pd.to_numeric(
        f["identified_exposure"],
        errors="coerce",
    ).sum()
    if "identified_exposure" in f.columns
    else 0
)

issue_count = len(f)

held_value = (
    pd.to_numeric(
        f["order_value_held_up"],
        errors="coerce",
    ).sum()
    if "order_value_held_up" in f.columns
    else 0
)

c = st.columns(4)

c[0].metric(
    "Purchasing spend reviewed",
    ui.money(cur, spend),
    help="Total purchasing value represented in the connected records.",
)

c[1].metric(
    "Potential cost exposure",
    ui.money(cur, exposure),
    help=(
        "Potential overpayments or value associated with "
        "delivery discrepancies. These are amounts to investigate, "
        "not confirmed losses."
    ),
)

c[2].metric(
    "Issues identified",
    f"{issue_count:,}",
    help="Findings identified by Seepsight's procurement checks.",
)

c[3].metric(
    "Orders awaiting attention",
    ui.money(cur, held_value),
    help="Value associated with orders flagged for further attention.",
)


# =========================================================
# 5. PRIORITY FINDINGS
# =========================================================

st.markdown("### Priority findings")

if f.empty:

    st.success(
        "No procurement findings are currently available "
        "for this analysis."
    )

else:

    rank = {
        "High": 0,
        "Medium": 1,
        "Low": 2,
    }

    ordered = f.copy()

    ordered["_priority"] = (
        ordered["severity"].map(rank).fillna(3)
        if "severity" in ordered.columns
        else 3
    )

    if "identified_exposure" in ordered.columns:
        ordered["_exposure"] = pd.to_numeric(
            ordered["identified_exposure"],
            errors="coerce",
        ).fillna(0)
    else:
        ordered["_exposure"] = 0

    ordered = ordered.sort_values(
        ["_priority", "_exposure"],
        ascending=[True, False],
    )

    for _, r in ordered.head(5).iterrows():

        severity = str(r.get("severity", "Low"))
        kind = ui.SEV_KIND.get(severity, "blue")
        label = ui.SEV_LABEL.get(severity, "Review")

        finding_id = r.get("finding_id")

        if (
            finding_id is not None
            and "finding_id" in evidence.columns
        ):
            ev = evidence[
                evidence["finding_id"] == finding_id
            ]
        else:
            ev = pd.DataFrame()

        with st.container(border=True):

            a, b = st.columns([6, 1])

            a.markdown(
                f"{ui.chip(label, kind)} "
                f"&nbsp; **{plain.title(r)}**",
                unsafe_allow_html=True,
            )

            a.write(plain.what_we_found(r, ev, cur))

            if b.button(
                "View details",
                key=f"open_{finding_id}",
            ):
                st.session_state["selected"] = finding_id
                st.switch_page("pages/findings.py")


# =========================================================
# 6. PROCUREMENT TRENDS
# =========================================================

def trend_note(series, unit, worse):
    """Describe the direction of a sufficiently populated trend."""

    s = pd.to_numeric(series, errors="coerce").dropna()

    if len(s) < 6:
        return ""

    first = s.iloc[:3].mean()
    recent = s.iloc[-3:].mean()

    if recent > first + 0.5:
        trend = worse
    elif abs(recent - first) <= 0.5:
        trend = "stayed about the same"
    else:
        trend = "improved"

    return (
        f"Previously averaging {first:.1f} {unit}; "
        f"recently {recent:.1f} {unit}. "
        f"The trend has {trend}."
    )


st.markdown("### Procurement performance trends")

trend_columns = st.columns(2)

with trend_columns[0]:

    st.markdown("**Delivery delays**")

    if (
        not mo.empty
        and {"po_month", "avg_days_late"}.issubset(mo.columns)
    ):

        delivery = mo.set_index("po_month")["avg_days_late"]

        if delivery.notna().any():

            st.line_chart(
                delivery,
                height=230,
                color="#47796B",
            )

            st.caption(
                trend_note(
                    mo["avg_days_late"],
                    "days late",
                    "increased",
                )
            )

        else:
            st.caption(
                "There is not enough delivery information "
                "to display this trend."
            )

    else:
        st.caption(
            "Delivery trend information is not available "
            "in the connected records."
        )


with trend_columns[1]:

    st.markdown("**Approval turnaround**")

    if (
        not mo.empty
        and {"po_month", "avg_approval_days"}.issubset(mo.columns)
    ):

        approval = mo["avg_approval_days"]

        if approval.notna().any():

            st.line_chart(
                mo.set_index("po_month")["avg_approval_days"],
                height=230,
                color="#D18A58",
            )

            st.caption(
                trend_note(
                    approval,
                    "days",
                    "increased",
                )
            )

        else:
            st.caption(
                "Approval dates were not available "
                "in the connected records."
            )

    else:
        st.caption(
            "Approval trend information is not available "
            "in the connected records."
        )


# =========================================================
# 7. PROCUREMENT RISK SIGNALS
# =========================================================

st.markdown("### Procurement risk signals")

st.caption(
    "These are orders flagged for further review. "
    "A risk signal is not proof of wrongdoing or a confirmed loss."
)

if risk.empty:

    st.write(
        "No procurement risk signals are currently available."
    )

else:

    display = pd.DataFrame()

    if "po_id" in risk.columns:
        display["Order number"] = risk["po_id"]

    if "entity" in risk.columns:
        display["Supplier"] = risk["entity"]

    if "risk_score" in risk.columns:
        display["Risk level"] = risk["risk_score"].map(
            plain.warning_level
        )

    if "key_drivers" in risk.columns:
        display["Why it was flagged"] = risk[
            "key_drivers"
        ].map(plain.driver_text)

    if not display.empty:

        st.dataframe(
            display,
            hide_index=True,
            width="stretch",
        )

    else:

        st.caption(
            "Risk records are available, but the expected "
            "display fields were not found."
        )


# =========================================================
# 8. ANALYSIS CONTEXT
# =========================================================

with st.expander("About this procurement analysis"):

    st.write(
        "Seepsight analyses the procurement records connected "
        "to your company. Findings and risk signals support "
        "human review and informed business decisions."
    )

    st.write(
        "Potential financial exposure should not be interpreted "
        "as a confirmed loss until the underlying transactions "
        "and supporting evidence have been checked."
    )

    st.caption(
        "The analysis reflects the records available to "
        "Seepsight at the time of processing."
    )
