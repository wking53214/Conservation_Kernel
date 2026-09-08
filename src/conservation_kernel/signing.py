"""Authentication for what the kernel and its callers write to disk.

Integrity (a digest that recomputes) says a file was not corrupted.
Authenticity (a signature only a key holder can produce) says who wrote it.
Until 0.3.0 every durable artifact in the portfolio had the first and not the
second: anyone who could write the file, and who could read the public
digest function, could produce a consistent forgery. This module supplies
the one primitive the rest of the portfolio shares, so ledger entries,
receipts and snapshots are all signed the same way with the same kind of key.

The key is the deployer's. It is never written into a record; only its
`key_id` is, so a verifier knows which key to ask for.
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Protocol, runtime_checkable


@runtime_checkable
class Signer(Protocol):
    """Anything that can sign bytes and verify a signature over them.

    `HmacSigner` is the in-process implementation. A deployment that keeps
    the key outside the process (a signing service, an HSM) implements the
    same three members and hands the object in; nothing else changes.
    """

    key_id: str

    def sign(self, payload: bytes) -> str: ...

    def verify(self, payload: bytes, signature: str) -> bool: ...


class HmacSigner:
    """HMAC-SHA256 over the payload with a caller-held key."""

    algorithm = "hmac-sha256"

    def __init__(self, key: bytes, key_id: str = "default"):
        if not isinstance(key, (bytes, bytearray)) or len(key) < 16:
            raise ValueError("HmacSigner needs a key of at least 16 bytes")
        if not key_id:
            raise ValueError("HmacSigner needs a key_id")
        self._key = bytes(key)
        self.key_id = key_id

    def sign(self, payload: bytes) -> str:
        return hmac.new(self._key, payload, hashlib.sha256).hexdigest()

    def verify(self, payload: bytes, signature: str) -> bool:
        if not isinstance(signature, str):
            return False
        return hmac.compare_digest(self.sign(payload), signature)


def signature_block(signer: Signer, digest: str) -> dict:
    """The signature as it is stored beside a digest."""
    return {
        "key_id": signer.key_id,
        "algorithm": getattr(signer, "algorithm", "unknown"),
        "value": signer.sign(digest.encode("utf-8")),
    }


def check_signature(signer: Signer, digest: str, block) -> str | None:
    """None when `block` is a valid signature over `digest` by `signer`'s key;
    otherwise the reason it is not."""
    if not isinstance(block, dict):
        return "no signature present"
    if block.get("key_id") != signer.key_id:
        return f"signed with key {block.get('key_id')!r}, verifier holds {signer.key_id!r}"
    if not signer.verify(digest.encode("utf-8"), block.get("value")):
        return "signature does not verify"
    return None
