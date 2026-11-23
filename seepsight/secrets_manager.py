"""Google Secret Manager access for external connection credentials.

Only Secret Manager resource references belong in app configuration/session state.
Secret payloads are fetched server-side and are never returned to UI helpers.
"""

import json
import re

_SECRET_RESOURCE = re.compile(
    r"^projects/[A-Za-z0-9._:-]+/secrets/[A-Za-z0-9_-]+/versions/(?:latest|[1-9][0-9]*)$"
)


def validate_secret_reference(reference):
    if not isinstance(reference, str) or not _SECRET_RESOURCE.fullmatch(reference.strip()):
        raise ValueError("A valid Secret Manager secret-version resource is required.")
    return reference.strip()


def access_secret_json(reference):
    """Fetch a JSON credential payload using the runtime's ADC identity."""
    resource = validate_secret_reference(reference)
    try:
        from google.cloud import secretmanager
    except ImportError as exc:
        raise RuntimeError(
            "Secret Manager support is not installed. Install the optional connector requirements."
        ) from exc

    try:
        client = secretmanager.SecretManagerServiceClient()
        response = client.access_secret_version(request={"name": resource})
        payload = response.payload.data.decode("utf-8")
        value = json.loads(payload)
        if not isinstance(value, dict):
            raise ValueError("Secret payload must be a JSON object.")
        return value
    except Exception as exc:
        raise RuntimeError(
            "The configured connection secret could not be accessed."
        ) from exc
