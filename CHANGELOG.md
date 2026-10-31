# Changelog

## Unreleased

- `ConservationKernel.submit` refuses (`LedgerError`) an input artifact that shares an id with a ledger artifact but is
  not that artifact. It used to verify whatever "before" the caller handed in, so a doctored copy of a registered root
  (an INFERENCE shown as a FACT with real evidence) let a FACT child of an INFERENCE root into the ledger, which the
  next restore then refused to reload. Inputs not in the ledger are unchanged (the commit still refuses them).
  `ConservationLedger.get(artifact_id)` returns the held artifact or None.
- A kernel now refuses to be built without an evidence guard: `ConservationKernel(...)` and `from_snapshot(...)` raise
  `UnguardedKernelError` unless `evidence_guard=...` is given (or the registry you pass in has one) or
  `allow_unguarded_evidence=True` says that is deliberate, mirroring `allow_unguarded_roots`. With a root guard but no
  evidence guard, any caller could add INDEPENDENT_VERIFICATION evidence that declares itself independent and the
  verifier would count it. **Breaking:** code that builds a kernel with no evidence guard must pass the flag. A bare
  `EvidenceRegistry` is unchanged.
- `AuthorizationEvent(subject_digest=...)` binds an authorization to the words it approves. One authorization for p-1
  becoming `HUMAN_AUTHORIZED` used to admit both "Refund customer $10." and "Refund customer $10,000,000.", because
  matching used only the subject id, the kind of change and the target value. `Proposition.canonical_digest` (id, text
  and conditions, not the status an authorization is about to change) is the value to bind to. When an authorization
  carries a digest it must equal that of the proposition it is used for, at root admission, in every verifier check,
  and for a new proposition's authority and canonical state; a caller that does not name the content cannot use it.
  The field is optional, round-trips in snapshots and is absent from the dict when unset, so existing digests do not
  change. `ConservationKernel(require_content_bound=True)` (or `EvidenceRegistry(require_content_bound=True)`) refuses an
  authorization with no digest, live and on restore. Default `False`.
- `ledger.add_initial` on a ledger a kernel owns applies the kernel's `admit_root`, before the root guard, so a root that
  cites evidence or authorizations the registry does not hold is refused through either door; it used to register
  through `kernel.ledger.add_initial` although `register_root` refused it. `register_root` now delegates to it. A ledger
  no kernel owns has no registry to check against and is unchanged.
- `ConservationLedger.commit` takes only a result the verifier produced. A result is a plain object a caller can write,
  so a hand-built `PASS` used to commit a child the verifier rejects (an INFERENCE lifted to a canonical FACT on
  authorization refs that do not exist). `IndependentVerifier.verify` now attaches a proof (`VerificationResult.proof`,
  never serialized or compared) over the result, the record, the output and the registry it ran against. `commit`
  refuses a result whose proof is missing or does not check, and a ledger a kernel owns also refuses one reached
  against any other registry. The public path stays `ConservationKernel.submit`. A ledger no kernel owns takes any
  verifier-produced result, and a custom verifier must return what `IndependentVerifier.verify` gives it, or `submit`
  cannot commit its results.
- `CnsRootAdmissionGate(kernel, require_evidence_guard=True)` refuses (`TERMINAL_BREACH`) a kernel built without an
  evidence guard, the way `require_guard=True` does for the root guard, so a roster that issues approvals can insist
  the kernel's registry will not take evidence from just any caller. Default `False`: the gate judges exactly as
  before, and the two flags are independent.
