"""Rejected transformations must not mutate persistent state.

This replaces an earlier root-level ``test_transactional_rollback.py`` script
that was written against an imagined dict-based API (``register_artifact``,
``get_artifact``, ``transform``) that this kernel never exposed. The property
it aimed at is real and worth keeping: a rejected transformation leaves the
ledger untouched, the rejection stays visible, and a legitimate transformation
still succeeds afterwards.
"""

import pytest

from conservation_kernel import ConservationKernel
from conservation_kernel.enums import VerificationStatus
from conservation_kernel.experiments import (
    build_ground_truth,
    hostile_cases,
    legitimate_transformation,
)


def _attack(name):
    return {case.name: case for case in hostile_cases()}[name]


def test_rejected_transformation_does_not_mutate_persistent_state():
    base, registry = build_ground_truth()
    kernel = ConservationKernel(registry=registry)
    kernel.register_root(base)

    baseline = kernel.reconstruct(base.artifact_id)
    assert baseline.artifact_ids_in_order == (base.artifact_id,)

    # A hostile UNKNOWN -> FACT promotion with fabricated evidence.
    hostile_output, hostile_record, _ = _attack("unknown-to-fact").build(base)
    result = kernel.submit(base, hostile_output, hostile_record)

    # 1. The transformation is rejected.
    assert result.status is VerificationStatus.REJECT
    assert not result.accepted
    assert result.violations

    # 2. The rejected output never enters the ledger.
    with pytest.raises(KeyError):
        kernel.ledger.artifact(hostile_output.artifact_id)
    assert kernel.ledger.transformation_for_output(hostile_output.artifact_id) is None

    # 3. Persistent state is byte-for-byte what it was before the attack.
    after = kernel.reconstruct(base.artifact_id)
    assert after.to_dict() == baseline.to_dict()

    # 4. The rejection is retained as a visible report, not silently dropped.
    reports = kernel.ledger.reports()
    assert len(reports) == 1
    assert not reports[0].accepted

    # 5. A legitimate transformation still commits after the rejected attack.
    good_output, good_record = legitimate_transformation(base, 1)
    good_result = kernel.submit(base, good_output, good_record)
    assert good_result.accepted
    assert kernel.ledger.artifact(good_output.artifact_id) == good_output

    reconstructed = kernel.reconstruct(good_output.artifact_id)
    assert reconstructed.root_artifact_ids == (base.artifact_id,)
    assert len(reconstructed.artifact_ids_in_order) == 2
    assert len(reconstructed.transformation_ids_in_order) == 1

    # 6. The rejected output is still absent.
    with pytest.raises(KeyError):
        kernel.ledger.artifact(hostile_output.artifact_id)
