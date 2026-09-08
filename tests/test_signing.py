"""A snapshot that re-verifies is one the constitution would accept, not one
this deployment produced. 0.3.0 adds the signature that says who wrote it."""
import json

import pytest

from conservation_kernel import Actor, ActorKind, Artifact, ConservationKernel, HmacSigner
from conservation_kernel.errors import SnapshotAuthenticityError, SnapshotIntegrityError
from conservation_kernel.signing import check_signature, signature_block

KEY = b"deployer-key-0123456789abcdef"


def _kernel():
    k = ConservationKernel()
    k.register_root(Artifact(artifact_id="root-1", content="observed", producer=Actor(actor_id="feed", kind=ActorKind.SYSTEM), propositions=()))
    return k


def test_signer_rejects_short_keys_and_empty_ids():
    with pytest.raises(ValueError):
        HmacSigner(b"short")
    with pytest.raises(ValueError):
        HmacSigner(KEY, key_id="")


def test_signature_block_round_trips_and_names_its_key():
    s = HmacSigner(KEY, key_id="k1")
    block = signature_block(s, "abc")
    assert block["key_id"] == "k1" and block["algorithm"] == "hmac-sha256"
    assert check_signature(s, "abc", block) is None
    assert "does not verify" in check_signature(s, "abd", block)
    assert "no signature" in check_signature(s, "abc", None)
    assert "verifier holds" in check_signature(HmacSigner(KEY, key_id="k2"), "abc", block)


def test_signed_snapshot_loads_with_the_same_key(tmp_path):
    s = HmacSigner(KEY, key_id="k1")
    _kernel().save(tmp_path / "k.json", signer=s)
    body = json.loads((tmp_path / "k.json").read_text())
    assert body["signature"]["key_id"] == "k1"
    restored = ConservationKernel.load(tmp_path / "k.json", signer=s)
    assert restored.ledger.artifact("root-1").content == "observed"


def test_unsigned_snapshot_is_refused_by_a_loader_that_holds_a_key(tmp_path):
    _kernel().save(tmp_path / "k.json")
    with pytest.raises(SnapshotAuthenticityError, match="no signature"):
        ConservationKernel.load(tmp_path / "k.json", signer=HmacSigner(KEY))


def test_snapshot_signed_by_another_key_is_refused(tmp_path):
    _kernel().save(tmp_path / "k.json", signer=HmacSigner(b"someone-elses-key-0123456789", key_id="k1"))
    with pytest.raises(SnapshotAuthenticityError, match="does not verify"):
        ConservationKernel.load(tmp_path / "k.json", signer=HmacSigner(KEY, key_id="k1"))


def test_a_consistent_forgery_with_a_recomputed_digest_is_refused(tmp_path):
    """The attack the digest alone could not stop: edit the file, recompute
    the public digest, and the integrity check passes. The signature does not."""
    from conservation_kernel.model import _digest, canonical_json
    s = HmacSigner(KEY, key_id="k1")
    path = tmp_path / "k.json"
    _kernel().save(path, signer=s)
    body = json.loads(path.read_text())
    signature = body.pop("signature")
    body.pop("snapshot_digest")
    body["ledger"]["artifacts"][0]["content"] = "forged"
    for digest in ("content_digest", "artifact_digest"):             # the forger lets the loader recompute them
        body["ledger"]["artifacts"][0][digest] = None
    body["snapshot_digest"] = _digest(canonical_json(body))
    body["signature"] = signature
    path.write_text(canonical_json(body))
    ConservationKernel.load(path)                                    # integrity alone: accepted
    with pytest.raises(SnapshotAuthenticityError):
        ConservationKernel.load(path, signer=s)                      # authenticity: refused


def test_corruption_is_still_reported_as_integrity_not_authenticity(tmp_path):
    s = HmacSigner(KEY)
    path = tmp_path / "k.json"
    _kernel().save(path, signer=s)
    path.write_text(path.read_text().replace("observed", "altered"))
    with pytest.raises(SnapshotIntegrityError):
        ConservationKernel.load(path, signer=s)


def test_an_unsigned_snapshot_still_loads_without_a_key(tmp_path):
    _kernel().save(tmp_path / "k.json")
    assert ConservationKernel.load(tmp_path / "k.json").ledger.artifact("root-1")
