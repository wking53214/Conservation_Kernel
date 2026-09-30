"""Optional connector to CNS (``cns.gate``).

The Conservation Kernel is independent. It has no runtime dependency, imports
nothing from CNS when it loads, and its whole suite passes with CNS absent.
This module is the one place that knows CNS exists, and it asks for CNS only
when one of its functions is called. Without CNS installed those calls raise
:class:`CnsNotInstalled` with the install command; nothing else in the kernel
is affected. ``conservation_kernel/__init__`` does not import this module.

What connecting means
---------------------
The kernel keeps its own verdict, :class:`~conservation_kernel.result.VerificationResult`
(``status``, ``violations``, ``unverifiable_properties``), and its own
admission check, :meth:`ConservationKernel.admit_root` (a tuple of reasons,
empty when the root may be registered). CNS's shared gate contract is
``cns.gate.GateResult`` (``gate``, ``position``, ``outcome``, ``reason``,
``subject``, ``subject_digest``). This module translates one into the other
without changing either, so a consumer that speaks CNS can resolve the
kernel's verdicts alongside gates from other repositories.

The two verdicts and where they sit
-----------------------------------
* **Transformation verification is the OMEGA end.** ``verify`` takes the
  produced output artifact as an argument: it judges a result that already
  exists, and a rejection means the result never enters the ledger
  (``docs/GATEWAY.md``: a transformer's output is an untrusted proposal until
  the kernel accepts it). The verifier cannot run before the output exists,
  so there is no precondition form of it.
* **Root admission is the ALPHA end.** Registering a root judges an asserted
  root before it becomes ancestry (``errors.RootAdmissionError``: a forged
  origin story must not become legitimate ancestry). A refusal means the
  artifact never becomes a root, so nothing can be derived from it.
  ``register_root`` refuses for two kinds of reason: ``admit_root`` inspects
  the propositions, and the ledger (``add_initial``) refuses an artifact that
  already has parents or whose id is already registered. ``admit_root`` alone
  does not see the second kind, so :func:`root_refusals` returns both and the
  gate uses it.

The two gates judge different candidates (a transformation, and an asserted
root artifact), so they do not run on one request. The connector therefore
does not pair them into a single ``GateChain``: :func:`cns_chain` holds the
OMEGA gate only and ``cns_chain(...).complete()`` is ``False`` by design.
Claiming a complete chain would be exactly the "two ends that nothing ties to
the same request" that CNS warns about. A consumer that wants the ALPHA end
runs :class:`CnsRootAdmissionGate` on its own, on a root artifact. Putting it
in the ``alpha`` slot of the same ``GateChain`` as :class:`CnsGate` is
possible (CNS then reports ``complete()`` as ``True``) but misleading: each
gate raises ``TypeError`` for the other's candidate, so the two ends share no
request, which is the false completeness :func:`cns_chain` avoids.

The mapping, and why
--------------------
* ``PASS`` -> ``PASS``.
* ``PASS_WITH_DECLARED_TRANSFORMATION`` -> ``PASS``. The kernel's own
  ``accepted`` is true for it and it commits to the ledger. The reason keeps
  what was left unverified (for example ``semantic_content_equivalence``).
  This holds for every unverifiable property, not only that one, because the
  kernel accepts them all. A consumer with a stricter policy has to read the
  reason: ``sentinel_os``'s ``ConservationGateway`` refuses an accepted result
  that carries any unverifiable property other than
  ``semantic_content_equivalence``, and splits a rejection into
  authorization-required, verification-required and rejected. This connector
  does neither: every rejection is the same ``TERMINAL_BREACH``.
* ``REJECT`` -> ``TERMINAL_BREACH``.
* ``UNVERIFIABLE`` -> ``TERMINAL_BREACH``. The kernel says it is "never
  treated as pass", and both consumers (sentinel_os, observe-perceive) abort
  on it.
* Accepted, then the ledger refuses (``LedgerError``) -> ``TERMINAL_BREACH``
  (``submit_to_cns`` only; ``ConservationKernel.submit`` raises here).
* Root registration that nothing refuses (:func:`root_refusals` is empty) ->
  ``PASS`` at ``ALPHA``.
* Root registration that anything refuses, whether ``admit_root`` or the
  ledger -> ``TERMINAL_BREACH`` at ``ALPHA``.
* ``RETRY`` is never produced. The kernel models no retry or repair:
  ``docs/GATEWAY.md`` puts retry policy in the gateway, and the model refuses
  "silent repair". Nothing here invents one.

Fail closed: ``PASS`` is produced only when the kernel itself accepted and the
verdict could be bound to what it judged. Anything else, including a verdict
whose content CNS cannot digest and a hand-built result that is ``accepted``
yet carries violations, is ``TERMINAL_BREACH``.

What a verdict is bound to
--------------------------
``subject`` is a label (default ``"transformation"`` or ``"root"``).
``subject_digest`` is ``cns.gate.subject_digest`` over a mapping made only of
strings: the ids and the kernel's own ``artifact_digest`` of every input and of
the output, the ``transformation_id``, and ``TransformationRecord.
canonical_digest()``. The kernel already digests everything it judges
(including ``created_at``, producers, propositions and declared changes), so
this binds the verdict to that content and keeps the CNS-side input to str
only. Two limits, both the kernel's own. ``artifact_digest`` is computed once,
when an ``Artifact`` is constructed, and the nested ``metadata`` of a
proposition is only shallow-frozen, so an artifact whose nested metadata is
mutated in place afterwards keeps the same digest even though a verdict on it
can change (the kernel's ``input_hashes`` check has the same blind spot).
And the evidence registry is deliberately not in the digest: it is the
witness the verdict was judged *against*, not the thing judged.

One real input cannot be expressed: a non-finite float (NaN or infinity) in a
``DeclaredChange`` value. The kernel constructs such a record, but
``canonical_digest()`` refuses it, and so does CNS. It surfaces in three ways:

* ``verify`` returns a rejection (the non-finite declaration matches no
  observed change, so it is ``REJECT``). The connector fails closed and says
  so: the verdict is ``TERMINAL_BREACH``, it is *unbound* (empty
  ``subject_digest``, so ``cns.gate.unbound`` names it) and its reason says
  why. It is never ``PASS``, even if a caller hands ``to_cns_result`` an
  accepted result for it.
* ``verify`` returns an *acceptance*. A matching declaration followed by a
  second declaration for the same subject and dimension that holds the
  non-finite value is accepted, because the verifier stops at the first match.
  The kernel then commits it. The connector still fails closed, with the same
  unbound ``TERMINAL_BREACH``, so here the CNS verdict and the ledger
  disagree: the ledger holds an output this verdict refuses.
  ``submit_to_cns`` says so in the reason. This is a kernel inconsistency the
  connector surfaces and does not fix.
* ``verify`` itself raises ``ValueError`` (the declaration matches an observed
  change, and comparing it needs the canonical form). There is no kernel
  verdict to translate, so the connector lets that error propagate unchanged.

A declared value nested so deeply that the canonical form overflows the
interpreter's recursion limit (``RecursionError``) is the same case as the
first: it cannot be digested, so the verdict is unbound ``TERMINAL_BREACH``.

Install with the extra. The extra pins ``cns`` by git commit, which PyPI does
not accept, so this package is installed from git or from a checkout, not from
an index: see ``INSTALL_HINT``.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from types import ModuleType
from typing import Any

from .errors import LedgerError
from .events import TransformationRecord
from .kernel import ConservationKernel
from .ledger import ConservationLedger
from .model import Artifact
from .registry import EvidenceRegistry
from .result import VerificationResult
from .verifier import IndependentVerifier

__all__ = [
    "CnsGate",
    "CnsNotInstalled",
    "CnsRootAdmissionGate",
    "TransformationCandidate",
    "admission_to_cns_result",
    "cns_available",
    "cns_chain",
    "root_digest",
    "root_refusals",
    "submit_to_cns",
    "to_cns_result",
    "transformation_digest",
    "verify_to_cns",
]

INSTALL_HINT = (
    "pip install 'conservation-kernel[cns] @ "
    "git+https://github.com/wking53214/conservation_kernel@<commit>' "
    "(or, from a checkout, pip install -e '.[cns]')"
)

#: The ``gate`` field of a transformation verdict.
GATE_NAME = "conservation"
#: The ``gate`` field of a root admission verdict.
ROOT_GATE_NAME = "root_admission"
#: What ``subject`` is set to when the caller does not name the judged content.
DEFAULT_SUBJECT = "transformation"
DEFAULT_ROOT_SUBJECT = "root"


class CnsNotInstalled(ImportError):
    """Raised by this module's functions when ``cns`` cannot be imported."""