- `EvidenceRegistry(evidence_guard=...)` and `ConservationKernel(evidence_guard=...)`: an optional caller permission for
  adding evidence, the way `root_guard` is for roots. The guard is asked with the record and permits only by answering
  exactly `True`; a raise or any other answer refuses with `InvalidEvent` and leaves the registry unchanged. A
  duplicate id is refused before the guard is asked, so a one-use permission is not spent on it. Evidence restored
  from a snapshot is put to the guard too: it is in place before the first record loads, and a record it refuses
  refuses the whole restore, so a file cannot plant evidence the guard would have refused.
  `has_evidence_guard` says whether one is in place. With none, a registry behaves exactly as before; passing a guard and a
  registry to the kernel together is a `ValueError`, as it is for the root guard and a ledger. (A kernel now needs
  one, or `allow_unguarded_evidence=True`; see above.)
- The kernel stamps when it decided. `ConservationKernel(clock=...)` (default:
  this machine's UTC clock) supplies the time of every decision and root
  admission; `VerificationResult.verified_at` and the ledger's
  `admitted_at` / `verified_at` keep it, snapshots carry it, and a restore
  re-verifies each transformation and re-admits each root as of its stamp. The
  kernel hands the verifier `registry.at(time)`, a time-bound view, so a
  verifier with the old four-argument `verify` still works. Unstamped results
  and ledgers keep their old shape.
- `AuthorizationEvent(valid_from=..., valid_until=...)`: an authorization can
  hold for a half-open window (ISO 8601 with a UTC offset). Outside it, or with
  no time to judge by, it does not count. An open-ended one behaves as before.
- `RevocationEvent` and `ConservationKernel.revoke()`: a human the registry
  trusts ends an authorization or delegation from when it is recorded, or a
  later `effective_at`. A revocation dated before it was recorded is refused.
- `DelegationEvent`: a trusted human lets a named delegate issue
  authorizations (`under_delegation`) for listed subjects, kinds of change and
  target values, within a window and until revoked. Re-delegation only if
  allowed, only narrower, at most `MAX_DELEGATION_DEPTH` (3) links; revoking a
  link cuts off everything beneath it.
- `EvidenceRegistry(require_bounded=True)` (default off) refuses an
  authorization or delegation with no end, live and on restore.
- A delegated authorization backs a new proposition only if it names that very
  proposition, not merely a parent of it.
- History with no time (written before times existed) is judged as of its first
  reload and given that time once. A recorded time that is unreadable or later
  than the kernel's clock is refused on reload. The kernel refuses a clock that
  does not return an ISO 8601 time with an offset.
- `CnsGate(..., clock=...)` and `verify_to_cns(..., clock=...)`: judge as of a
  clock, to agree with the kernel on time-limited authorizations. Without one
  they judge exactly as the verifier does on the registry given.
- Compatibility: a registry subclass that overrides `has_authorization` must
  accept `as_of`; a custom verifier now receives a `RegistryAt` view (it keeps
  the registry's lookups and read-only settings). A `VerificationResult` from
  the kernel now carries its time, so two kernels with different clocks give
  unequal results for the same submission.
- A root `FACT` must cite evidence in the registry (`evidence_refs`). A source
  alone no longer admits a FACT: it supports an `OBSERVATION` or an
  `INFERENCE`. An `OBSERVATION` root still needs only a source or evidence.
  Breaking for a caller that registered FACT roots on a source alone.
- `ConservationKernel(root_guard=...)` and `ConservationLedger(root_guard=...)`:
  an optional permission check, handed in by the caller, that the ledger asks
  before adding any initial artifact, through `register_root` or through
  `ledger.add_initial` directly. Only an answer of `True` permits; a raise or
  anything else refuses. It is asked last, after the kernel's own admission
  and the duplicate-id check, so a one-shot permission is not spent on a root
  that would be refused anyway. Restoring a snapshot does not ask it. The
  kernel imports nothing to build a guard; a composition layer supplies one.
- `kernel.has_root_guard` and `ledger.has_root_guard`: whether a kernel registers
  a root only with a guard's permission. `CnsRootAdmissionGate(kernel,
  require_guard=True)` refuses a kernel built without one, so a roster that
  issues approvals can insist the kernel will actually ask. Default is
  `False`, the old behaviour.
- Breaking: a `ConservationKernel` must be built with a root guard. Building one
  with none raises `UnguardedKernelError`, because it would register any root it
  admits with no approved decision required. Pass `root_guard=...`, or pass
  `allow_unguarded_roots=True` to say that is deliberate (a test, a tool that
  never registers roots). The flag is greppable on purpose: it marks every place
  that has not yet decided what authorizes a root. `from_snapshot` and `load`
  take the same two arguments, and `ConservationLedger.restore` takes
  `root_guard`; roots already in a snapshot are not put to the guard. This
  replaces the DeprecationWarning released a day earlier (#19), which was only a
  day old: callers that pin a commit are unaffected until they bump, and a
  bump now needs one of the two arguments.

- `Proposition.conditions`: an optional list of the circumstances a claim
  holds under. A transformation may add a condition. Dropping or rewording
  one is `UNAUTHORIZED_SCOPE_WIDENING`, and a new proposition that leaves out
  a parent's condition is `CONDITION_DROPPED_IN_DERIVATION`, unless a human
  `SCOPE_WIDENING` authorization (new `TransitionKind`) covers exactly that
  change. Condition changes are a new protected `Dimension.SCOPE` and must be
  declared like any other. A reworded condition counts as dropped: the
  verifier does not judge whether two wordings mean the same thing.
- Backward compatible: `conditions` is left out of `to_dict()` when empty and
  is optional in `from_dict()`, so every existing artifact keeps its digest
  and every existing snapshot loads and re-verifies unchanged.
- Source: innovation_os's `CompressionConstraint` (summaries must not widen
  scope), defined there but never called, carried over ahead of that
  repository's retirement. Only the scope axis is enforced; certainty and
  permanence were already covered by `UNCERTAINTY_COLLAPSE` and
  `UNAUTHORIZED_TEMPORAL_CHANGE`, and significance needs human judgment.
- `ConservationLedger.commit` refuses an output with no parents. Such an
  artifact is a root, and roots enter through `add_initial`, which asks the root
  guard; `commit` took any output whose result said PASS, so a caller holding the
  ledger could write a result by hand and plant a root past a closed guard.
  `ConservationKernel.submit` already rejected a transformation with no inputs,
  so only the direct ledger call changes. A snapshot holding such a root already
  failed to reload; now it cannot be made live either.

## 0.1.0 (2026-09-07)

First versioned release. The kernel has been in use as a pinned git
dependency of `sentinel_os` (every governed decision routes through its
conservation boundary), as an installed package in `observe-perceive`'s
governance chain, and by `GEMS`'s transport experiments.

What this release is:

- `ConservationKernel`: `register_root` -> `submit` -> `reconstruct` facade
  over an `EvidenceRegistry`, an `IndependentVerifier` and an append-only
  `ConservationLedger`.
- The verifier recomputes observed changes from artifact digests and never
  trusts a declaration: an undeclared change to a protected dimension, a
  declared hash that does not match the artifact, or a self-verification are
  each refused with a named violation.
- A replay (duplicate output artifact id) or an unregistered parent is refused
  by the ledger with `LedgerError`.
- Python 3.11+, no runtime dependencies. `pytest` for development only.

Verified for this release (external audit, 2026-09-07):

- 52 tests pass in a fresh clone with no sibling repository present.
- The wheel installs and imports from a clean virtual environment.
- No unused imports, no bare excepts (ruff 0.15.22, now a CI gate).

Known limits, stated rather than implied:

- `build_ground_truth()` and the hostile corpus in `experiments.py` are
  synthetic and authored alongside the verifier. `TOUCHSTONE`, a separate
  repository, holds the only non-synthetic ground truth in the ecosystem.
- Ledger refusals are raised, not returned as `VerificationResult`; consumers
  that want a uniform verdict shape must catch `LedgerError` (observe-perceive's
  adapter does).
