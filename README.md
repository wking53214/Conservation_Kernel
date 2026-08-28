# Conservation Kernel

## Adversarial enforcement of epistemic conservation

The Conservation Kernel is a small, independently testable mechanism for
checking whether a machine-mediated transformation preserved the properties
that were supposed to remain conserved.

Its question is **not**:

> "Is this claim true?"

It is:

> "Did this transformation preserve provenance, evidence, authority,
> certainty, and historical state — or did it silently change one of them?"

A transformation can produce plausible-looking output while quietly promoting
an inference to a fact, detaching a claim from its source, or rewriting a
historical record. The kernel exists to make those changes detectable at the
transformation boundary.

---

## Install and run

Python 3.11+, no runtime dependencies outside the standard library.

```bash
python3 -m pip install -e ".[dev]"      # dev install (pytest only)

python3 -m pytest -q                     # the test + hostile-attack suite
PYTHONPATH=src python3 experiments/run_experiment.py   # control/treatment experiment
```

---

## Repository layout

```
src/conservation_kernel/
    enums.py            closed vocabularies (epistemic status, origin, authority, ...)
    model.py            immutable Artifact / Proposition / envelope types + canonical hashing
    events.py           DeclaredChange, AuthorizationEvent, EvidenceRecord, TransformationRecord
    registry.py         EvidenceRegistry — the external witness / trust boundary
    verifier.py         IndependentVerifier — recomputes observed changes, never trusts declarations
    result.py           VerificationResult (PASS / PASS_WITH_DECLARED_TRANSFORMATION / REJECT / UNVERIFIABLE)
    ledger.py           append-only (by API) artifact + transformation store
    reconstruction.py   rebuild history and per-proposition timelines from the ledger
    kernel.py           ConservationKernel façade: register_root -> submit -> reconstruct
    experiments.py      deterministic hostile corpus + the control/treatment experiment
tests/                  unit tests and numbered hostile-attack regressions
docs/                   architecture assessment, model, invariants, threat model, hostile review
experiments/            executable experiment entrypoint and recorded metrics
```

---

## How it works

The kernel operates over explicit, immutable **input** and **output**
artifacts plus a **declared transformation** and **external registries**:

```
    IMMUTABLE INPUT ARTIFACT
          +  DECLARED TRANSFORMATION   (what was supposed to change)
          +  OBSERVED EFFECTS          (what the verifier recomputes independently)
          +  EXTERNAL EVIDENCE / AUTHORIZATION REGISTRY
                     │
                     ▼
          CONSERVATION EVALUATION
                     │
              ┌──────┴──────┐
           PRESERVED     VIOLATED
              │             │
              ▼             ▼
           ACCEPT         REJECT
```

- **Immutable input/output.** Comparison is against fixed representations with
  deterministic SHA-256 identity, not mutable application state.
- **Declared vs. observed.** A transformation declares what it intended to
  change. The verifier recomputes what actually changed, field by field, and
  requires the two to match — every observed change must be declared, and
  every declared change must be observed.
- **External registries.** Evidence and human authorization live in a
  separate `EvidenceRegistry`, not inside the artifact. A transformer can
  *name* an authorization ID, but only a registered event created by a human
  actor satisfies a human-authorization check.
- **Fail closed.** If a required condition cannot be established, the result
  is not `PASS`.

Content may change freely; when it does, the result explicitly reports
semantic content equivalence as **unverified** rather than implying the
meaning was preserved.

---

## What is conserved

The verifier treats these proposition-level distinctions as protected. Each
may change only when the output, declaration, and registry records jointly
satisfy the relevant transition rule:

| Property | Silent change that is rejected |
| --- | --- |
| **Provenance** | source references stripped or substituted |
| **Evidence** | support removed while the claim still presents as supported; unregistered evidence added |
| **Authority** | `PROPOSED` → `HUMAN_AUTHORIZED` / `CANONICAL` without a matching human authorization |
| **Certainty** | uncertainty collapsed without independent verification |
| **Epistemic status** | `INFERENCE`/`ESTIMATED`/`CONFLICTED` → `FACT`/`OBSERVATION`; `SIMULATED` → historical fact |
| **Human origin** | machine-originated content relabelled as human-originated |
| **Historical / temporal state** | `occurred_at` / `observed_at` / scope changed without an explicit temporal transition |
| **Lineage** | output parents that are not exactly the declared inputs; new propositions with no root in the input |
| **Functional contract** | required properties dropped or changed without a functional-validation record |

Model consensus, citations, execution records, and an actor's self-report are
explicitly **not** accepted as independent verification. The full list is in
[`docs/INVARIANTS.md`](docs/INVARIANTS.md).

