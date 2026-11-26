
"""Seepsight AI-powered procurement intelligence and Firebase authentication."""

import requests
import streamlit as st

from seepsight import company_store

TIMEOUT = 20
BASE_URL = "https://identitytoolkit.googleapis.com/v1/accounts"


# ---------------------------------------------------------
# FIREBASE AUTHENTICATION
# ---------------------------------------------------------

def _api_key():
    try:
        return st.secrets["firebase"]["api_key"]
    except Exception:
        st.error(
            "Firebase is not configured. Add your Firebase API key "
            "to Streamlit secrets before using authentication."
        )
        return None


def _request(endpoint, payload):
    key = _api_key()
    if not key:
        return None

    try:
        response = requests.post(
            f"{BASE_URL}:{endpoint}?key={key}",
            json=payload,
            timeout=TIMEOUT,
        )
        data = response.json()

        if response.ok:
            return data

        message = data.get("error", {}).get("message", "UNKNOWN_ERROR")
        st.error(_friendly_error(message))
        return None

    except requests.RequestException:
        st.error("Unable to contact the authentication service. Please try again.")
        return None
    except ValueError:
        st.error("The authentication service returned an invalid response.")
        return None


def _friendly_error(message):
    errors = {
        "EMAIL_EXISTS": "This email already has an account. Please sign in.",
        "INVALID_EMAIL": "Please enter a valid email address.",
        "WEAK_PASSWORD": "Use a password with at least 6 characters.",
        "INVALID_LOGIN_CREDENTIALS": "Email or password is incorrect.",
        "EMAIL_NOT_FOUND": "No account was found for this email.",
        "USER_DISABLED": "This account has been disabled.",
        "TOO_MANY_ATTEMPTS_TRY_LATER": "Too many attempts. Please try again later.",
        "INVALID_PASSWORD": "Email or password is incorrect.",
        "OPERATION_NOT_ALLOWED": "Email and password sign-in is not enabled in Firebase.",
        "API_KEY_INVALID": "The Firebase API key is invalid.",
    }
    return errors.get(message, "Authentication could not be completed. Please check your details and try again.")


def _send_verification(id_token):
    return _request(
        "sendOobCode",
        {"requestType": "VERIFY_EMAIL", "idToken": id_token},
    )


def _get_user(id_token):
    result = _request("lookup", {"idToken": id_token})

    if result and result.get("users"):
        return result["users"][0]

    return None


def _set_auth_view(view):
    st.session_state["seepsight_auth_view"] = view
    st.rerun()


# ---------------------------------------------------------
# REGISTRATION
# ---------------------------------------------------------

def _register():
    st.subheader("Create your company account")
    st.write(
        "Get started with your company's AI-powered procurement "
        "intelligence workspace."
    )

    with st.form("company_registration"):
        company_name = st.text_input("Company name")
        email = st.text_input("Official company email")
        password = st.text_input("Password", type="password")
        confirm = st.text_input("Confirm password", type="password")

        submitted = st.form_submit_button(
            "Create company account",
            use_container_width=True,
        )

    if not submitted:
        return

    company_name = company_name.strip()
    email = email.strip().lower()

    if not company_name or not email or not password:
        st.warning("Please complete all fields.")
        return

    if password != confirm:
        st.warning("Your passwords do not match.")
        return

    if len(password) < 6:
        st.warning("Your password must contain at least 6 characters.")
        return

    account = _request(
        "signUp",
        {
            "email": email,
            "password": password,
            "returnSecureToken": True,
        },
    )

    if not account:
        return

    update_result = _request(
        "update",
        {
            "idToken": account["idToken"],
            "displayName": company_name,
            "returnSecureToken": True,
        },
    )

    if not update_result:
        st.warning(
            "Your account was created, but the company name could not be saved. "
            "Please contact support before proceeding."
        )
        return

    verification = _send_verification(account["idToken"])

    if verification:
        st.success(
            "Your company account has been created. Check your email "
            "and verify your address before signing in."
        )
        st.info("If the message is not in your inbox, check your spam folder.")
    else:
        st.warning(
            "Your account was created, but the verification email could not "
            "be sent. Please try again or contact support."
        )


# ---------------------------------------------------------
# EMAIL VERIFICATION
# ---------------------------------------------------------

def _resend_pending_verification():
    token = st.session_state.get("seepsight_pending_verification_token")

    if not token:
        return

    if st.button(
        "Resend verification email",
        use_container_width=True,
        key="resend_verification",
    ):
        if _send_verification(token):
            st.success("A new verification email has been sent.")


# ---------------------------------------------------------
# SIGN IN
# ---------------------------------------------------------

