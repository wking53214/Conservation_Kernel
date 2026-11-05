"""A roster can say which guard it will accept, not only that the kernel has one.

`require_guard` and `require_evidence_guard` ask whether a guard exists, and a lambda that answers True to everything
satisfies them. `accept_guard` and `accept_evidence_guard` hand the kernel's own guard to a predicate the roster
supplies (an isinstance check on the roster's own guard class, say), so a guard the roster did not build is a breach.
Skipped when cns is absent, like the rest of the connected half.
"""
from __future__ import annotations

import os

import pytest

if os.environ.get("CONSERVATION_KERNEL_REQUIRE_CNS") == "1":
    import cns.gate  # noqa: F401
else:
    pytest.importorskip("cns.gate", reason="cns not installed; run in an environment with the [cns] extra")

from conservation_kernel import ConservationKernel  # noqa: E402
from conservation_kernel.cns_connector import CnsRootAdmissionGate  # noqa: E402
from tests.test_root_guard import root as guard_root  # noqa: E402


class OurGuard:
    def __init__(self, answer=False):
        self.answer = answer

    def __call__(self, thing):
        return self.answer


def ours(guard):
    return isinstance(guard, OurGuard)


def test_the_kernel_hands_out_the_guards_it_was_built_with_and_none_when_it_has_none():
    root_guard, evidence_guard = OurGuard(), OurGuard()
    kernel = ConservationKernel(root_guard=root_guard, evidence_guard=evidence_guard)
    assert kernel.root_guard is root_guard and kernel.evidence_guard is evidence_guard
    bare = ConservationKernel(allow_unguarded_roots=True)
    assert bare.root_guard is None and bare.evidence_guard is None


def test_a_guard_the_roster_built_is_accepted():
    kernel = ConservationKernel(root_guard=OurGuard(), evidence_guard=OurGuard())
    result = CnsRootAdmissionGate(kernel, accept_guard=ours, accept_evidence_guard=ours).check(guard_root())
    assert result.outcome.value == "pass"


def test_a_lambda_that_says_yes_to_everything_is_refused_even_though_a_guard_exists():
    kernel = ConservationKernel(root_guard=lambda a: True, evidence_guard=lambda r: True)
    assert CnsRootAdmissionGate(kernel, require_guard=True, require_evidence_guard=True).check(guard_root()).outcome.value == "pass"
    result = CnsRootAdmissionGate(kernel, accept_guard=ours, accept_evidence_guard=ours).check(guard_root())
    assert result.outcome.value == "terminal_breach"
    assert "root guard is not one the roster accepts" in result.reason
    assert "evidence guard is not one the roster accepts" in result.reason


def test_each_acceptance_is_judged_on_its_own():
    kernel = ConservationKernel(root_guard=OurGuard(), evidence_guard=lambda r: True)
    result = CnsRootAdmissionGate(kernel, accept_guard=ours, accept_evidence_guard=ours).check(guard_root())
    assert "evidence guard is not one the roster accepts" in result.reason and "root guard is not" not in result.reason


def test_asking_to_accept_a_guard_also_refuses_a_kernel_with_none():
    kernel = ConservationKernel(allow_unguarded_roots=True)
    result = CnsRootAdmissionGate(kernel, accept_guard=ours, accept_evidence_guard=ours).check(guard_root())
    assert result.outcome.value == "terminal_breach"
    assert "no root guard" in result.reason and "no evidence guard" in result.reason


def test_a_predicate_that_raises_or_answers_loosely_never_accepts():
    def boom(guard):
        raise RuntimeError("cannot say")
    kernel = ConservationKernel(root_guard=OurGuard(), evidence_guard=OurGuard())
    for predicate in (boom, lambda g: 1, lambda g: "yes", lambda g: None):
        result = CnsRootAdmissionGate(kernel, accept_guard=predicate).check(guard_root())
        assert result.outcome.value == "terminal_breach", predicate


def test_a_predicate_that_is_not_callable_is_refused_at_construction():
    with pytest.raises(ValueError, match="accept_guard"):
        CnsRootAdmissionGate(ConservationKernel(allow_unguarded_roots=True), accept_guard="OurGuard")


def test_without_the_new_arguments_the_gate_judges_as_before():
    kernel = ConservationKernel(root_guard=lambda a: True)
    assert CnsRootAdmissionGate(kernel).check(guard_root()).outcome.value == "pass"
