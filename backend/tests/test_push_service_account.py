"""FIREBASE_SERVICE_ACCOUNT parsing survives the usual Railway paste damage and
explains what's wrong otherwise (never echoing the key). Uses a throwaway
locally generated RSA key."""

import base64
import json

import pytest

pytest.importorskip("google.oauth2")
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402

from push_service import parse_service_account  # noqa: E402

PEM = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
ACCOUNT = {"type": "service_account", "project_id": "chintan-test", "private_key_id": "abc",
           "private_key": PEM, "client_email": "firebase-adminsdk@chintan-test.iam.gserviceaccount.com",
           "token_uri": "https://oauth2.googleapis.com/token"}
GOOD = json.dumps(ACCOUNT, indent=2)


@pytest.mark.parametrize("raw", [
    GOOD,                                                   # as downloaded
    json.dumps(ACCOUNT),                                    # one line
    "'" + GOOD + "'",                                       # wrapped in quotes
    base64.b64encode(GOOD.encode()).decode(),               # base64
    GOOD.replace("\\n", "\n"),                              # \n escapes became real newlines
    json.dumps(json.dumps(ACCOUNT)),                        # JSON pasted as a JSON string
    json.dumps({**ACCOUNT, "private_key": PEM.replace("\n", "\\n")}),   # double-escaped key
])
def test_accepts_common_pastes(raw):
    data, problem = parse_service_account(raw)
    assert problem is None and data["project_id"] == "chintan-test"


@pytest.mark.parametrize("raw,needle", [
    ("", "isn't set"),
    ("not json at all", "isn't JSON"),
    ("{ broken", "couldn't be read"),
    (json.dumps({"project_info": {}, "client": []}), "google-services.json"),
    (json.dumps({**ACCOUNT, "client_email": ""}), "missing client_email"),
    (json.dumps({**ACCOUNT, "private_key": "-----BEGIN PRIVATE KEY-----\nnope\n-----END PRIVATE KEY-----\n"}),
     "couldn't be loaded"),
])
def test_explains_problems_without_leaking(raw, needle):
    data, problem = parse_service_account(raw)
    assert data is None and needle in problem
    assert "BEGIN PRIVATE KEY" not in problem and PEM[40:80] not in problem
