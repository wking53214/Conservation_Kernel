# Provenance

## What this repository is

Conservation Kernel is an **active, from-scratch engineering experiment**. It is
a deliberately small, hostile, independently testable mechanism built to probe
one hypothesis:

> Can machine-mediated transformations be evaluated for preservation of
> protected epistemic and provenance distinctions, without the evaluator
> having to decide whether any claim is true?

It is **not** an archived AI-chat transcript, and it does not follow this
account's `PROVENANCE.md` + `TRANSCRIPT.md` archival convention. There is no
source conversation to preserve. The code here is written, tested, and revised
as normal software. A future housekeeping pass should treat it as a live
project — fix real bugs, keep the suite green — not as evidentiary material to
be left untouched.

## Origin

The project was created after a reconnaissance pass over sibling repositories
(`CCC`, `Triad-42`, `innovation_os`, `sentinel_os`, `GSA-815`, `synapsis`,
`resume_os`, `Ecology`) to check whether any existing checkout was a suitable
home for a cross-repository transition verifier. The conclusion — recorded in
[`docs/ARCHITECTURE_ASSESSMENT.md`](docs/ARCHITECTURE_ASSESSMENT.md) — was to
build a dedicated project that imports none of them, so that a passing test
demonstrates independent verification rather than correct use of an existing
manager.

## Timeline

| Date | Milestone |
| --- | --- |
| 2026-08-17 | `d6c67dc` — initial hostile baseline: typed artifact/proposition model, independent verifier, external evidence/authorization registry, append-only in-memory ledger, reconstruction engine, 10-boundary control/treatment experiment. |
| 2026-08-18 | `2260320` freeze, then hostile attacks #7 (cross-subject authorization replay), #8 (recursive self-verification), #9 (provenance forgery) added to the corpus and test suite. |
| 2026-08-24 | `d91e5cd`, `6290f4d` — README expanded into a full conceptual overview. |
| 2026-08-27 | Housekeeping: `LICENSE` (Apache-2.0), this file, description alignment, README tightened; hostile attacks #11/#12/#14 landed (kernel already enforced them — test-only additions). Attacks #10 and #13 deferred pending an invariant design decision (see below). |

## What is real vs. aspirational

The repository is candid about its own limits. Do not infer more from the
README's scope than the following documents support:

- [`docs/REPORT.md`](docs/REPORT.md) — every claim classified as
  `TEST-VERIFIED`, `FALSIFIED`, or `UNVERIFIED`. Notably `FALSIFIED`: "the
  mechanism independently verifies truth" and "a library alone prevents bypass
  by a downstream system".
- [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) — the in-memory ledger is
  append-only *by API only*, not tamper-proof; SHA-256 is used for
  deterministic identity and change detection, **not** for signatures,
  custody, or authenticity.
- [`docs/HOSTILE_REVIEW.md`](docs/HOSTILE_REVIEW.md) — 20 adversarial
  questions answered against the implementation, several with `FALSIFIED` or
  `UNVERIFIED`.
- [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) — explicit out-of-scope list.

Verified state as of 2026-08-27: `python3 -m pytest -q` → 47 passed; the code
has no runtime dependencies outside the standard library.

## Adversarial audit history

The hostile corpus in `src/conservation_kernel/experiments.py` and the
`tests/test_attack_*.py` files are the record of attempted bypasses. Each
attack tries to produce a *false acceptance*; a passing test means the
invariant held and the transformation was rejected.

Two attacks are **deferred**, not solved, and are kept out of the suite so it
does not carry a misleading green:

- **#10 cross-subject evidence replay** — attaching evidence whose registry
  subject is proposition A to proposition B. `_check_evidence_refs` and
  `_check_evidence_change` currently test only presence and `active`, not the
  evidence record's `subject_id`, so a cross-subject attachment is accepted
  today when no epistemic promotion is involved. Catching it requires a new
  subject-binding invariant with real blast radius (`has_active_evidence`
  already enforces subject binding elsewhere), so it is a design decision, not
  a mechanical fix.
- **#13 historical-content mutation** — silently changing the `text` of a
  `FACT` proposition whose temporal scope is `HISTORICAL`. The verifier
  observes proposition content as a SHA-256 digest and has no rule protecting
  historical content specifically; a correctly declared content change is
  accepted as `PASS_WITH_DECLARED_TRANSFORMATION`. Whether historical content
  should be a protected dimension is an open invariant question.

## Related investigation

On 2026-08-27 an external candidate architecture (an event-sourcing / CQRS
coordinator with a per-entity hash chain and a versioned governance manifest)
was evaluated against this kernel. Verdict: **harvest tests, do not
integrate**. The comparison surfaced two gaps worth tracking here:

1. **Ledger continuity as a cryptographic property.** The ledger is
   append-only by dict discipline only; reorder / truncation is undetectable.
   Already acknowledged in `HOSTILE_REVIEW.md` #6.
2. **Decisions bound to a versioned ruleset.** A `VerificationResult` and an
   `AuthorizationEvent` carry no identifier for the invariant set in force
   when they were produced.

Neither is implemented. Both are candidates for a future `INVARIANTS.md` /
`THREAT_MODEL.md` revision.
