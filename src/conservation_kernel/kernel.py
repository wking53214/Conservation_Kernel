"""Public Conservation Kernel façade."""

from __future__ import annotations

import hashlib

from collections.abc import Callable, Sequence

from .enums import AuthorityStatus, CanonicalState, EpistemicStatus, TransitionKind
from .errors import LedgerError, SnapshotAuthenticityError, SnapshotIntegrityError, UnguardedKernelError
from .events import EvidenceRecord, RevocationEvent, TransformationRecord, instant
from .ledger import ConservationLedger
from .model import Artifact, _digest, canonical_json, utc_now
from .reconstruction import Reconstruction, ReconstructionEngine
from .registry import EvidenceRegistry
from .result import VerificationResult, _is_undigestable
from .verifier import IndependentVerifier


#: The evidence detail key that carries the SHA-256 of the statement the evidence records. A proposition that cites
#: such a record must say exactly that statement: its text must hash to this value (see `admit_root`).
STATEMENT_DIGEST_KEY = "statement_sha256"


def statement_digest(text: str) -> str:
    """SHA-256 of a statement's UTF-8 text: the value an evidence record's STATEMENT_DIGEST_KEY holds."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ConservationKernel:
    """Compose the verifier, external registry, and append-only ledger.

    This class is intentionally thin. The verifier remains independently
    callable so an experiment can audit a control pipeline without using the
    kernel as its gate.
    """

    version = "0.3.0"

    def __init__(
        self,
        *,
        registry: EvidenceRegistry | None = None,
        verifier: IndependentVerifier | None = None,
        ledger: ConservationLedger | None = None,
        root_guard: Callable[[Artifact], bool] | None = None,
        allow_unguarded_roots: bool = False,
        clock: Callable[[], str] | None = None,
        evidence_guard: Callable[[EvidenceRecord], bool] | None = None,
        refuse_inactive_root_evidence: bool = False,
        require_content_bound: bool = False,
        allow_unguarded_evidence: bool = False,
        allow_untrusted_humans: bool = False,
    ) -> None:
        """`clock` returns the time the kernel decides at (ISO 8601 with offset). Every decision and root admission
        is stamped with it and judged as of it. It defaults to this machine's UTC clock; a deployment should hand in
        the clock of the ledger it writes to, since a time-limited authorization is only as good as that time.

        `root_guard` makes registering a root depend on a permission the caller holds: the ledger asks it
        before adding any initial artifact, whether through `register_root` or `ledger.add_initial`. To guard a
        ledger you pass in, build it with `ConservationLedger(root_guard=...)`.

        A kernel needs a guard. One with none would register any root it admits, with no approved decision
        required, so building it raises `UnguardedKernelError` unless you pass `allow_unguarded_roots=True` to say
        that is deliberate (a test, a tool that never registers roots). The flag is greppable on purpose: it is the
        list of places that have not yet decided what authorizes a root.

        `evidence_guard` makes adding evidence depend on a permission the caller holds: the registry asks it before
        adding any evidence record, whether through `kernel.registry.add_evidence` or any other route to it, and
        about every record a snapshot restores. A kernel needs one too: with none, any caller could add evidence that
        declares itself independent verification and the verifier would count it, so building it raises
        `UnguardedKernelError` unless you pass `allow_unguarded_evidence=True` to say that is deliberate. As with
        `allow_unguarded_roots`, the flag is greppable on purpose. To guard a registry you pass in, build it with
        `EvidenceRegistry(evidence_guard=...)`.

        `allow_untrusted_humans` is the same kind of explicit opt-out for authorizations. A registry with no
        `trusted_humans` cannot tell a human from an actor that labels itself one, so it refuses every authorization
        and delegation unless this is True. It applies to the registry this kernel builds; to set it on a registry you
        pass in, build it with `EvidenceRegistry(allow_untrusted_humans=True)` (or give it `trusted_humans`).

        `require_content_bound` makes the registry refuse an authorization that does not carry the digest of the
        proposition it approves (`AuthorizationEvent.subject_digest`), so no authorization can be reused for other
        words than the ones approved. Off by default: an authorization with a digest is always held to it, and one
        without is judged as before. To set it on a registry you pass in, build it with
        `EvidenceRegistry(require_content_bound=True)`.

        `refuse_inactive_root_evidence` makes `admit_root` refuse a new root whose fact, observation, authority or
        canonical proposition cites evidence that is no longer active, the rule the verifier already applies to a
        transformation. Off by default, so nothing changes until a deployer asks. It is never applied when a snapshot
        is restored: a root admitted while its evidence was active stays admitted if the evidence is withdrawn later."""
        if root_guard is not None and ledger is not None:
            raise ValueError("pass the root guard to the ledger you supply, not to the kernel as well")
        if evidence_guard is not None and registry is not None:
            raise ValueError("pass the evidence guard to the registry you supply, not to the kernel as well")
        self.refuse_inactive_root_evidence = bool(refuse_inactive_root_evidence)
        if require_content_bound and registry is not None:
            raise ValueError("pass require_content_bound to the registry you supply, not to the kernel as well")
        if allow_untrusted_humans and registry is not None:
            raise ValueError("pass allow_untrusted_humans to the registry you supply, not to the kernel as well")
        self._registry = registry or EvidenceRegistry(evidence_guard=evidence_guard,
                                                      require_content_bound=require_content_bound,
                                                      allow_untrusted_humans=allow_untrusted_humans)
        self.clock = clock or utc_now
        self.verifier = verifier or IndependentVerifier()
        self._ledger = ledger or ConservationLedger(root_guard=root_guard)
        if not self.ledger.has_root_guard and not allow_unguarded_roots:
            raise UnguardedKernelError(
                "ConservationKernel built without a root_guard: it would register any root it admits, with no "
                "approved decision required. Pass root_guard=..., or allow_unguarded_roots=True if that is "
                "deliberate."
            )
        if not self.registry.has_evidence_guard and not allow_unguarded_evidence:
            raise UnguardedKernelError(
                "ConservationKernel built without an evidence_guard: any caller could add evidence that declares "
                "itself independent verification, and the verifier would count it. Pass evidence_guard=..., or "
                "allow_unguarded_evidence=True if that is deliberate."
            )
        self.ledger._bind(self.registry.issuer, self.admit_root)
        self.reconstruction = ReconstructionEngine()

    @property
    def registry(self) -> EvidenceRegistry:
        """The evidence registry this kernel was built with. Read-only: replacing it would replace its evidence guard."""
        return self._registry

    @property
    def ledger(self) -> ConservationLedger:
        """The ledger this kernel was built with. Read-only: replacing it would replace its root guard."""
        return self._ledger

    @property
    def has_root_guard(self) -> bool:
        """Whether this kernel registers a root only with a guard's permission. A caller deciding whether to
        trust this kernel with an approval can read this; it cannot be turned off through the kernel's public
        interface after construction (the ledger is read-only). Code running in the same process can still reach
        private attributes and replace the guard: the guards protect against callers outside the process or behind
        the public interface, not against code that shares it. That is a documented limit of in-process checks, not
        something the kernel can prevent."""
        return self.ledger.has_root_guard

    @property
    def root_guard(self) -> Callable[[Artifact], bool] | None:
        """The guard that decides whether a root may be registered, or None. Read it to judge whether it is one you trust."""
        return self.ledger.root_guard

    @property
    def evidence_guard(self) -> Callable[[EvidenceRecord], bool] | None:
        """The guard that decides whether evidence may be added, or None. Read it to judge whether it is one you trust."""
        return self.registry.evidence_guard

    @property
    def require_content_bound(self) -> bool:
        """Whether this kernel's registry refuses an authorization that is not bound to the content it approves."""
        return self.registry.require_content_bound

    @property
    def has_evidence_guard(self) -> bool:
        """Whether this kernel's registry adds evidence only with a guard's permission."""
        return self.registry.has_evidence_guard

    STRONG_EPISTEMIC = frozenset({EpistemicStatus.FACT, EpistemicStatus.OBSERVATION})
    AUTHORITATIVE = frozenset({AuthorityStatus.HUMAN_AUTHORIZED, AuthorityStatus.CANONICAL, AuthorityStatus.EXECUTED})
    CANONICAL_STATES = frozenset({CanonicalState.ACCEPTED, CanonicalState.CANONICAL, CanonicalState.SUPERSEDED,
                                  CanonicalState.REVOKED, CanonicalState.DELETED})

    def admit_root(self, artifact: Artifact, *, as_of: str | None = None) -> tuple[str, ...]:
        """Reasons this artifact may not be registered as a root now; empty if it may. See `_admit_root`."""
        return self._admit_root(artifact, as_of=as_of, restoring=False)

    def _admit_root(self, artifact: Artifact, *, as_of: str | None, restoring: bool) -> tuple[str, ...]:
        """Reasons this artifact may not be registered as a root; empty if it may.

        The constitution constrains transitions, so a root is asserted. But an
        assertion that cites a registry must be backed by it: a reference that
        does not exist, an authoritative or canonical claim with no
        authorization for that proposition, a fact with no evidence, or an
        observation with no source, is a forged origin story, and everything derived from it would inherit
        verified ancestry it never had.

        Authorizations are judged as of `as_of`, or as of the kernel's clock now when it is not given.
        """
        registry = self.registry.at(as_of if as_of is not None else self._now())
        reasons: list[str] = []
        for prop in artifact.propositions:
            missing = self.registry.missing_refs(prop.evidence_refs)
            if missing:
                reasons.append(f"{prop.proposition_id}: evidence_refs not in registry: {list(missing)}")
            if prop.epistemic_status in self.STRONG_EPISTEMIC:
                cited = [self.registry.evidence(ref) for ref in prop.evidence_refs if ref not in missing]
                if cited and not any(item is not None and item.subject_id == prop.proposition_id for item in cited):
                    # A root has no parents, so its own id is the only subject that counts, and "*" counts for none.
                    reasons.append(f"{prop.proposition_id}: a root {prop.epistemic_status.value} must cite evidence about "
                                   f"this proposition; {[item.evidence_id for item in cited if item is not None]} "
                                   "support others")
            inactive = self.registry.inactive_refs(prop.evidence_refs)
            if self.refuse_inactive_root_evidence and not restoring and inactive and (prop.epistemic_status in self.STRONG_EPISTEMIC or prop.authority is not AuthorityStatus.NONE
                             or prop.canonical_state is CanonicalState.CANONICAL):
                # The verifier's own rule (INACTIVE_EVIDENCE), applied at the other door into the ledger.
                reasons.append(f"{prop.proposition_id}: strong/canonical root proposition cites inactive evidence: {list(inactive)}")
            for ref in prop.evidence_refs:
                record = self.registry.evidence(ref)
                bound = None if record is None else record.detail.get(STATEMENT_DIGEST_KEY)
                if bound is not None and str(bound) != statement_digest(prop.text):
                    reasons.append(f"{prop.proposition_id}: its text is not the statement of evidence {ref}, which it cites")
            dangling = tuple(ref for ref in prop.authorization_refs if self.registry.authorization(ref) is None)
            if dangling:
                reasons.append(f"{prop.proposition_id}: authorization_refs not in registry: {list(dangling)}")
            if prop.authority in self.AUTHORITATIVE and not self._authorized(
                    prop.authorization_refs, prop.proposition_id, TransitionKind.AUTHORITY_ESCALATION, prop.authority.value,
                    subject_digest=prop.canonical_digest, registry=registry):
                reasons.append(f"{prop.proposition_id}: authority {prop.authority.value} has no authorization for this proposition")
            if prop.canonical_state in self.CANONICAL_STATES and not self._authorized(
                    prop.authorization_refs, prop.proposition_id, TransitionKind.CANONICALIZATION, prop.canonical_state.value,
                    subject_digest=prop.canonical_digest, registry=registry):
                reasons.append(f"{prop.proposition_id}: canonical state {prop.canonical_state.value} has no canonicalization for this proposition")
            if prop.epistemic_status in self.STRONG_EPISTEMIC and not (prop.source_refs or prop.evidence_refs):
                reasons.append(f"{prop.proposition_id}: a root {prop.epistemic_status.value} must cite a source or evidence")
            elif prop.epistemic_status is EpistemicStatus.FACT and not prop.evidence_refs:
                reasons.append(f"{prop.proposition_id}: a root FACT must cite evidence in the registry; "
                               "a source alone supports an OBSERVATION or an INFERENCE, not a FACT")
        return tuple(reasons)

    def _now(self) -> str:
        """The kernel's clock, refused unless it is a time this kernel can judge by."""
        moment = self.clock()
        instant(moment, "clock")
        return moment

    def _authorized(self, refs, subject_id: str, kind: TransitionKind, to_value: str, *,
                    subject_digest: str | None = None, registry=None) -> bool:
        registry = registry if registry is not None else self.registry.at(self._now())
        for ref in refs:
            event = registry.authorization(ref)
            if event is None:
                continue
            if (event.subject_id == subject_id and event.transition_kind is kind and event.to_value == to_value
                    and registry.binds(event, subject_digest)):
                return True
        return False

    def revoke(self, event: RevocationEvent) -> None:
        """Record a revocation as of this kernel's clock (see `EvidenceRegistry.add_revocation`)."""
        self.registry.add_revocation(event, recorded_at=self._now())

    def register_root(self, artifact: Artifact) -> None:
        # The ledger asks `admit_root` itself, as of the time given here, so this door and `ledger.add_initial` agree.
        self.ledger.add_initial(artifact, admitted_at=self._now())

    def submit(
        self,
        input_artifacts: Artifact | Sequence[Artifact],
        output: Artifact,
        record: TransformationRecord,
    ) -> VerificationResult:
        # An input that shares an id with a ledger artifact must be that artifact. Otherwise the verifier would judge
        # a "before" the caller wrote, and the ledger would record a child of a parent that never looked like that.
        for item in (input_artifacts,) if isinstance(input_artifacts, Artifact) else tuple(input_artifacts):
            held = self.ledger.get(item.artifact_id)
            if held is not None and held != item:
                raise LedgerError(f"input artifact {item.artifact_id} is not the artifact the ledger holds under that id")
        result = self.verifier.verify(input_artifacts, output, record, self.registry.at(self._now()))
        if result.accepted:
            try:
                self.ledger.commit(output, record, result)
            except LedgerError:
                # The verification happened and was accepted; the ledger could
                # not take it (unregistered parent, duplicate id). Before this
                # the accepted result vanished with the exception (measured
                # 2026-09-08), so a verification that occurred left no trace.
                # Keep the report, then let the caller see the ledger's refusal.
                self._keep_report(result, record, output)
                raise
        else:
            self._keep_report(result, record, output)
        return result

    def _keep_report(self, result: VerificationResult, record: TransformationRecord, output: Artifact) -> None:
        # A result for a record that cannot be digested has no proof, so the ledger cannot keep it as a report.
        # Nothing is kept for it; the verdict built on it says the transformation was not committed.
        if result.proof is None and _is_undigestable(record):
            return
        self.ledger.record_rejection(result, record, output)

    def reconstruct(self, artifact_id: str) -> Reconstruction:
        return self.reconstruction.reconstruct(self.ledger, artifact_id)

    # -- persistence -------------------------------------------------------------

    SNAPSHOT_VERSION = "1.0.0"

    def snapshot(self) -> dict:
        """Everything needed to continue after a restart, plus a digest of it."""
        body = {
            "snapshot_version": self.SNAPSHOT_VERSION,
            "kernel_version": self.version,
            "ledger": self.ledger.snapshot(),
            "registry": self.registry.snapshot(),
        }
        body["snapshot_digest"] = _digest(canonical_json(body))
        return body

    @classmethod
    def from_snapshot(cls, snapshot: dict, *, trusted_humans=None, reverify: bool = True, signer=None,
                      root_guard: Callable[[Artifact], bool] | None = None,
                      allow_unguarded_roots: bool = False,
                      clock: Callable[[], str] | None = None,
                      require_bounded: bool = False,
                      evidence_guard: Callable[[EvidenceRecord], bool] | None = None,
                      refuse_inactive_root_evidence: bool = False,
                      require_content_bound: bool = False,
                      allow_unguarded_evidence: bool = False,
                      allow_untrusted_humans: bool = False,
                      allow_unguarded_restore: bool = False) -> "ConservationKernel":
        """A kernel continuing from `snapshot()`.

        The digest is checked first (corruption). Then, with `reverify`, every
        root is re-admitted and every transformation is re-verified against
        the restored registry, so a lineage that was written into the file
        by hand fails the same way it would have failed live. What this does
        not do is authenticate the file: a snapshot that re-verifies is one
        the constitution would have accepted, not one this kernel is known to
        have produced. That needs a signature the deployer holds.

        A snapshot that holds roots is refused (`UnguardedKernelError`) unless a `root_guard` is passed or
        `allow_unguarded_restore=True` says restoring without one is deliberate. The guard is only required to be
        configured: it is not run on the restored roots (a one-use permission would be spent), so `reverify` and the
        signature, not the guard, are what vouch for them. Likewise the registry refuses authorizations and
        delegations unless `trusted_humans` is given or `allow_untrusted_humans=True`.
        """
        body = dict(snapshot)
        signature = body.pop("signature", None)
        recorded = body.pop("snapshot_digest", None)
        if recorded is not None and _digest(canonical_json(body)) != recorded:
            raise SnapshotIntegrityError("snapshot digest does not recompute; the file was altered")
        if signer is not None:
            # 0.3.0: a loader that holds a key expects the file to be signed
            # by it. An unsigned file, or one signed by another key, is not
            # this deployment's kernel, however well it re-verifies.
            from .signing import check_signature
            problem = check_signature(signer, recorded or "", signature)
            if problem:
                raise SnapshotAuthenticityError(f"snapshot not authenticated: {problem}")
        registry = EvidenceRegistry.restore(body.get("registry", {}), trusted_humans=trusted_humans,
                                            require_bounded=require_bounded, evidence_guard=evidence_guard,
                                            require_content_bound=require_content_bound,
                                            allow_untrusted_humans=allow_untrusted_humans)
        ledger = ConservationLedger.restore(body.get("ledger", {}), root_guard=root_guard,
                                            allow_unguarded_restore=allow_unguarded_restore)
        kernel = cls(registry=registry, ledger=ledger, allow_unguarded_roots=allow_unguarded_roots, clock=clock,
                     refuse_inactive_root_evidence=refuse_inactive_root_evidence,
                     allow_unguarded_evidence=allow_unguarded_evidence)
        if reverify:
            kernel.reverify()
        return kernel

    def reverify(self) -> None:
        """Re-admit every root and re-verify every transformation now in the ledger, each as of when it was first
        accepted. One recorded without a time (written before times existed, or straight to the ledger) is judged as
        of now and given that time, once, so a revocation recorded later cannot reach back over it. A recorded time
        that is unreadable or later than now is refused: no decision can have been made in the future."""
        now = self._now()
        unstamped_roots: dict[str, str] = {}
        unstamped_transformations: dict[str, str] = {}
        for artifact in self.ledger.artifacts():
            if not artifact.parent_artifact_ids:
                as_of = self._recorded(self.ledger.admitted_at(artifact.artifact_id), now, f"root {artifact.artifact_id}")
                if self.ledger.admitted_at(artifact.artifact_id) is None:
                    unstamped_roots[artifact.artifact_id] = as_of
                reasons = self._admit_root(artifact, as_of=as_of, restoring=True)
                if reasons:
                    raise SnapshotIntegrityError(f"root {artifact.artifact_id} would not be admitted: " + "; ".join(reasons))
        for record in self.ledger.transformations():
            try:
                inputs = [self.ledger.artifact(i) for i in record.input_artifact_ids]
                output = self.ledger.artifact(record.output_artifact_id)
            except KeyError as e:
                raise SnapshotIntegrityError(f"transformation {record.transformation_id} references an artifact not in the ledger: {e}") from e
            stamp = self.ledger.verified_at(record.transformation_id)
            as_of = self._recorded(stamp, now, f"transformation {record.transformation_id}")
            if stamp is None:
                unstamped_transformations[record.transformation_id] = as_of
            result = self.verifier.verify(inputs, output, record, self.registry.at(as_of))
            if not result.accepted:
                raise SnapshotIntegrityError(
                    f"transformation {record.transformation_id} does not re-verify: "
                    + "; ".join(f"{v.code}" for v in result.violations)
                )
        self.ledger._record_times(admitted=unstamped_roots, verified=unstamped_transformations)

    @staticmethod
    def _recorded(stamp: str | None, now: str, what: str) -> str:
        """The time to re-judge `what` at: its recorded time, checked, or `now` when it has none."""
        if stamp is None:
            return now
        try:
            moment = instant(stamp, "recorded time")
        except Exception as exc:
            raise SnapshotIntegrityError(f"{what} carries an unreadable time {stamp!r}") from exc
        if moment > instant(now, "clock"):
            raise SnapshotIntegrityError(f"{what} is recorded at {stamp}, in the future of this kernel's clock ({now})")
        return stamp

    def save(self, path, *, signer=None) -> None:
        """Write the snapshot; with a signer, sign its digest with the deployer's key."""
        from pathlib import Path
        body = self.snapshot()
        if signer is not None:
            from .signing import signature_block
            body["signature"] = signature_block(signer, body["snapshot_digest"])
        Path(path).write_text(canonical_json(body), encoding="utf-8")

    @classmethod
    def load(cls, path, **kwargs) -> "ConservationKernel":
        import json
        from pathlib import Path
        return cls.from_snapshot(json.loads(Path(path).read_text(encoding="utf-8")), **kwargs)
