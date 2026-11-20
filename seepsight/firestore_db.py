
"""Secure server-side connection to Firebase Cloud Firestore."""

import streamlit as st


def get_firestore_client():
    """Return an authenticated Firestore client."""

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except ImportError as exc:
        raise RuntimeError(
            "Firebase Admin SDK is missing. "
            "Install firebase-admin from requirements.txt."
        ) from exc

    try:
        app = firebase_admin.get_app()

    except ValueError:
        if "firebase_admin" not in st.secrets:
            raise RuntimeError(
                "Firebase Admin credentials are missing from "
                "Streamlit Secrets."
            )

        service_account_info = dict(st.secrets["firebase_admin"])
        credential = credentials.Certificate(service_account_info)

        app = firebase_admin.initialize_app(credential)

    return firestore.client(app=app)
