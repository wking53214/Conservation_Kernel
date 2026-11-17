"""Backlog item 5: every restored root can be put to a deployer's own side-effect-free check.

A restore required a root guard to exist but never ran it (it may be a one-use permission). `restore_root_check` is a
separate yes/no function that only looks, run once for each root in the snapshot; any answer but exactly True, or an
exception, refuses the whole file.
"""
from __future__ import annotations

import pytest

from conservation_kernel import (
    Actor, ActorKind, Artifact, ConservationKernel, EpistemicStatus, OriginStatus, Proposition,
)
from conservation_kernel.errors import SnapshotIntegrityError

BOT = Actor("bot", ActorKind.SYSTEM)
RESTORE = dict(root_guard=lambda artifact: True, allow_unguarded_evidence=True)


def _root(aid):
    prop = Proposition(f"p-{aid}", "Queue is slow.", EpistemicStatus.INFERENCE, OriginStatus.MACHINE_ORIGINATED,
                       source_refs=("log",))
    return Artifact(aid, "x", (prop,), BOT)


def _snapshot(*root_ids):
    kernel = ConservationKernel(**RESTORE)
    for rid in root_ids:
        kernel.register_root(_root(rid))
    return kernel.snapshot()


def test_with_no_check_restore_behaves_as_before():
    kernel = ConservationKernel.from_snapshot(_snapshot("r1", "r2"), **RESTORE)
    assert {a.artifact_id for a in kernel.ledger.artifacts()} == {"r1", "r2"}


def test_the_check_is_asked_about_every_root_and_approving_all_restores():
    asked = []
    kernel = ConservationKernel.from_snapshot(_snapshot("r1", "r2"), restore_root_check=lambda a: asked.append(a.artifact_id) or True, **RESTORE)
    assert sorted(asked) == ["r1", "r2"]
    assert len(kernel.ledger.artifacts()) == 2


def test_one_refused_root_refuses_the_whole_snapshot():
    with pytest.raises(SnapshotIntegrityError, match="r2"):
        ConservationKernel.from_snapshot(_snapshot("r1", "r2"), restore_root_check=lambda a: a.artifact_id != "r2", **RESTORE)


@pytest.mark.parametrize("answer", [False, None, 1, "yes", ()], ids=repr)
def test_anything_but_exactly_true_refuses(answer):
    with pytest.raises(SnapshotIntegrityError):
        ConservationKernel.from_snapshot(_snapshot("r1"), restore_root_check=lambda a: answer, **RESTORE)


def test_a_check_that_raises_never_approves():
    def broken(artifact):
        raise RuntimeError("cannot decide")
    with pytest.raises(SnapshotIntegrityError):
        ConservationKernel.from_snapshot(_snapshot("r1"), restore_root_check=broken, **RESTORE)


def test_the_check_runs_even_when_reverify_is_off():
    with pytest.raises(SnapshotIntegrityError):
        ConservationKernel.from_snapshot(_snapshot("r1"), reverify=False, restore_root_check=lambda a: False, **RESTORE)


def test_the_check_is_not_asked_about_a_transformed_artifact():
    kernel = ConservationKernel(**RESTORE)
    kernel.register_root(_root("r1"))
    asked = []
    ConservationKernel.from_snapshot(kernel.snapshot(), restore_root_check=lambda a: asked.append(a.artifact_id) or True, **RESTORE)
    assert asked == ["r1"]


def test_a_one_use_guard_is_still_not_spent_by_a_restore():
    class OneUse:
        commits = 0
        def __call__(self, artifact):
            return True
        def commit(self):
            OneUse.commits += 1
        def abort(self):
            pass
    ConservationKernel.from_snapshot(_snapshot("r1"), root_guard=OneUse(), allow_unguarded_evidence=True,
                                     restore_root_check=lambda a: True)
    assert OneUse.commits == 0
