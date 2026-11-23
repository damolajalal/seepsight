
"""Seepsight Design System
Premium, editorial enterprise SaaS interface.
"""

import html
import streamlit as st


# =========================================================
# 1. BRAND IDENTITY
# =========================================================

NAVY = "#142B3B"
NAVY_LIGHT = "#203E50"
SAGE = "#D5E8E1"
SAGE_DARK = "#47796B"
IVORY = "#F7F5F0"
WHITE = "#FFFFFF"
AMBER_BRAND = "#D18A58"
TEXT = "#263944"
MUTED = "#71808A"
BORDER = "#E6E5DF"

# Semantic colours: reserved for actual business status.
RED = "#C0392B"
AMBER = "#D97706"
GREEN = "#15803D"
BLUE = "#1D6FB8"

KIND = {
    "red": (RED, "#FCECE9"),
    "amber": (AMBER, "#FFF3DF"),
    "green": (GREEN, "#E6F5EA"),
    "blue": (BLUE, "#EAF1F8"),
}

SEV_KIND = {
    "High": "red",
    "Medium": "amber",
    "Low": "blue",
}

SEV_LABEL = {
    "High": "High priority",
    "Medium": "Medium priority",
    "Low": "Low priority",
}

STATUS_KIND = {
    "Open": "amber",
    "Investigating": "blue",
    "Resolved": "green",
}


# =========================================================
# 2. GLOBAL DESIGN SYSTEM
# =========================================================