def _login():
    st.subheader("Welcome back")
    st.write("Access your company's procurement intelligence workspace.")

    with st.form("company_login"):
        email = st.text_input("Company email")
        password = st.text_input("Password", type="password")

        submitted = st.form_submit_button(
            "Sign in",
            use_container_width=True,
        )

    if submitted:
        account = _request(
            "signInWithPassword",
            {
                "email": email.strip().lower(),
                "password": password,
                "returnSecureToken": True,
            },
        )

        if not account:
            return

        user = _get_user(account["idToken"])

        if not user:
            return

        if not user.get("emailVerified", False):
            st.session_state["seepsight_pending_verification_token"] = (
                account["idToken"]
            )
            st.warning("Please verify your email address before signing in.")
            _resend_pending_verification()
            return

        st.session_state.pop(
            "seepsight_pending_verification_token",
            None,
        )

        try:
            company = company_store.ensure_company_for_user(
                uid=user["localId"],
                email=user["email"],
                company_name=user.get("displayName", "Company"),
            )
        except Exception:
            st.error(
                "Your sign-in succeeded, but your company workspace "
                "could not be loaded. Please try again or contact support."
            )
            return

        st.session_state["seepsight_auth"] = {
            "uid": user["localId"],
            "email": user["email"],
            "company_name": company["company_name"],
            "company_id": company["company_id"],
            "role": company["role"],
            "id_token": account["idToken"],
            "refresh_token": account["refreshToken"],
        }

        st.session_state.pop("seepsight_auth_view", None)
        st.rerun()

    _resend_pending_verification()

    if st.button("Forgot your password?", key="forgot_password_link"):
        _set_auth_view("reset")

    if st.button(
        "Don't have a company account? Create one",
        key="register_from_login",
    ):
        _set_auth_view("register")


# ---------------------------------------------------------
# PASSWORD RESET
# ---------------------------------------------------------

def _password_reset():
    st.subheader("Reset your password")
    st.write("Enter your company email to receive a password reset link.")

    with st.form("password_reset"):
        email = st.text_input("Company email")
        submitted = st.form_submit_button(
            "Send reset email",
            use_container_width=True,
        )

    if submitted:
        if not email.strip():
            st.warning("Enter your company email.")
            return

        result = _request(
            "sendOobCode",
            {
                "requestType": "PASSWORD_RESET",
                "email": email.strip().lower(),
            },
        )

        if result:
            st.success(
                "If the account exists, a password reset email has been sent."
            )


# ---------------------------------------------------------
# PUBLIC LANDING PAGE
# ---------------------------------------------------------

