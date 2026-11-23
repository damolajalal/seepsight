"""Private, company-scoped Google Cloud Storage for original uploads."""
import mimetypes
import os
import re
from datetime import datetime, timezone
from pathlib import PurePath

ALLOWED_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls", ".json"}
DEFAULT_MAX_BYTES = 50 * 1024 * 1024
_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _valid_id(value, label):
    if not isinstance(value, str) or not _ID_PATTERN.fullmatch(value):
        raise ValueError(f"{label} is invalid.")
    return value


def _bucket_name():
    name = os.environ.get("SEEPSIGHT_UPLOADS_BUCKET", "").strip()
    if not name:
        try:
            import streamlit as st
            name = str(st.secrets.get("gcp", {}).get("uploads_bucket", "")).strip()
        except Exception:
            name = ""
    if not name:
        raise RuntimeError("Private upload storage is not configured. Set SEEPSIGHT_UPLOADS_BUCKET or [gcp].uploads_bucket in Streamlit Secrets.")
    return name


def _client():
    try:
        from google.cloud import storage
    except ImportError as exc:
        raise RuntimeError("Google Cloud Storage support is missing. Install google-cloud-storage.") from exc
    return storage.Client()


def _object_name(company_id, upload_id, filename):
    company_id = _valid_id(company_id, "company_id")
    upload_id = _valid_id(upload_id, "upload_id")
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError("A filename is required.")
    safe_name = PurePath(filename.replace("\\", "/")).name.strip()
    if safe_name in {"", ".", ".."} or len(safe_name) > 180:
        raise ValueError("The filename is invalid.")
    if any(ord(char) < 32 for char in safe_name):
        raise ValueError("The filename contains unsupported characters.")
    if PurePath(safe_name).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError("This file type is not supported.")
    return f"companies/{company_id}/uploads/{upload_id}/{safe_name}", safe_name


def upload_company_file(company_id, upload_id, filename, data, content_type=None):
    """Create a new private object and refuse to overwrite existing objects."""
    from seepsight.firestore_db import verify_company_access
    verify_company_access(company_id)
    object_name, safe_name = _object_name(company_id, upload_id, filename)
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("Upload data must be bytes.")
    payload = bytes(data)
    try:
        max_bytes = int(os.environ.get("SEEPSIGHT_MAX_UPLOAD_BYTES", DEFAULT_MAX_BYTES))
    except ValueError:
        max_bytes = DEFAULT_MAX_BYTES
    if max_bytes < 1 or len(payload) > max_bytes:
        raise ValueError(f"File exceeds the configured upload limit ({max_bytes} bytes).")
    if not payload:
        raise ValueError("The uploaded file is empty.")
    bucket = _client().bucket(_bucket_name())
    blob = bucket.blob(object_name)
    mime = content_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    try:
        blob.upload_from_string(payload, content_type=mime, if_generation_match=0, checksum="auto")
        blob.reload()
    except Exception as exc:
        raise RuntimeError("The file could not be saved to private cloud storage.") from exc
    return {
        "storage_provider": "gcs",
        "bucket": bucket.name,
        "object_name": object_name,
        "generation": str(blob.generation) if blob.generation is not None else None,
        "size_bytes": int(blob.size or len(payload)),
        "content_type": blob.content_type or mime,
        "crc32c": blob.crc32c,
        "md5_hash": blob.md5_hash,
        "uploaded_at": datetime.now(timezone.utc),
        "original_filename": safe_name,
        "private": True,
    }


def _validate_company_object(company_id, object_name):
    company_id = _valid_id(company_id, "company_id")
    prefix = f"companies/{company_id}/uploads/"
    if not isinstance(object_name, str) or not object_name.startswith(prefix):
        raise PermissionError("The requested file is outside this company workspace.")
    parts = object_name.split("/")
    if len(parts) != 5 or not _ID_PATTERN.fullmatch(parts[3]):
        raise ValueError("The stored object path is invalid.")
    _object_name(company_id, parts[3], parts[4])
    return object_name


def download_company_file(company_id, object_name):
    """Download only an object within the authenticated company's namespace."""
    from seepsight.firestore_db import verify_company_access
    verify_company_access(company_id)
    object_name = _validate_company_object(company_id, object_name)
    try:
        return _client().bucket(_bucket_name()).blob(object_name).download_as_bytes()
    except Exception as exc:
        raise RuntimeError("The stored file could not be retrieved.") from exc


def delete_company_file(company_id, object_name, if_generation_match=None):
    """Delete only an object within the authenticated company's namespace."""
    from seepsight.firestore_db import verify_company_access
    verify_company_access(company_id)
    object_name = _validate_company_object(company_id, object_name)
    try:
        blob = _client().bucket(_bucket_name()).blob(object_name)
        kwargs = {}
        if if_generation_match is not None:
            kwargs["if_generation_match"] = int(if_generation_match)
        blob.delete(**kwargs)
        return True
    except Exception as exc:
        raise RuntimeError("The stored file could not be deleted.") from exc