def _cns_gate() -> ModuleType:
    """Import ``cns.gate`` on demand, or say exactly what is missing."""
    try:
        return importlib.import_module("cns.gate")
    except ImportError as exc:
        raise CnsNotInstalled(
            "conservation_kernel.cns_connector needs the CNS package "
            f"(cns.gate), which is not installed. Install it with: {INSTALL_HINT}. "
            "The Conservation Kernel itself works without it."
        ) from exc


def cns_available() -> bool:
    """Whether the CNS gate contract can be imported in this environment."""
    try:
        _cns_gate()
    except CnsNotInstalled:
        return False
    return True


@dataclass(frozen=True)
class TransformationCandidate:
    """One transformation as the kernel judges it: inputs, output and record.

    ``inputs`` may be a single artifact or a sequence, as in
    ``IndependentVerifier.verify``. An empty sequence is allowed: the kernel
    rejects it (``NO_INPUT_ARTIFACT``) and that rejection should be reported,
    not refused here.
    """

    inputs: Any
    output: Artifact
    record: TransformationRecord

    def __post_init__(self) -> None:
        inputs = (self.inputs,) if isinstance(self.inputs, Artifact) else tuple(self.inputs)
        if any(not isinstance(item, Artifact) for item in inputs):
            raise TypeError("inputs must be an Artifact or a sequence of Artifacts")
        if not isinstance(self.output, Artifact):
            raise TypeError(f"output must be an Artifact; got {type(self.output).__name__}")
        if not isinstance(self.record, TransformationRecord):
            raise TypeError(
                f"record must be a TransformationRecord; got {type(self.record).__name__}"
            )
        object.__setattr__(self, "inputs", inputs)


