"""Tests for Apple identity-token verification.

This is the security-critical half of Sign in with Apple. The token arrives
from the client, which means it arrives from whoever is holding the phone --
so every check that makes it trustworthy has to actually run. If signature,
audience, issuer or expiry verification is skipped or misconfigured, the
endpoint stops being authentication and becomes "tell me who you'd like to
be", and nothing about the happy path would look different.

So these tests mint real RS256 tokens with a throwaway keypair and assert
that valid ones pass and each individually-broken one does not.

Extracted from server.py the same way the email-template tests are, because
server.py reads os.environ['MONGO_URL'] at import time.
"""

import json
import pathlib
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

APPLE_CLIENT_ID = "com.chintan.app"
ISSUER = "https://appleid.apple.com"
KID = "test-key-1"


@pytest.fixture(scope="module")
def keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key, key.public_key()


@pytest.fixture(scope="module")
def jwk(keypair):
    _, public = keypair
    return json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(public)) | {"kid": KID, "alg": "RS256"}


def mint(keypair, **overrides):
    private, _ = keypair
    claims = {
        "iss": ISSUER,
        "aud": APPLE_CLIENT_ID,
        "sub": "001234.abcdef.0000",
        "email": "someone@privaterelay.appleid.com",
        "is_private_email": True,
        "exp": int(time.time()) + 600,
        "iat": int(time.time()),
    }
    claims.update(overrides)
    return jwt.encode(claims, private, algorithm="RS256", headers={"kid": KID})


def load_verifier(monkeypatch, jwk):
    """Exec the verification helpers out of server.py against a stub JWKS."""
    src = pathlib.Path(__file__).parent.parent / "server.py"
    text = src.read_text(encoding="utf-8")
    start = text.index("async def _verify_apple_identity_token(")
    end = text.index('@api_router.post("/auth/apple")')

    ns = {
        "jwt": jwt, "json": json, "logger": _NullLogger(),
        "APPLE_CLIENT_ID": APPLE_CLIENT_ID, "_APPLE_ISSUER": ISSUER,
        "HTTPException": _HTTPError,
    }

    async def _apple_public_keys(force: bool = False):
        return [jwk]

    ns["_apple_public_keys"] = _apple_public_keys
    exec(text[start:end], ns)
    return ns["_verify_apple_identity_token"]


class _HTTPError(Exception):
    def __init__(self, status_code=401, detail=""):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class _NullLogger:
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass
    def info(self, *a, **k): pass


@pytest.mark.asyncio
async def test_valid_token_is_accepted(monkeypatch, keypair, jwk):
    verify = load_verifier(monkeypatch, jwk)
    claims = await verify(mint(keypair))
    assert claims["sub"] == "001234.abcdef.0000"
    assert claims["is_private_email"] is True


@pytest.mark.asyncio
async def test_token_signed_by_a_different_key_is_rejected(monkeypatch, keypair, jwk):
    """The whole point: a token the caller signed themselves must not work."""
    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(
        {"iss": ISSUER, "aud": APPLE_CLIENT_ID, "sub": "attacker",
         "exp": int(time.time()) + 600},
        attacker, algorithm="RS256", headers={"kid": KID},
    )
    verify = load_verifier(monkeypatch, jwk)
    with pytest.raises(_HTTPError):
        await verify(forged)


@pytest.mark.asyncio
async def test_token_for_another_app_is_rejected(monkeypatch, keypair, jwk):
    """A genuine Apple token issued to a DIFFERENT app is still a real,
    Apple-signed token -- only the audience check stops it."""
    verify = load_verifier(monkeypatch, jwk)
    with pytest.raises(_HTTPError) as e:
        await verify(mint(keypair, aud="com.someone.else"))
    assert "different app" in e.value.detail


@pytest.mark.asyncio
async def test_expired_token_is_rejected(monkeypatch, keypair, jwk):
    verify = load_verifier(monkeypatch, jwk)
    with pytest.raises(_HTTPError) as e:
        await verify(mint(keypair, exp=int(time.time()) - 60))
    assert "expired" in e.value.detail.lower()


@pytest.mark.asyncio
async def test_token_from_a_different_issuer_is_rejected(monkeypatch, keypair, jwk):
    verify = load_verifier(monkeypatch, jwk)
    with pytest.raises(_HTTPError):
        await verify(mint(keypair, iss="https://evil.example.com"))


@pytest.mark.asyncio
async def test_garbage_token_is_rejected_without_crashing(monkeypatch, keypair, jwk):
    verify = load_verifier(monkeypatch, jwk)
    with pytest.raises(_HTTPError) as e:
        await verify("not-a-jwt")
    assert e.value.status_code == 401


@pytest.mark.asyncio
async def test_unknown_key_id_is_rejected(monkeypatch, keypair, jwk):
    """Apple rotates keys; an unknown kid must fail closed, not open."""
    private, _ = keypair
    token = jwt.encode(
        {"iss": ISSUER, "aud": APPLE_CLIENT_ID, "sub": "x", "exp": int(time.time()) + 600},
        private, algorithm="RS256", headers={"kid": "some-other-kid"},
    )
    verify = load_verifier(monkeypatch, jwk)
    with pytest.raises(_HTTPError) as e:
        await verify(token)
    assert "signing key" in e.value.detail.lower()
