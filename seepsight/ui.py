
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
    color-scheme: light;
    --sp-navy: #142B3B;
    --sp-navy-light: #203E50;
    --sp-sage: #D5E8E1;
    --sp-sage-dark: #47796B;
    --sp-ivory: #F5F6F3;
    --sp-white: #FFFFFF;
    --sp-amber: #D18A58;
    --sp-text: #263944;
    --sp-muted: #71808A;
    --sp-border: #E4E9E6;
    --sp-shadow: 0 8px 28px rgba(20, 43, 59, .055);
}

/* Foundation */
html, body, [data-testid="stApp"] {
    background: var(--sp-ivory);
    color: var(--sp-text);
    font-family: Inter, "Segoe UI", sans-serif;
}
[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(ellipse at 88% 0%, rgba(213, 232, 225, .28), transparent 34%),
        var(--sp-ivory);
}
.block-container {
    max-width: 1460px;
    padding: 2.1rem clamp(1.2rem, 3vw, 3rem) 4rem;
}
[data-testid="stDecoration"] {
    background: var(--sp-sage-dark);
    height: 3px;
}
h1, h2, h3, h4, h5 {
    color: var(--sp-navy);
    letter-spacing: -.035em;
}
p, li {
    line-height: 1.65;
}

/* Navigation */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #142B3B 0%, #102432 100%);
    border-right: 1px solid #294354;
}
[data-testid="stSidebar"] > div:first-child {
    background: transparent;
}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] a {
    color: #E4ECEE;
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
    color: #B7C8CF;
}
[data-testid="stSidebar"] a {
    border-radius: 10px;
    margin: 2px 0;
    transition: background .18s ease, transform .18s ease;
}
[data-testid="stSidebar"] a:hover {
    background: rgba(255,255,255,.085);
    color: #FFFFFF;
    transform: translateX(2px);
}
[data-testid="stSidebar"] a[aria-current="page"] {
    background: rgba(169, 209, 195, .16);
    border-left: 3px solid #A9D1C3;
    border-radius: 8px;
    color: #FFFFFF;
}
[data-testid="stSidebar"] [data-baseweb="select"] * {
    color: var(--sp-navy) !important;
}
.sp-brand {
    color: #FFFFFF !important;
    font-size: 28px;
    font-weight: 780;
    letter-spacing: -1.3px;
    line-height: 1.12;
}
.sp-brand i {
    color: #A9D1C3;
    font-style: normal;
}
.sp-tag {
    color: #B7C8CF !important;
    font-size: 11px;
    line-height: 1.7;
    letter-spacing: .25px;
    margin-top: 9px;
}

/* Page hierarchy */
.sp-h1 {
    color: var(--sp-navy);
    font-size: clamp(29px, 3vw, 36px);
    font-weight: 780;
    letter-spacing: -1.35px;
    line-height: 1.16;
    margin: 0 0 10px;
}
.sp-sub {
    color: var(--sp-muted);
    font-size: 14px;
    line-height: 1.75;
    margin: 0 0 29px;
    max-width: 900px;
}
.sp-eyebrow {
    color: var(--sp-sage-dark);
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 1.55px;
    text-transform: uppercase;
    margin-bottom: 10px;
}

/* Cards and containers */
.sp-card {
    background: var(--sp-white);
    border: 1px solid var(--sp-border);
    border-radius: 15px;
    padding: 23px 25px;
    margin-bottom: 17px;
    box-shadow: var(--sp-shadow);
    transition: border-color .18s ease, box-shadow .18s ease, transform .18s ease;
}
.sp-card:hover {
    border-color: #CFDDD6;
    box-shadow: 0 12px 32px rgba(20, 43, 59, .075);
    transform: translateY(-1px);
}
.sp-card h4 {
    color: var(--sp-navy);
    font-size: 16px;
    font-weight: 740;
    letter-spacing: -.25px;
    margin: 0 0 9px;
}
.sp-card p {
    color: var(--sp-muted);
    line-height: 1.7;
}
[data-testid="stVerticalBlockBorderWrapper"] {
    border-color: var(--sp-border);
    border-radius: 15px;
    background: rgba(255,255,255,.82);
    box-shadow: 0 4px 18px rgba(20, 43, 59, .035);
}