---

## Hostile baseline

The kernel is intentionally adversarial. It is not built to make
transformations look safe; it is built to try to falsify the claim that they
are.

The test suite reflects this. A strong result is not "test passed" — it is:

```
HOSTILE TRANSFORMATION ATTEMPTED  ->  INVARIANT HELD  ->  REJECTED
```

`tests/test_attack_*.py` and the corpus in `experiments.py` are numbered
attempts at *false acceptance*: cross-subject authorization replay, recursive
self-verification, provenance forgery, evidence deactivation, machine-to-human
reclassification, and more. `tests/test_transactional_rollback.py` covers a
related property — a rejected transformation must not mutate the ledger, and a
legitimate transformation must still succeed afterwards.

Two attacks (#10 cross-subject evidence replay, #13 historical-content
mutation) are documented in [`PROVENANCE.md`](PROVENANCE.md) as **deferred**:
they require an invariant design decision and are deliberately kept out of the
suite rather than carried as a misleading pass.

---

## The experiment

`experiments/run_experiment.py` runs the same ten transformation boundaries
through two pipelines:

```
control:   artifact -> transformer -> next artifact
treatment: artifact -> transformer -> kernel -> next artifact
```

At five boundaries the same hostile mutations are attempted. The control (with
ordinary artifact identity, hashes, timestamps, and a transformation log, but
no conservation gate) accepts them. The treatment records and rejects all
five, then performs the legitimate transformation so it still reaches ten
accepted transformations, and finally reconstructs the full history from the
ledger without embedding the original content in every downstream artifact.

The run is deterministic and uses simulated transformers. It demonstrates the
mechanics of measurement, not a population-level claim about real systems.

---

## Scope and boundaries

**The kernel does not** determine external-world truth, and it is not a fact
checker, a truth oracle, a complete authorization system, a production
database, an identity provider, or an AI-governance platform.

**Local vs. universal enforcement.** The kernel enforces conservation at the
boundary where it is actually invoked. A caller who never submits a
transformation stays outside the mechanism entirely. Universal enforcement
would require a mandatory transport/gateway boundary, which this library is
not. This limitation is stated, not hidden — see [`docs/REPORT.md`](docs/REPORT.md),
where that claim is classified `FALSIFIED`. A working reference gateway built
on this kernel is described in [`docs/GATEWAY.md`](docs/GATEWAY.md).

**Cryptography.** SHA-256 is used here for deterministic identity and change
detection only — not for signatures, custody, authenticity, or tamper-proof
storage. The ledger is append-only *by API*; it is not a durable tamper-proof
store. See [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) and
[`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md).

**Relationship to governance.** A governance system decides *which* properties
are protected, *who* has authority, and *what* transitions are permitted. The
kernel is the lower-level mechanism that checks whether a transformation
actually preserved those properties. It is the enforcement primitive, not the
enforcement architecture.

---

## Documentation

| File | Contents |
| --- | --- |
| [`PROVENANCE.md`](PROVENANCE.md) | what this repo is, its history, deferred work, and what is real vs. aspirational |
| [`docs/ARCHITECTURE_ASSESSMENT.md`](docs/ARCHITECTURE_ASSESSMENT.md) | why a dedicated project, and the sibling-repo reconnaissance behind it |
| [`docs/MODEL.md`](docs/MODEL.md) | the artifact/proposition model and result semantics |
| [`docs/INVARIANTS.md`](docs/INVARIANTS.md) | the enforced invariants, enumerated |
| [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) | assumptions and explicit out-of-scope items |
| [`docs/GATEWAY.md`](docs/GATEWAY.md) | the transport boundary, its reference implementation, and what makes a gateway sound |
| [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) | what a passing result does and does not mean |
| [`docs/HOSTILE_REVIEW.md`](docs/HOSTILE_REVIEW.md) | 20 adversarial questions answered against the implementation |
| [`docs/REPORT.md`](docs/REPORT.md) | per-claim classification (`TEST-VERIFIED` / `FALSIFIED` / `UNVERIFIED`) |
| [`docs/EXPERIMENT.md`](docs/EXPERIMENT.md) | the control/treatment experiment design |

---

## Status

An experimental, independently testable hostile baseline. Its value is a
concrete, testable answer to a narrow question — *can machine-mediated
transformations be evaluated for preservation of protected epistemic and
provenance distinctions?* — and a foundation from which mandatory
transformation-boundary enforcement could be built.

## License

Apache License 2.0 — see [`LICENSE`](LICENSE).
