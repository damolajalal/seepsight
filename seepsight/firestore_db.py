
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

def test_firestore_connection():
    """Verify that the app can communicate with Firestore."""

    client = get_firestore_client()

    test_ref = (
        client.collection("_system")
        .document("connection_test")
    )

    test_ref.set({
        "status": "connected",
        "purpose": "temporary_connection_test",
    })

    snapshot = test_ref.get()

    if not snapshot.exists:
        raise RuntimeError("Firestore test document could not be read.")

    test_ref.delete()

    return True
