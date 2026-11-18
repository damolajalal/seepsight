"""Look and feel: colours, chips, page headers. Red = problem, amber = needs attention, green = good, blue = normal."""
import streamlit as st

RED, AMBER, GREEN, BLUE = "#c0392b", "#d97706", "#15803d", "#1d6fb8"
KIND = {"red": (RED, "#fdeceb"), "amber": (AMBER, "#fff3df"), "green": (GREEN, "#e6f5ea"), "blue": (BLUE, "#e6f0fa")}
SEV_KIND = {"High": "red", "Medium": "amber", "Low": "blue"}
SEV_LABEL = {"High": "High priority", "Medium": "Medium priority", "Low": "Low priority"}
STATUS_KIND = {"Open": "amber", "Investigating": "blue", "Resolved": "green"}

CSS = """
html, body, [data-testid="stApp"]{background:#f6f8fa}
.block-container{padding-top:2rem;max-width:1200px}
[data-testid="stSidebar"]{background:#0f1b2d}
[data-testid="stSidebar"] a, [data-testid="stSidebar"] p, [data-testid="stSidebar"] label, [data-testid="stSidebar"] span{color:#dbe5f1 !important}
[data-testid="stSidebar"] [data-baseweb="select"] *{color:#0f1b2d !important}
[data-testid="stSidebar"] a[aria-current="page"]{background:#1b3553;border-radius:8px}
.sp-h1{color:#0f1b2d;font-size:28px;font-weight:700;margin:0 0 4px}
.sp-sub{color:#5f6e80;margin:0 0 18px;font-size:15px}
.sp-card{background:#fff;border:1px solid #e0e5ec;border-radius:14px;padding:16px 18px;margin-bottom:12px}
.sp-card h4{margin:0 0 6px;color:#0f1b2d;font-size:16px}
.sp-brand{font-size:22px;font-weight:700;color:#fff !important}.sp-brand i{color:#3fc2ae;font-style:normal}
.sp-tag{font-size:12px;color:#9fb3c8 !important}
div[data-testid="stMetric"]{background:#fff;border:1px solid #e0e5ec;border-radius:14px;padding:14px 16px}
"""


def inject_css():
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)


def chip(text, kind="blue"):
    fg, bg = KIND[kind]
    return (f'<span style="background:{bg};color:{fg};padding:2px 10px;border-radius:99px;font-size:12px;'
            f'font-weight:600;border:1px solid {fg}44">{text}</span>')


def money(cur, v):
    return f"{cur} {v:,.0f}"


def page_header(title, sub=""):
    st.markdown(f"<h1 class='sp-h1'>{title}</h1><p class='sp-sub'>{sub}</p>", unsafe_allow_html=True)


def card(html):
    st.markdown(f"<div class='sp-card'>{html}</div>", unsafe_allow_html=True)


def sidebar_header():
    from seepsight import workspace
    with st.sidebar:
        st.markdown("<div class='sp-brand'>Seep<i>sight</i></div><div class='sp-tag'>See the gaps. Show the impact. "
                    "Act with confidence.</div>", unsafe_allow_html=True)
        st.write("")
        workspace.workspace_picker()