def _public_welcome():

    st.markdown(
        """
        <style>
        .stApp [data-testid="stMainBlockContainer"] {
            max-width: 1160px;
            padding-top: 3.5rem !important;
            padding-bottom: 3rem !important;
        }

        .ss-brand-group {
            display: flex;
            align-items: center;
            gap: 14px;
            min-height: 64px;
        }

        .ss-logo {
            width: 54px;
            height: 54px;
            border-radius: 11px;
            background: #173449;
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 29px;
            font-weight: 800;
            flex-shrink: 0;
        }

        .ss-brand {
            color: #173449;
            font-size: 2.25rem;
            font-weight: 800;
            letter-spacing: -1.3px;
            line-height: 1.2;
        }

        .ss-brand-subtitle {
            color: #A66C3F;
            font-size: 0.68rem;
            font-weight: 750;
            letter-spacing: 2px;
            margin-top: 3px;
        }

        .ss-eyebrow {
            color: #A66C3F;
            font-size: 0.76rem;
            font-weight: 750;
            letter-spacing: 2px;
            text-transform: uppercase;
            margin-bottom: 0.8rem;
        }

        .ss-ai-label {
            display: inline-block;
            color: #173449;
            background: #E7EFEC;
            border: 1px solid #D1E0DA;
            border-radius: 5px;
            padding: 7px 12px;
            font-size: 0.75rem;
            font-weight: 750;
            letter-spacing: 1.2px;
            margin-bottom: 12px;
        }

        .ss-hero {
            font-size: clamp(2.5rem, 5vw, 4.1rem);
            line-height: 1.08;
            letter-spacing: -2px;
            font-weight: 750;
            color: #173449;
            margin: 1rem 0;
        }

        .ss-lead {
            font-size: 1.12rem;
            line-height: 1.8;
            color: #586773;
            max-width: 700px;
        }

        .ss-panel {
            background: #F5F3ED;
            border: 1px solid #E5E0D6;
            border-radius: 14px;
            padding: 1.5rem;
            min-height: 165px;
            box-sizing: border-box;
        }

        .ss-panel h4 {
            color: #173449;
            margin-top: 0.5rem;
            font-size: 1.05rem;
        }

        .ss-panel p {
            color: #64717A;
            line-height: 1.65;
            font-size: 0.92rem;
        }

        .ss-number {
            color: #B5794B;
            font-weight: 750;
            font-size: 0.82rem;
            letter-spacing: 1px;
        }

        .ss-section-intro {
            color: #64717A;
            line-height: 1.7;
            max-width: 760px;
        }

        .ss-highlight {
            background: #173449;
            color: #FFFFFF;
            border-radius: 14px;
            padding: 26px;
        }

        .ss-highlight h3 {
            color: #FFFFFF;
        }

        .ss-highlight p {
            color: #E1E9ED;
            line-height: 1.7;
        }

        @media (max-width: 700px) {
            .ss-brand {
                font-size: 1.7rem;
            }

            .ss-brand-subtitle {
                font-size: 0.55rem;
                letter-spacing: 1.2px;
            }

            .ss-logo {
                width: 46px;
                height: 46px;
                font-size: 24px;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # HEADER
    brand, signin, register = st.columns(
        [3, 1, 1.55],
        vertical_alignment="center",
        gap="small",
    )

    with brand:
        st.markdown(
            """
            <div class="ss-brand-group">
                <div class="ss-logo">S</div>
                <div>
                    <div class="ss-brand">Seepsight</div>
                    <div class="ss-brand-subtitle">
                        AI-POWERED PROCUREMENT INTELLIGENCE
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with signin:
        if st.button(
            "Sign in",
            use_container_width=True,
            key="header_signin",
        ):
            _set_auth_view("signin")

    with register:
        if st.button(
            "Create account",
            type="primary",
            use_container_width=True,
            key="header_register",
        ):
            _set_auth_view("register")

    st.divider()

    # HERO
    left, right = st.columns([1.45, 0.75], gap="large")

    with left:
        st.markdown(
            '<div class="ss-ai-label">'
            '✦ AI-POWERED PROCUREMENT INTELLIGENCE'
            '</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="ss-eyebrow">Intelligence for smarter procurement</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="ss-hero">'
            'See the gaps.<br>'
            'Show the impact.<br>'
            'Act with confidence.'
            '</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="ss-lead">'
            'Seepsight is an AI-powered procurement intelligence platform '
            'that helps businesses uncover potential financial leakages, '
            'identify procurement risks, understand supplier performance '
            'and make more informed purchasing decisions.'
            '</div>',
            unsafe_allow_html=True,
        )

    with right:
        st.markdown(
            """
            <div class="ss-highlight">
                <div class="ss-eyebrow" style="color:#D8AA82;">
                    INTELLIGENT PROCUREMENT
                </div>
                <h3>From procurement data to actionable intelligence.</h3>
                <p>
                    Bring purchasing information into focus. Use intelligent
                    analysis to surface potential issues, understand their
                    impact and support better decisions.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.write("")
    st.divider()

    # AI CAPABILITIES
    st.markdown("## Intelligence behind better procurement decisions")

    st.markdown(
        '<div class="ss-section-intro">'
        'Seepsight brings procurement analytics, intelligent risk detection '
        'and AI-assisted explanations together to help organisations '
        'understand what is happening across their purchasing operations.'
        '</div>',
        unsafe_allow_html=True,
    )

    capabilities = [
        (
            "01",
            "AI-powered procurement intelligence",
            "Turn procurement information into meaningful insights that support better decisions.",
        ),
        (
            "02",
            "Intelligent risk detection",
            "Identify potential price changes, delivery discrepancies and procurement risks.",
        ),
        (
            "03",
            "Financial leakage analysis",
            "Investigate potential financial exposure and understand where purchasing value may be lost.",
        ),
        (
            "04",
            "Supplier intelligence",
            "Examine supplier performance, purchasing patterns and operational concerns.",
        ),
        (
            "05",
            "AI-assisted explanations",
            "Make findings easier to understand through contextual explanations and supporting evidence.",
        ),
        (
            "06",
            "Procurement action management",
            "Prioritise findings, investigate issues and track corrective actions.",
        ),
    ]

    columns = st.columns(3, gap="medium")

    for index, (number, heading, description) in enumerate(capabilities):
        with columns[index % 3]:
            st.markdown(
                f"""
                <div class="ss-panel">
                    <div class="ss-number">{number}</div>
                    <h4>{heading}</h4>
                    <p>{description}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.write("")

    st.divider()

    # WORKFLOW
    st.markdown("## How Seepsight works")

    st.markdown(
        '<div class="ss-section-intro">'
        'A connected approach to understanding procurement activity '
        'and acting on important findings.'
        '</div>',
        unsafe_allow_html=True,
    )

    steps = st.columns(3, gap="large")

    workflow = [
        (
            "01 · CONNECT",
            "Bring your data together",
            "Connect your company's procurement records and prepare them for analysis.",
        ),
        (
            "02 · ANALYSE",
            "Discover what matters",
            "Use procurement analytics and intelligent detection to examine purchasing activity.",
        ),
        (
            "03 · TAKE ACTION",
            "Turn insights into action",
            "Review findings, examine evidence and track corrective actions.",
        ),
    ]

    for column, (number, heading, description) in zip(steps, workflow):
        with column:
            st.caption(number)
            st.subheader(heading)
            st.write(description)

    st.divider()

    # FOOTER
    footer_left, footer_right = st.columns([2, 1])

    with footer_left:
        st.markdown("**Seepsight**")
        st.caption("AI-powered procurement intelligence.")
        st.caption("See the gaps. Show the impact. Act with confidence.")

    with footer_right:
        if st.button(
            "Access your workspace",
            use_container_width=True,
            key="footer_signin",
        ):
            _set_auth_view("signin")


# ---------------------------------------------------------
# AUTHENTICATION ROUTING
# ---------------------------------------------------------

def _authentication_screen():
    view = st.session_state.get("seepsight_auth_view", "welcome")

    if view == "welcome":
        _public_welcome()
        return

    st.markdown("### Seepsight")
    st.caption("AI-powered procurement intelligence.")

    if st.button("← Back to welcome page", key="auth_back"):
        _set_auth_view("welcome")

    st.divider()

    if view == "signin":
        _login()
    elif view == "register":
        _register()
    elif view == "reset":
        _password_reset()
    else:
        _public_welcome()


def _refresh_session_token(refresh_token):
    """Exchange a Firebase refresh token for a fresh ID token."""
    try:
        api_key = st.secrets["firebase"]["api_key"]
    except Exception:
        return None

    try:
        response = requests.post(
            f"https://securetoken.googleapis.com/v1/token?key={api_key}",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=TIMEOUT,
        )
        if not response.ok:
            return None

        data = response.json()
        if not data.get("id_token") or not data.get("refresh_token"):
            return None
        return data
    except (requests.RequestException, ValueError):
        return None


def _verified_account(account):
    """Verify the Firebase identity and re-resolve active company membership."""
    if not isinstance(account, dict):
        return None

    id_token = account.get("id_token")
    refresh_token = account.get("refresh_token")
    if not id_token or not refresh_token:
        return None

    # Ensure the Admin SDK is initialized before token verification.
    try:
        from firebase_admin import auth as firebase_auth
        from seepsight.firestore_db import get_firestore_client

        get_firestore_client()
    except Exception:
        return None

    try:
        claims = firebase_auth.verify_id_token(
            id_token,
            check_revoked=True,
        )
    except Exception:
        refreshed = _refresh_session_token(refresh_token)
        if not refreshed:
            return None

        id_token = refreshed["id_token"]
        refresh_token = refreshed["refresh_token"]
        try:
            claims = firebase_auth.verify_id_token(
                id_token,
                check_revoked=True,
            )
        except Exception:
            return None

    uid = claims.get("uid")
    email = (claims.get("email") or "").strip().lower()
    if not uid or not email or not claims.get("email_verified", False):
        return None

    # Resolve company and role from Firestore on each authenticated rerun.
    # Never trust a company ID or role copied from Streamlit session state.
    try:
        company = company_store.get_company_for_user(uid)
    except Exception:
        return None

    if company.get("uid") != uid:
        return None
    if str(company.get("email") or "").strip().lower() != email:
        return None

    verified = {
        **account,
        "uid": uid,
        "email": email,
        "company_id": company["company_id"],
        "company_name": company["company_name"],
        "role": company["role"],
        "id_token": id_token,
        "refresh_token": refresh_token,
    }
    return verified


def logout():
    st.session_state.pop("seepsight_auth", None)
    st.session_state.pop("mine", None)
    st.session_state.pop("chat", None)
    st.session_state.pop("cases", None)
    st.session_state.pop("seepsight_pending_verification_token", None)
    st.rerun()


def require_auth():
    """Verify identity and active company membership before rendering pages."""

    account = st.session_state.get("seepsight_auth")

    if account:
        verified = _verified_account(account)
        if not verified:
            logout()
            return False

        st.session_state["seepsight_auth"] = verified
        st.sidebar.markdown("---")
        st.sidebar.caption("SIGNED IN AS")
        st.sidebar.write(verified["company_name"])
        st.sidebar.caption(verified["email"])

        _jira_connection_panel(verified)

        if st.sidebar.button("Sign out", use_container_width=True):
            logout()

        return True

    _authentication_screen()
    return False