def _artifact_ref(artifact: Artifact) -> dict[str, str]:
    return {
        "artifact_id": artifact.artifact_id,
        "artifact_digest": str(artifact.artifact_digest),
    }


def _transformation_content(candidate: TransformationCandidate) -> dict[str, Any]:
    """The judged content of a transformation, as str-only canonical input.

    ``record.canonical_digest()`` raises ``ValueError`` for a non-finite float
    in a declared change; callers that must not raise go through ``_bind``.
    """
    return {
        "kind": "transformation",
        "transformation_id": candidate.record.transformation_id,
        "input_artifacts": [_artifact_ref(item) for item in candidate.inputs],
        "output_artifact": _artifact_ref(candidate.output),
        "record_digest": candidate.record.canonical_digest(),
    }


def _root_content(artifact: Artifact) -> dict[str, Any]:
    return {"kind": "root_artifact", **_artifact_ref(artifact)}


def transformation_digest(candidate: TransformationCandidate) -> str:
    """The digest a bound verdict on ``candidate`` carries.

    Pass it, with the subject label, to ``GateResult.binds`` to check that a
    verdict was issued against exactly this transformation. Raises
    ``ValueError`` for a candidate the kernel cannot digest (a non-finite
    float in a declared change) and ``RecursionError`` for a declared value
    nested beyond the recursion limit; a verdict on such a candidate is
    unbound.
    """
    return _cns_gate().subject_digest(_transformation_content(candidate))


def root_digest(artifact: Artifact) -> str:
    """The digest a bound root admission verdict on ``artifact`` carries."""
    return _cns_gate().subject_digest(_root_content(artifact))


def _bind(cns_gate: ModuleType, content: Callable[[], dict[str, Any]]) -> tuple[str, str]:
    """``(digest, problem)``; ``digest`` is empty when the content cannot be digested."""
    try:
        return cns_gate.subject_digest(content()), ""
    except (TypeError, ValueError) as exc:
        return "", str(exc)
    except RecursionError:
        # A declared value nested past the recursion limit: the kernel accepts
        # or rejects it, but its canonical form cannot be built.
        return "", "declared content is nested too deeply to canonicalize"


def _require_subject(subject: str) -> None:
    if not isinstance(subject, str) or not subject:
        raise ValueError("subject must be a non-empty label; an unlabelled verdict binds to nothing")


