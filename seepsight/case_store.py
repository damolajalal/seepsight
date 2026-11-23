"""Durable, company-scoped case state and append-only activity history."""

from datetime import datetime, timezone

from firebase_admin import firestore

from seepsight import firestore_db


def get_company_cases(company_id):
    """Return case state and ordered history for the verified company."""
    company = firestore_db._company_ref(company_id)
    cases = {}
    query = company.collection("cases").order_by("__name__")
    for snapshot in firestore_db._stream_query_pages(query, page_size=200):
        data = snapshot.to_dict() or {}
        history_query = (
            snapshot.reference.collection("history")
            .order_by("event_number")
        )
        history = [
            (event.to_dict() or {}).get("message", "")
            for event in firestore_db._stream_query_pages(
                history_query, page_size=200
            )
        ]
        expected_count = data.get("history_count")
        if expected_count is not None and len(history) != int(expected_count):
            raise RuntimeError("Case activity history is incomplete; refresh or contact support.")
        cases[snapshot.id] = {
            "status": data.get("status", "Open"),
            "owner": data.get("owner", ""),
            "note": data.get("note", ""),
            "history": history,
        }
    firestore_db.write_company_audit_event(
        company_id, "cases.listed", "case", None,
        {"case_count": len(cases)},
    )
    return cases


def save_company_case(company_id, case_id, case):
    """Transactionally save case state and append-only activity events."""
    case_id = firestore_db._validate_id(case_id, "case_id")
    if not isinstance(case, dict):
        raise TypeError("case must be a dictionary.")

    status = case.get("status", "Open")
    if status not in {"Open", "Investigating", "Resolved"}:
        raise ValueError("Invalid case status.")
    owner = case.get("owner", "")
    note = case.get("note", "")
    history = case.get("history", [])
    if not isinstance(owner, str) or not isinstance(note, str):
        raise TypeError("Case owner and note must be strings.")
    if not isinstance(history, list) or not all(
        isinstance(item, str) for item in history
    ):
        raise TypeError("Case history must be a list of strings.")

    company = firestore_db._company_ref(company_id)
    case_ref = company.collection("cases").document(case_id)
    transaction = firestore_db.get_firestore_client().transaction()

    @firestore.transactional
    def _save(transaction):
        existing = case_ref.get(transaction=transaction)
        previous_count = int(
            (existing.to_dict() or {}).get("history_count", 0)
        ) if existing.exists else 0

        if len(history) < previous_count:
            raise ValueError("Case history cannot be shortened.")
        if len(history) > previous_count + 450:
            raise ValueError("A single case update cannot append more than 450 history events.")

        for index in range(previous_count, len(history)):
            event_ref = case_ref.collection("history").document(
                f"event_{index:012d}"
            )
            transaction.set(event_ref, {
                "event_number": index,
                "message": history[index],
                "created_at": datetime.now(timezone.utc),
            })

        transaction.set(case_ref, {
            "status": status,
            "owner": owner,
            "note": note,
            "history_count": len(history),
            "updated_at": datetime.now(timezone.utc),
        }, merge=True)

    _save(transaction)
    firestore_db.write_company_audit_event(
        company_id, "case.updated", "case", case_id,
        {"status": status, "history_count": len(history)},
    )
    return True
