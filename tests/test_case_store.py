"""Focused tests for durable, company-scoped case history."""

import unittest
from unittest.mock import MagicMock, patch

from seepsight import case_store


class CaseStoreTests(unittest.TestCase):
    def setUp(self):
        self.company = MagicMock()
        self.case_ref = MagicMock()
        self.company.collection.return_value.document.return_value = self.case_ref
        self.case_ref.get.return_value.exists = True
        self.case_ref.get.return_value.to_dict.return_value = {"history_count": 1}
        self.history = MagicMock()
        self.case_ref.collection.return_value = self.history
        self.transaction = MagicMock()
        self.client = MagicMock()
        self.client.transaction.return_value = self.transaction
        self.client_patch = patch.object(
            case_store.firestore_db, "get_firestore_client", return_value=self.client
        )
        self.client_patch.start()
        self.addCleanup(self.client_patch.stop)
        self.transactional_patch = patch.object(
            case_store.firestore, "transactional",
            side_effect=lambda function: (lambda transaction: function(transaction)),
        )
        self.transactional_patch.start()
        self.addCleanup(self.transactional_patch.stop)
        self.audit_patch = patch.object(
            case_store.firestore_db, "write_company_audit_event", return_value="audit-id"
        )
        self.audit_patch.start()
        self.addCleanup(self.audit_patch.stop)
        self.event_refs = {}

        def event_document(event_id):
            ref = self.event_refs.setdefault(event_id, MagicMock())
            return ref

        self.history.document.side_effect = event_document
        self.company_patch = patch.object(
            case_store.firestore_db, "_company_ref", return_value=self.company
        )
        self.company_patch.start()
        self.addCleanup(self.company_patch.stop)

    def test_save_appends_only_events_after_persisted_count(self):
        result = case_store.save_company_case(
            "company-a",
            "finding-1",
            {
                "status": "Investigating",
                "owner": "Analyst",
                "note": "Checking invoice",
                "history": ["Case opened", "Invoice requested", "Invoice received"],
            },
        )

        self.assertTrue(result)
        self.assertEqual(self.history.document.call_count, 2)
        self.assertEqual(self.transaction.set.call_count, 3)
        self.assertEqual(
            self.transaction.set.call_args_list[0].args[0],
            self.event_refs["event_000000000001"],
        )
        self.assertEqual(
            self.transaction.set.call_args_list[1].args[0],
            self.event_refs["event_000000000002"],
        )
        saved_state = self.transaction.set.call_args_list[-1].args[1]
        self.assertEqual(saved_state["history_count"], 3)
        self.assertEqual(saved_state["status"], "Investigating")

    def test_save_rejects_shortened_history(self):
        self.case_ref.get.return_value.to_dict.return_value = {"history_count": 2}
        with self.assertRaisesRegex(ValueError, "cannot be shortened"):
            case_store.save_company_case(
                "company-a", "finding-1", {"history": ["Case opened", "Follow-up"]}
            )
        self.history.document.assert_not_called()
        self.transaction.set.assert_not_called()

    def test_save_rejects_invalid_status(self):
        with self.assertRaisesRegex(ValueError, "Invalid case status"):
            case_store.save_company_case(
                "company-a", "finding-1",
                {"status": "Archived", "history": ["Opened"]},
            )

    def test_save_rejects_non_string_history_entries(self):
        with self.assertRaisesRegex(TypeError, "list of strings"):
            case_store.save_company_case(
                "company-a", "finding-1", {"history": ["Opened", 3]}
            )

    def test_company_reference_is_requested_before_case_access(self):
        case_store.save_company_case(
            "company-a", "finding-1", {"history": ["Case opened"]}
        )
        case_store.firestore_db._company_ref.assert_called_once_with("company-a")
        self.assertEqual(self.transaction.set.call_count, 2)


if __name__ == "__main__":
    unittest.main()