/* KPI metrics */
div[data-testid="stMetric"] {
    background: linear-gradient(160deg, #FFFFFF 0%, #FBFCFA 100%);
    border: 1px solid var(--sp-border);
    border-radius: 15px;
    padding: 19px 20px;
    min-height: 112px;
    box-shadow: var(--sp-shadow);
}
div[data-testid="stMetricLabel"] {
    color: var(--sp-muted);
    font-size: 11px;
    font-weight: 650;
    letter-spacing: .02em;
}
div[data-testid="stMetricValue"] {
    color: var(--sp-navy);
    font-size: clamp(22px, 2vw, 29px);
    font-weight: 790;
    letter-spacing: -.85px;
}
div[data-testid="stMetricDelta"] {
    font-size: 11px;
    font-weight: 650;
}

/* Buttons */
.stButton > button,
.stDownloadButton > button,
[data-testid="stFormSubmitButton"] > button {
    min-height: 42px;
    border-radius: 9px;
    font-weight: 680;
    letter-spacing: -.01em;
    transition: transform .16s ease, box-shadow .16s ease, background .16s ease;
}
.stButton > button[kind="primary"],
[data-testid="stFormSubmitButton"] > button[kind="primary"] {
    background: var(--sp-navy);
    border: 1px solid var(--sp-navy);
    color: #FFFFFF;
    box-shadow: 0 4px 12px rgba(20, 43, 59, .12);
}
.stButton > button[kind="primary"]:hover,
[data-testid="stFormSubmitButton"] > button[kind="primary"]:hover {
    background: var(--sp-navy-light);
    border-color: var(--sp-navy-light);
    color: #FFFFFF;
    transform: translateY(-1px);
    box-shadow: 0 7px 16px rgba(20, 43, 59, .16);
}
.stButton > button[kind="secondary"]:hover,
.stDownloadButton > button:hover {
    border-color: var(--sp-sage-dark);
    color: var(--sp-navy);
    transform: translateY(-1px);
}

/* Inputs */
.stTextInput input,
.stTextArea textarea,
.stNumberInput input,
[data-baseweb="select"] > div {
    background: #FFFFFF;
    border: 1px solid #DCE4DF;
    border-radius: 9px;
    color: var(--sp-text);
}
.stTextInput input:focus,
.stTextArea textarea:focus,
.stNumberInput input:focus {
    border-color: var(--sp-sage-dark);
    box-shadow: 0 0 0 3px rgba(71, 121, 107, .12);
}
[data-baseweb="select"] > div {
    min-height: 42px;
}
label, [data-testid="stWidgetLabel"] p {
    color: #40535D;
    font-weight: 620;
}

/* Tabs */
.stTabs [data-baseweb="tab"] {
    color: var(--sp-muted);
    font-weight: 650;
}
.stTabs [aria-selected="true"] {
    color: var(--sp-navy);
}
.stTabs [data-baseweb="tab-highlight"] {
    background: var(--sp-sage-dark);
}

/* Data tables */
[data-testid="stDataFrame"],
[data-testid="stTable"] {
    border: 1px solid var(--sp-border);
    border-radius: 12px;
    overflow: hidden;
}
[data-testid="stDataFrame"] {
    background: #FFFFFF;
}

/* Feedback, expanders and dividers */
[data-testid="stAlert"] {
    border-radius: 11px;
    border-width: 1px;
}
[data-testid="stExpander"] {
    background: #FFFFFF;
    border: 1px solid var(--sp-border);
    border-radius: 11px;
}
hr {
    border-color: var(--sp-border);
}

/* Responsive layout */
@media (max-width: 900px) {
    .block-container {
        padding: 1.5rem 1.15rem 3rem;
    }
}
@media (max-width: 768px) {
    .block-container {
        padding: 1.2rem .9rem 2.5rem;
    }
    .sp-h1 {
        font-size: 27px;
    }
    .sp-sub {
        font-size: 13px;
        margin-bottom: 21px;
    }
    .sp-card {
        padding: 17px;
        border-radius: 12px;
    }
    div[data-testid="stMetric"] {
        padding: 14px;
        min-height: 96px;
    }
    div[data-testid="stMetricValue"] {
        font-size: 21px;
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