def _verdict(
    cns_gate: ModuleType,
    *,
    gate_name: str,
    position: Any,
    outcome: Any,
    reason: str,
    subject: str,
    content: Callable[[], dict[str, Any]],
    unbound_note: str = "",
) -> Any:
    """Build the verdict, refusing to issue a PASS that is not bound.

    ``unbound_note`` is appended to the reason only when the verdict turns out
    unbound, for a caller that knows something the reason cannot (for
    example that the ledger holds the output).
    """
    digest, problem = _bind(cns_gate, content)
    if not digest:
        outcome = cns_gate.GateOutcome.TERMINAL_BREACH
        reason = f"unbound, the judged content cannot be digested canonically ({problem}); {reason}"
        if unbound_note:
            reason = f"{reason}; {unbound_note}"
    return cns_gate.GateResult(
        gate=gate_name,
        position=position,
        outcome=outcome,
        reason=reason,
        subject=subject,
        subject_digest=digest,
    )


def _reason(result: VerificationResult) -> str:
    text = str(result.status)
    if result.violations:
        parts = []
        for item in result.violations:
            where = f"[{item.subject_id}]" if item.subject_id else ""
            parts.append(f"{item.code}{where}: {item.detail}")
        text += ": " + "; ".join(parts)
    if result.unverifiable_properties:
        text += " (unverifiable: " + ", ".join(result.unverifiable_properties) + ")"
    return text


def _require_describes(result: VerificationResult, candidate: TransformationCandidate) -> None:
    """A result may only be bound to the candidate it was issued for.

    Without this, ``to_cns_result`` would be the place a verdict is lifted off
    one transformation and bound to another, the transplant the digest exists
    to catch. A ``VerificationResult`` carries ids and no content digest, so
    this catches a result for a different transformation, not a result for the
    same ids over altered content. ``CnsGate.check`` and ``submit_to_cns`` run
    the kernel themselves and do not depend on the caller getting this right.
    """
    if (
        result.transformation_id != candidate.record.transformation_id
        or result.output_artifact_id != candidate.output.artifact_id
        or tuple(result.input_artifact_ids) != tuple(item.artifact_id for item in candidate.inputs)
    ):
        raise ValueError(
            "this VerificationResult was not issued for this candidate "
            f"(result is for {result.transformation_id!r}, candidate is "
            f"{candidate.record.transformation_id!r}); refusing to bind it"
        )


def to_cns_result(
    result: VerificationResult,
    candidate: TransformationCandidate,
    *,
    subject: str = DEFAULT_SUBJECT,
) -> Any:
    """Translate the kernel's verdict on ``candidate`` into a ``cns.gate.GateResult``.

    ``PASS`` exactly when ``result.accepted``, the result carries no violations,
    and the verdict could be bound to the candidate; every other case is
    ``TERMINAL_BREACH``. The position is ``OMEGA``. Raises ``ValueError`` if
    ``result`` was issued for a different transformation (or other ids) than
    ``candidate``.

    The binding is only as good as the caller's pairing. A
    ``VerificationResult`` carries ids and no content digest, so a result
    issued for the same ids over *different* content cannot be detected here,
    and would be bound to the content of ``candidate``, which was never
    verified. Pair a result with the candidate it was computed from, or use
    :class:`CnsGate`, :func:`verify_to_cns` or :func:`submit_to_cns`, which run
    the verifier on the very candidate they bind.
    """
    return _to_cns_result(result, candidate, subject, "")


def _to_cns_result(
    result: VerificationResult,
    candidate: TransformationCandidate,
    subject: str,
    unbound_note: str,
) -> Any:
    cns_gate = _cns_gate()
    _require_subject(subject)
    if not isinstance(candidate, TransformationCandidate):
        raise TypeError(
            f"the kernel judges transformations; got {type(candidate).__name__}"
        )
    _require_describes(result, candidate)
    reason = _reason(result)
    if result.accepted and result.violations:
        # An accepted status that also lists violations is not a verdict the
        # kernel produces. Do not read only .accepted and pass it.
        outcome = cns_gate.GateOutcome.TERMINAL_BREACH
        reason = f"inconsistent result, accepted yet carrying violations; {reason}"
    elif result.accepted:
        outcome = cns_gate.GateOutcome.PASS
    else:
        outcome = cns_gate.GateOutcome.TERMINAL_BREACH
    return _verdict(
        cns_gate,
        gate_name=GATE_NAME,
        position=cns_gate.GatePosition.OMEGA,
        outcome=outcome,
        reason=reason,
        subject=subject,
        content=lambda: _transformation_content(candidate),
        unbound_note=unbound_note,
    )


