"""Unit tests for company-scoped upload path validation."""
import unittest
from unittest.mock import MagicMock, patch

from seepsight import cloud_storage, firestore_db


class CloudStorageValidationTests(unittest.TestCase):
    def test_company_scoped_path(self):
        path, name = cloud_storage._object_name("company_1", "upload-1", "orders.csv")
        self.assertEqual(path, "companies/company_1/uploads/upload-1/orders.csv")
        self.assertEqual(name, "orders.csv")

    def test_traversal_filename_is_reduced_to_basename(self):
        path, _ = cloud_storage._object_name("company_1", "upload-1", "../../orders.csv")
        self.assertEqual(path, "companies/company_1/uploads/upload-1/orders.csv")

    def test_unsupported_extension_rejected(self):
        with self.assertRaises(ValueError):
            cloud_storage._object_name("company_1", "upload-1", "payload.exe")

    def test_invalid_company_rejected(self):
        with self.assertRaises(ValueError):
            cloud_storage._object_name("../other", "upload-1", "orders.csv")

    def test_cross_company_download_rejected_before_cloud_access(self):
        with patch.object(firestore_db, "verify_company_access", return_value={"company_id": "company_1"}):
            with patch.object(cloud_storage, "_client") as client:
                with self.assertRaises(PermissionError):
                    cloud_storage.download_company_file("company_1", "companies/company_2/uploads/id/orders.csv")
                client.assert_not_called()

    def test_upload_is_create_only(self):
        blob = MagicMock(generation=7, size=12, content_type="text/csv")
        bucket = MagicMock(name="private-bucket")
        bucket.name = "private-bucket"
        bucket.blob.return_value = blob
        client = MagicMock()
        client.bucket.return_value = bucket
        with patch.dict("os.environ", {"SEEPSIGHT_UPLOADS_BUCKET": "private-bucket"}):
            with patch.object(firestore_db, "verify_company_access", return_value={"company_id": "company_1"}):
                with patch.object(cloud_storage, "_client", return_value=client):
                    meta = cloud_storage.upload_company_file("company_1", "upload-1", "orders.csv", b"a,b\n1,2\n")
        self.assertTrue(meta["private"])
        self.assertEqual(meta["object_name"], "companies/company_1/uploads/upload-1/orders.csv")
        self.assertEqual(blob.upload_from_string.call_args.kwargs["if_generation_match"], 0)


if __name__ == "__main__":
    unittest.main()
