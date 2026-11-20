"""Seepsight company authentication using Firebase Authentication."""

import requests
import streamlit as st

TIMEOUT = 20
BASE_URL = "https://identitytoolkit.googleapis.com/v1/accounts"


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

    url = f"{BASE_URL}:{endpoint}?key={key}"

    try:
        response = requests.post(
            url,
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
    return errors.get(message, f"Authentication error: {message}")


def _send_verification(id_token):
    return _request(
        "sendOobCode",
        {
            "requestType": "VERIFY_EMAIL",
            "idToken": id_token,
        },
    )


def _get_user(id_token):
    result = _request(
        "lookup",
        {"idToken": id_token},
    )

    if result and result.get("users"):
        return result["users"][0]

    return None


def _register():
    st.subheader("Register your company")

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

    # Store the company name as the Firebase account display name.
    _request(
        "update",
        {
            "idToken": account["idToken"],
            "displayName": company_name,
            "returnSecureToken": True,
        },
    )

    verification = _send_verification(account["idToken"])

    if verification:
        st.success(
            "Your account has been created. Check your email and verify "
            "your address before signing in."
        )
        st.info("If the message is not in your inbox, check your spam folder.")
    else:
        st.warning(
            "Your account was created, but the verification email could not "
            "be sent. Try signing in later to request another verification email."
        )


def _login():
    st.subheader("Company sign in")

    with st.form("company_login"):
        email = st.text_input("Company email")
        password = st.text_input("Password", type="password")

        submitted = st.form_submit_button(
            "Sign in",
            use_container_width=True,
        )

    if not submitted:
        return

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
        st.warning("Please verify your email address before signing in.")

        if st.button("Resend verification email"):
            result = _send_verification(account["idToken"])
            if result:
                st.success("A new verification email has been sent.")
        return

    st.session_state["seepsight_auth"] = {
        "uid": user["localId"],
        "email": user["email"],
        "company_name": user.get("displayName", "Company"),
        "id_token": account["idToken"],
        "refresh_token": account["refreshToken"],
    }

    st.rerun()


def _password_reset():
    st.subheader("Reset your password")

    with st.form("password_reset"):
        email = st.text_input("Company email")
        submitted = st.form_submit_button("Send reset email")

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
            st.success("If the account exists, a password reset email has been sent.")


def logout():
    st.session_state.pop("seepsight_auth", None)
    st.rerun()


def require_auth():
    """Display authentication screens and return True for verified users."""

    account = st.session_state.get("seepsight_auth")

    if account:
        st.sidebar.markdown("---")
        st.sidebar.caption("SIGNED IN AS")
        st.sidebar.write(account["company_name"])
        st.sidebar.caption(account["email"])

        if st.sidebar.button("Sign out", use_container_width=True):
            logout()

        return True

    st.title("Seepsight")
    st.caption("See the gaps. Show the impact. Act with confidence.")

    st.markdown("### Secure company access")

    login_tab, register_tab, reset_tab = st.tabs(
        ["Sign in", "Register company", "Forgot password"]
    )

    with login_tab:
        _login()

    with register_tab:
        _register()

    with reset_tab:
        _password_reset()

    return False