CSS = """
:root {
    --sp-navy: #142B3B;
    --sp-navy-light: #203E50;
    --sp-sage: #D5E8E1;
    --sp-sage-dark: #47796B;
    --sp-ivory: #F7F5F0;
    --sp-white: #FFFFFF;
    --sp-amber: #D18A58;
    --sp-text: #263944;
    --sp-muted: #71808A;
    --sp-border: #E6E5DF;
}

/* -------------------------------------------------------
   APPLICATION FOUNDATION
------------------------------------------------------- */

html,
body,
[data-testid="stApp"] {
    background: var(--sp-ivory);
    color: var(--sp-text);
    font-family: "Inter", "Segoe UI", sans-serif;
}

.block-container {
    max-width: 1380px;
    padding-top: 2.2rem;
    padding-bottom: 4rem;
}

/* Remove excessive default visual clutter */

[data-testid="stDecoration"] {
    background: var(--sp-sage-dark);
}

/* -------------------------------------------------------
   SIDEBAR
------------------------------------------------------- */

[data-testid="stSidebar"] {
    background: var(--sp-navy);
    border-right: 1px solid #294354;
}

[data-testid="stSidebar"] > div:first-child {
    background: var(--sp-navy);
}

[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] a {
    color: #E4ECEE;
}

[data-testid="stSidebar"] a {
    border-radius: 7px;
    transition: background 0.2s ease;
}

[data-testid="stSidebar"] a:hover {
    background: #203E50;
    color: #FFFFFF;
}

[data-testid="stSidebar"] a[aria-current="page"] {
    background: #294858;
    border-left: 3px solid #A9D1C3;
    border-radius: 7px;
}

[data-testid="stSidebar"] [data-baseweb="select"] * {
    color: var(--sp-navy) !important;
}

/* Brand */

.sp-brand {
    color: #FFFFFF !important;
    font-size: 27px;
    font-weight: 750;
    letter-spacing: -1.1px;
    line-height: 1.15;
}

.sp-brand i {
    color: #A9D1C3;
    font-style: normal;
}

.sp-tag {
    color: #B7C8CF !important;
    font-size: 11px;
    line-height: 1.7;
    letter-spacing: 0.25px;
    margin-top: 9px;
}

/* -------------------------------------------------------
   PAGE HEADERS
------------------------------------------------------- */

.sp-h1 {
    color: var(--sp-navy);
    font-size: 32px;
    font-weight: 750;
    letter-spacing: -1.1px;
    line-height: 1.2;
    margin: 0 0 9px;
}

.sp-sub {
    color: var(--sp-muted);
    font-size: 15px;
    line-height: 1.7;
    margin: 0 0 27px;
    max-width: 850px;
}

.sp-eyebrow {
    color: var(--sp-sage-dark);
    font-size: 11px;
    font-weight: 750;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    margin-bottom: 9px;
}

/* -------------------------------------------------------
   CONTENT CARDS
------------------------------------------------------- */

.sp-card {
    background: var(--sp-white);
    border: 1px solid var(--sp-border);
    border-radius: 12px;
    padding: 21px 23px;
    margin-bottom: 15px;
    box-shadow: 0 3px 12px rgba(20, 43, 59, 0.025);
}

.sp-card h4 {
    color: var(--sp-navy);
    font-size: 16px;
    font-weight: 700;
    letter-spacing: -0.2px;
    margin: 0 0 9px;
}

.sp-card p {
    color: var(--sp-muted);
    line-height: 1.65;
}

/* -------------------------------------------------------
   METRICS
------------------------------------------------------- */

div[data-testid="stMetric"] {
    background: var(--sp-white);
    border: 1px solid var(--sp-border);
    border-radius: 12px;
    padding: 18px 19px;
    box-shadow: 0 3px 12px rgba(20, 43, 59, 0.025);
}

div[data-testid="stMetricLabel"] {
    color: var(--sp-muted);
    font-size: 12px;
    font-weight: 550;
}

div[data-testid="stMetricValue"] {
    color: var(--sp-navy);
    font-size: clamp(16px, 1.7vw, 25px);
    font-weight: 750;
    letter-spacing: -0.7px;
    white-space: nowrap;
    overflow-wrap: normal;
    word-break: keep-all;
    font-variant-numeric: tabular-nums;
}

div[data-testid="stMetricValue"] > div {
    white-space: nowrap;
    overflow-wrap: normal;
    word-break: keep-all;
    font-size: inherit;
}

div[data-testid="stMetricDelta"] {
    font-size: 12px;
}

/* -------------------------------------------------------
   BUTTONS
------------------------------------------------------- */

.stButton > button,
.stDownloadButton > button {
    border-radius: 8px;
    font-weight: 650;
    min-height: 40px;
    transition: all 0.2s ease;
}

.stButton > button[kind="primary"] {
    background: var(--sp-navy);
    border: 1px solid var(--sp-navy);
    color: #FFFFFF;
}

.stButton > button[kind="primary"]:hover {
    background: var(--sp-navy-light);
    border-color: var(--sp-navy-light);
    color: #FFFFFF;
}

.stButton > button[kind="secondary"]:hover,
.stDownloadButton > button:hover {
    border-color: var(--sp-sage-dark);
    color: var(--sp-navy);
}

/* -------------------------------------------------------
   FORMS AND INPUTS
------------------------------------------------------- */

.stTextInput input,
.stTextArea textarea,
.stNumberInput input {
    background: #FFFFFF;
    border: 1px solid var(--sp-border);
    border-radius: 8px;
    color: var(--sp-text);
}

.stTextInput input:focus,
.stTextArea textarea:focus,
.stNumberInput input:focus {
    border-color: var(--sp-sage-dark);
    box-shadow: 0 0 0 1px var(--sp-sage-dark);
}

[data-baseweb="select"] > div {
    border-radius: 8px;
    border-color: var(--sp-border);
}

/* -------------------------------------------------------
   TABS
------------------------------------------------------- */

.stTabs [data-baseweb="tab"] {
    color: var(--sp-muted);
    font-weight: 600;
}

.stTabs [aria-selected="true"] {
    color: var(--sp-navy);
}

.stTabs [data-baseweb="tab-highlight"] {
    background: var(--sp-sage-dark);
}

/* -------------------------------------------------------
   TABLES AND DATA
------------------------------------------------------- */

[data-testid="stDataFrame"],
[data-testid="stTable"] {
    border: 1px solid var(--sp-border);
    border-radius: 10px;
    overflow: hidden;
}

/* -------------------------------------------------------
   ALERTS AND EXPANDERS
------------------------------------------------------- */

[data-testid="stAlert"] {
    border-radius: 9px;
}

[data-testid="stExpander"] {
    background: #FFFFFF;
    border: 1px solid var(--sp-border);
    border-radius: 9px;
}

/* -------------------------------------------------------
   DIVIDERS
------------------------------------------------------- */

hr {
    border-color: var(--sp-border);
}

/* -------------------------------------------------------
   RESPONSIVE DESIGN
------------------------------------------------------- */

@media (max-width: 768px) {
    .block-container {
        padding: 1.3rem 1rem 2rem;
    }

    .sp-h1 {
        font-size: 26px;
    }

    .sp-sub {
        font-size: 14px;
        margin-bottom: 19px;
    }

    .sp-card {
        padding: 16px;
    }

    div[data-testid="stMetric"] {
        min-width: 0;
        padding: 12px 10px;
    }

    div[data-testid="stMetricLabel"] {
        white-space: normal;
        overflow-wrap: anywhere;
        line-height: 1.3;
    }

    div[data-testid="stMetricValue"],
    div[data-testid="stMetricValue"] > div {
        min-width: 0;
        max-width: 100%;
        font-size: clamp(12px, 3.8vw, 17px);
        line-height: 1.25;
        white-space: normal;
        overflow-wrap: anywhere;
        word-break: normal;
    }
}
"""


