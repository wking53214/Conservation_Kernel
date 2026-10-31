"""A root guard that offers `commit` and `abort` is told how the write it permitted ended.

A one-use permission that is spent when it says yes is lost if the write then fails. The ledger tells a guard that has
`commit` and `abort` methods: `commit()` after the root is in, `abort()` if adding it raised, so the guard can give the
permission back. A guard with neither behaves as before. The kernel imports nothing to supply either method.
"""
from __future__ import annotations

import pytest

from conservation_kernel import Actor, Artifact, ConservationKernel, EpistemicStatus, OriginStatus, Proposition
from conservation_kernel.errors import RootAdmissionError


def root(artifact_id="root:doc-1") -> Artifact:
    proposition = Proposition(proposition_id="p0", text="The invoice came to $412.00.", epistemic_status=EpistemicStatus.INFERENCE,
                              origin=OriginStatus.MACHINE_ORIGINATED, source_refs=("doc-1",))
    return Artifact(artifact_id=artifact_id, content="Invoice came to $412.00.", propositions=(proposition,),
                    producer=Actor.system("tie"))


class Settling:
    def __init__(self, answer=True):
        self.answer, self.told = answer, []

    def __call__(self, artifact):
        return self.answer

    def commit(self):
        self.told.append("commit")

    def abort(self):
        self.told.append("abort")


def test_a_root_that_goes_in_tells_the_guard_to_commit():
    guard = Settling()
    kernel = ConservationKernel(root_guard=guard)
    kernel.register_root(root())
    assert guard.told == ["commit"]


def test_a_root_the_ledger_cannot_add_tells_the_guard_to_abort(monkeypatch):
    guard = Settling()
    kernel = ConservationKernel(root_guard=guard)

    def fails(artifact):
        raise RuntimeError("the ledger could not take it")
    monkeypatch.setattr(kernel.ledger, "_add_artifact", fails)
    with pytest.raises(RuntimeError):
        kernel.register_root(root())
    assert guard.told == ["abort"]


def test_a_refusal_by_the_guard_is_not_a_write_and_tells_it_nothing():
    guard = Settling(answer=False)
    kernel = ConservationKernel(root_guard=guard)
    with pytest.raises(RootAdmissionError, match="root guard"):
        kernel.register_root(root())
    assert guard.told == []


def test_a_guard_with_neither_method_works_as_before():
    kernel = ConservationKernel(root_guard=lambda artifact: True)
    kernel.register_root(root())
    assert kernel.ledger.artifact("root:doc-1") is not None


def test_a_guard_whose_settling_raises_does_not_hide_the_write_or_its_failure(monkeypatch):
    class Broken(Settling):
        def commit(self):
            raise RuntimeError("cannot settle")
    kernel = ConservationKernel(root_guard=Broken())
    kernel.register_root(root())
    assert kernel.ledger.artifact("root:doc-1") is not None
