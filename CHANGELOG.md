# Changelog

## Unreleased

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