def root_refusals(kernel: ConservationKernel, artifact: Artifact) -> tuple[str, ...]:
    """Every reason ``kernel.register_root(artifact)`` would refuse it; empty if none.

    ``admit_root`` is not enough on its own. It inspects the propositions,
    while ``register_root`` also refuses what the ledger refuses
    (``ConservationLedger.add_initial``): an artifact that already has parents
    is not a root, and an id that is already registered cannot be registered
    again. Both are included here, so an empty result means ``register_root``
    would accept. Nothing is registered and nothing is written.
    """
    if not isinstance(artifact, Artifact):
        raise TypeError(f"root admission judges an Artifact; got {type(artifact).__name__}")
    reasons = list(kernel.admit_root(artifact))
    try:
        # The ledger's own parent rule, run on a throwaway ledger so the text
        # and the rule cannot drift from what register_root does.
        ConservationLedger().add_initial(artifact)
    except LedgerError as exc:
        reasons.append(str(exc))
    try:
        kernel.ledger.artifact(artifact.artifact_id)
    except KeyError:
        pass
    else:
        reasons.append(f"duplicate artifact ID {artifact.artifact_id}")
    return tuple(reasons)


def admission_to_cns_result(
    reasons: Sequence[str],
    artifact: Artifact,
    *,
    subject: str = DEFAULT_ROOT_SUBJECT,
) -> Any:
    """Translate root-refusal reasons into a ``GateResult``.

    No reasons is ``PASS``; any reason is ``TERMINAL_BREACH``. The position is
    ``ALPHA``: the root is judged before it is registered.

    Pass :func:`root_refusals`, not ``admit_root`` alone. ``admit_root`` returns
    no reasons for an artifact that has parents or whose id is already
    registered, which ``register_root`` refuses; a ``PASS`` made from its
    reasons alone would say the kernel accepts what it does not.
    """
    cns_gate = _cns_gate()
    _require_subject(subject)
    if isinstance(reasons, (str, bytes)):
        # tuple("") is empty and would read as "no reasons": a PASS.
        raise TypeError("reasons must be a sequence of strings, as admit_root returns")
    if not isinstance(artifact, Artifact):
        raise TypeError(f"root admission judges an Artifact; got {type(artifact).__name__}")
    reasons = tuple(reasons)
    if reasons:
        outcome = cns_gate.GateOutcome.TERMINAL_BREACH
        reason = "root refused: " + "; ".join(reasons)
    else:
        outcome = cns_gate.GateOutcome.PASS
        reason = "root admitted"
    return _verdict(
        cns_gate,
        gate_name=ROOT_GATE_NAME,
        position=cns_gate.GatePosition.ALPHA,
        outcome=outcome,
        reason=reason,
        subject=subject,
        content=lambda: _root_content(artifact),
    )


class CnsGate:
    """The kernel's transformation verification as a ``cns.gate.Gate``.

    Holds an evidence registry (and optionally a verifier) and judges a
    :class:`TransformationCandidate`. ``check`` runs the verifier unchanged
    and returns its verdict as a bound ``cns.gate.GateResult`` at the OMEGA
    end. It never writes: no ledger is involved, so judging a candidate does
    not commit it. Use :func:`submit_to_cns` for the kernel's own path.
    """

    name = GATE_NAME

    def __init__(
        self,
        registry: EvidenceRegistry,
        verifier: IndependentVerifier | None = None,
        *,
        subject: str = DEFAULT_SUBJECT,
    ) -> None:
        _cns_gate()  # fail here, at construction, not on first use
        _require_subject(subject)
        self._registry = registry
        self._verifier = verifier or IndependentVerifier()
        self._subject = subject

    @property
    def position(self) -> Any:
        return _cns_gate().GatePosition.OMEGA

    def check(self, candidate: object) -> Any:
        if not isinstance(candidate, TransformationCandidate):
            raise TypeError(
                "the conservation gate judges a TransformationCandidate; "
                f"got {type(candidate).__name__}"
            )
        result = self._verifier.verify(
            candidate.inputs, candidate.output, candidate.record, self._registry
        )
        return to_cns_result(result, candidate, subject=self._subject)