# =========================================================
# 3. APPLY STYLES
# =========================================================

def inject_css():
    """Apply the shared Seepsight visual design."""

    st.markdown(
        f"<style>{CSS}</style>",
        unsafe_allow_html=True,
    )


# =========================================================
# 4. STATUS CHIPS
# =========================================================

def chip(text, kind="blue"):
    """Create a compact, accessible business status chip."""

    fg, bg = KIND.get(kind, KIND["blue"])
    safe_text = html.escape(str(text))

    return (
        f'<span style="'
        f'background:{bg};'
        f'color:{fg};'
        f'padding:4px 10px;'
        f'border-radius:6px;'
        f'font-size:11px;'
        f'font-weight:700;'
        f'border:1px solid {fg}35;'
        f'white-space:nowrap;'
        f'display:inline-block;'
        f'">'
        f'{safe_text}'
        f'</span>'
    )


# =========================================================
# 5. CURRENCY FORMATTING
# =========================================================

def money(cur, v):
    """Format currency values consistently."""

    try:
        return f"{cur} {float(v):,.0f}"
    except (TypeError, ValueError):
        return f"{cur} 0"


# =========================================================
# 6. PAGE HEADER COMPONENT
# =========================================================

def page_header(title, sub=""):
    """Display a consistent page heading."""

    safe_title = html.escape(str(title))
    safe_sub = html.escape(str(sub))

    st.markdown(
        f"""
        <h1 class="sp-h1">{safe_title}</h1>
        <p class="sp-sub">{safe_sub}</p>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# 7. CONTENT CARD COMPONENT
# =========================================================

def card(html_content):
    """Render a shared content card.

    Existing callers may pass trusted formatted HTML.
    """

    st.markdown(
        f'<div class="sp-card">{html_content}</div>',
        unsafe_allow_html=True,
    )


# =========================================================
# 8. SIDEBAR BRAND COMPONENT
# =========================================================

def sidebar_header():
    """Display the Seepsight brand in the application sidebar.

    No demo workspace selector is displayed here.
    """

    with st.sidebar:
        st.markdown(
            """
            <div class="sp-brand">Seep<i>sight</i></div>
            <div class="sp-tag">
                See the gaps. Show the impact.
                Act with confidence.
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.write("")
