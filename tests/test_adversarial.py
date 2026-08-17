import pytest

from conservation_kernel.enums import VerificationStatus
from conservation_kernel.experiments import build_ground_truth, hostile_cases
from conservation_kernel.verifier import IndependentVerifier


@pytest.mark.parametrize("case_index", range(25))
def test_hostile_case_is_rejected(case_index):
    base, _ = build_ground_truth()
    cases = hostile_cases()
    assert len(cases) == 25
    case = cases[case_index]
    output, record, registry = case.build(base)

    result = IndependentVerifier().verify(base, output, record, registry)

    assert result.status is VerificationStatus.REJECT, case.name
    assert result.violations, case.name


def test_hostile_case_names_cover_the_required_attack_classes():
    names = {case.name for case in hostile_cases()}
    required_fragments = {
        "unknown-to-fact",
        "inference-to-fact",
        "simulation-to-historical-fact",
        "recommendation-to-decision",
        "ai-output-to-human-origin",
        "estimated-to-verified",
        "historical-to-current",
        "model-consensus-to-truth",
        "execution-success-to-correctness",
        "authorization-to-truth",
        "citation-to-proof",
        "deleted-evidence-still-valid",
        "provenance-stripping",
        "source-substitution",
        "conflict-collapse",
        "unknown-field-dropped",
        "actor-report-promoted-to-observation",
        "observed-at-substituted-for-occurred-at",
        "derived-result-as-direct-observation",
        "fabricated-human-adoption",
        "canonical-state-without-authorization",
        "false-lineage-envelope",
        "required-metadata-omitted",
        "claims-preservation-alters-semantics",
        "downstream-unrooted-new-artifact",
    }
    assert required_fragments <= names