class CnsRootAdmissionGate:
    """The kernel's root admission as a ``cns.gate.Gate`` at the ALPHA end.

    ``check`` asks what ``register_root`` would refuse (:func:`root_refusals`:
    ``admit_root`` unchanged, plus the ledger's structural refusals), reads the
    registry and the ledger, writes nothing, and returns the answer as a bound
    ``GateResult``. It does not register the root;
    ``ConservationKernel.register_root`` does.
    """

    name = ROOT_GATE_NAME

    def __init__(self, kernel: ConservationKernel, *, subject: str = DEFAULT_ROOT_SUBJECT) -> None:
        _cns_gate()  # fail here, at construction, not on first use
        _require_subject(subject)
        self._kernel = kernel
        self._subject = subject

    @property
    def position(self) -> Any:
        return _cns_gate().GatePosition.ALPHA

    def check(self, candidate: object) -> Any:
        if not isinstance(candidate, Artifact):
            raise TypeError(
                f"root admission judges an Artifact; got {type(candidate).__name__}"
            )
        return admission_to_cns_result(
            root_refusals(self._kernel, candidate), candidate, subject=self._subject
        )


def cns_chain(
    registry: EvidenceRegistry,
    verifier: IndependentVerifier | None = None,
    *,
    subject: str = DEFAULT_SUBJECT,
) -> Any:
    """A ``cns.gate.GateChain`` holding the transformation gate in ``omega``.

    ``alpha`` stays empty and ``complete()`` is ``False``: the two kernel gates
    judge different candidates, so this does not pair them. See the module
    docstring.
    """
    cns_gate = _cns_gate()
    return cns_gate.GateChain(omega=(CnsGate(registry, verifier, subject=subject),))


def verify_to_cns(
    input_artifacts: Artifact | Sequence[Artifact],
    output: Artifact,
    record: TransformationRecord,
    registry: EvidenceRegistry,
    *,
    verifier: IndependentVerifier | None = None,
    subject: str = DEFAULT_SUBJECT,
) -> Any:
    """Run ``IndependentVerifier.verify`` and return the verdict as a CNS verdict.

    Same arguments, same verdict, same absence of side effects as the
    verifier; only the representation differs. Combine the result with
    ``cns.gate.resolve([verdict, ...])``.
    """
    candidate = TransformationCandidate(input_artifacts, output, record)
    return CnsGate(registry, verifier, subject=subject).check(candidate)


def submit_to_cns(
    kernel: ConservationKernel,
    input_artifacts: Artifact | Sequence[Artifact],
    output: Artifact,
    record: TransformationRecord,
    *,
    subject: str = DEFAULT_SUBJECT,
) -> Any:
    """Run ``ConservationKernel.submit`` and return the verdict as a CNS verdict.

    The kernel does exactly what it does for a direct ``submit``: it verifies,
    commits an accepted transformation, and records a rejection. The one
    difference is in how a refusal is *reported*: ``submit`` raises
    ``LedgerError`` when an accepted verification cannot be committed (an
    unregistered parent, a duplicate id), and here that refusal is the
    ``TERMINAL_BREACH`` verdict it is, with the ledger's reason. The kernel's
    own state is the same either way: the accepted report is kept.

    Only ``LedgerError`` is turned into a verdict. Any other error from the
    kernel (for example the ``ValueError`` for a non-finite declaration that
    matches an observed change) propagates unchanged: it is not a ledger
    refusal and is not relabelled as one.

    CNS is checked first, so without it this raises ``CnsNotInstalled``
    before the kernel is touched.
    """
    cns_gate = _cns_gate()
    _require_subject(subject)
    candidate = TransformationCandidate(input_artifacts, output, record)
    try:
        result = kernel.submit(candidate.inputs, candidate.output, candidate.record)
    except LedgerError as exc:
        return _verdict(
            cns_gate,
            gate_name=GATE_NAME,
            position=cns_gate.GatePosition.OMEGA,
            outcome=cns_gate.GateOutcome.TERMINAL_BREACH,
            reason=f"verification accepted but the ledger refused to commit it: {exc}",
            subject=subject,
            content=lambda: _transformation_content(candidate),
        )
    # Here the kernel verified and, if it accepted, committed. An accepted
    # result whose content cannot be digested is still a TERMINAL_BREACH, and
    # the reason must say the ledger holds the output.
    note = (
        "the kernel accepted it and committed the output to the ledger, so the "
        "ledger and this verdict disagree"
        if result.accepted
        else ""
    )
    return _to_cns_result(result, candidate, subject, note)
