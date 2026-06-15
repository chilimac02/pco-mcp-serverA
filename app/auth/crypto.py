"""Fernet symmetric encryption for OAuth tokens at rest.

Keyed by `ENCRYPTION_KEY` in .env. If that env var ever changes after data
is stored, every existing session row becomes unreadable — there is no
recovery path. The .env.example file warns about this explicitly.

Why Fernet (not e.g. AES-GCM directly):
- It's authenticated (HMAC included) — tampered ciphertext fails cleanly
- The library handles IV generation, padding, and key rotation primitives
- A single high-level API: `Fernet(key).encrypt(plaintext) -> ciphertext`
- Ciphertext is base64url-safe; stores fine in a TEXT column

Why a tiny wrapper module instead of using Fernet directly at call sites:
- Centralises the lru_cache on the Fernet instance (parsing the key is cheap
  but not free; instantiating once per process matters under load)
- Gives us a single place to swap in MultiFernet later for key rotation
- Lets call sites pass/receive str rather than bytes
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


# Fernet ciphertext always begins with this byte string (base64-encoded
# version byte 0x80). Used by the migration to tell encrypted rows apart
# from plaintext ones.
FERNET_PREFIX = "gAAAAA"


class DecryptionError(Exception):
    """Raised when stored ciphertext can't be decrypted.

    Almost always means ENCRYPTION_KEY has changed since the row was written
    (or the row is corrupt). Either way the session is unrecoverable and the
    user has to re-authenticate.
    """


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    """Cached Fernet instance built from settings.encryption_key."""
    key = get_settings().encryption_key
    # Fernet accepts bytes or str; using bytes is the documented path.
    return Fernet(key.encode("ascii"))


def encrypt(plaintext: str) -> str:
    """Encrypt a UTF-8 string. Returns base64url-safe ciphertext (str)."""
    if not isinstance(plaintext, str):
        raise TypeError("encrypt() expects str")
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(ciphertext: str) -> str:
    """Decrypt a string produced by `encrypt()`. Raises DecryptionError."""
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise DecryptionError(
            "Could not decrypt stored token — has ENCRYPTION_KEY changed?"
        ) from exc


def looks_encrypted(value: str | None) -> bool:
    """Cheap heuristic used by the plaintext-to-encrypted migration.

    True if `value` looks like Fernet ciphertext. We don't actually attempt
    decryption here — that's slower and would fire spurious errors during
    startup-time migration scans.
    """
    return bool(value) and value.startswith(FERNET_PREFIX)
