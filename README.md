# Conservation_Kernel

Independently testable **hostile baseline** for transformation conservation. Version as tagged (`CHANGELOG.md`; live path pins `25145aa` / 0.3.0). Stdlib only. Python ≥ 3.11.

## 1. Pipeline Position & Role

**CONSERVATION.** After policy decision, before trusted downstream use / execution.

```text
Admission → Observe/Keys → Locks → PERCEIVE → Decision
    → Conservation (this repo)
    → Execution → Custody
```

Hard dependency of [`observe-perceive`](https://github.com/wking53214/observe-perceive) (`perceive_conservation_adapter.py`, orchestrator Phase 3). [`sentinel_os`](https://github.com/wking53214/sentinel_os) also fail-closes ledger writes through `conservation/boundary.py` onto this verifier.

Question: *did this transformation preserve protected epistemic and provenance distinctions, or did it silently change one of them?*  
Not: *is this claim true?* *is this request permitted?* *was a human authorization issued?* (The kernel **checks** registered authorization events; it does **not issue** them.)

## 2. Full System Scope & Architectural Depth

The kernel compares an immutable **input artifact** + a **declared transformation** against **independently recomputed observed effects**, using **external registries** as the trust boundary.

```
INPUT ARTIFACT + DECLARED CHANGE + OBSERVED EFFECTS + EVIDENCE/AUTH REGISTRY
        → ConservationKernel.submit
        → PASS | PASS_WITH_DECLARED_TRANSFORMATION | REJECT | UNVERIFIABLE
```

### Closed vocabularies (`enums.py`)

- `ActorKind`: HUMAN / MODEL / SYSTEM / EXTERNAL
- `EpistemicStatus`: FACT, OBSERVATION, INFERENCE, ESTIMATED, UNKNOWN, CONFLICTED, SIMULATED, ASSUMPTION, RECOMMENDATION, DECISION
- `AuthorityStatus`: NONE, PROPOSED, HUMAN_AUTHORIZED, CANONICAL, EXECUTED
- `OriginStatus`: HUMAN_ORIGINATED, MACHINE_ORIGINATED, HUMAN_ADOPTED_MACHINE_OUTPUT, EXTERNAL_ORIGINATED
- `UncertaintyState`, `TemporalScope`, `CanonicalState`
- `Dimension`: CONTENT, PROVENANCE, EPISTEMIC_STATUS, AUTHORITY, HUMAN_ORIGIN, UNCERTAINTY, LINEAGE, …

### Mechanics

- **`Proposition` / `Artifact`**: proposition-oriented envelope. Wording may change while each proposition keeps explicit epistemic/authority/origin state. Canonical JSON → SHA-256 (`canonical_json` / `_digest`). Sets forbidden; non-finite floats forbidden.
- **`IndependentVerifier`**: recomputes observed changes; **never trusts the declaration string**. Undeclared shifts → REJECT.
- **`EvidenceRegistry`**: external witness. Source-reference changes require a registered source observation.
- **`AuthorizationEvent`**: checked, not issued. If the transformer can write the authorization registry, independence is gone (`docs/LIMITATIONS.md`).
- **`ConservationLedger`**: append-only **by API**, in-memory. SHA-256 detects inconsistency on recompute; it is not a tamper-proof durable store.
- **`ConservationKernel` façade**: `register_root` → `submit` → `reconstruct`. Root admission and born-authoritative rules exist (0.2.0+). Signed snapshots in 0.3.0 (`signing.py`).
- **Hostile corpus** (`experiments.py`, numbered `test_attack_0*.py`): cross-subject authorization, recursive self-verification, provenance forgery, evidence-subject binding, human-origin reclassification, evidence deactivation.

Natural-language semantic equivalence is **unverifiable** when content changes. `PASS_WITH_DECLARED_TRANSFORMATION` means envelope invariants survived, not that a summary preserved every nuance.

## 3. What It Does NOT Do / Non-Goals

- Does **not** judge truth, usefulness, or policy permission.
- Does **not** issue authorization or manage grant lifecycle.
- Does **not** execute.
- Does **not** provide KMS/HSM, authenticity, or non-repudiation (HMAC/signatures in 0.3.0 are snapshot authenticity for a deployed key, not a grant protocol).
- Does **not** crypto-shred. Canonical fields are hashed in the clear.
- Does **not** replace Gateway admission, PERCEIVE gates, or sentinel_os Postgres custody.

## 4. Brutally Honest Current Status & Gaps

| Gap | Detail |
|---|---|
| In-memory ledger | Durable custody is sentinel_os / observe-perceive JSONL, not this package. |
| Trust boundary | Registry independence is a **deployment** property. Nothing stops a caller from stuffing HUMAN_AUTHORIZED events. |
| NL equivalence | Explicitly unverified. |
| Vocab drift | Gateway epistemic enum ≠ this enum. Adapters must map. |
| Pinned by consumers | observe-perceive and sentinel_os pin `25145aa`. Do not "fix" the default branch without re-running those suites. |
| Not a product | Commercial red team: receipt library is a **component of the spine**, not a purchase. |
| No Raft, no multi-region | Single-process verifier. |

`python3 -m pytest -q` (hostile suite included). `PYTHONPATH=src python3 experiments/run_experiment.py` is a simulated control/treatment, **not** a population claim about LLMs.

## 5. Core Invariants & Guarantees

- Fail-closed: undeclared protected-dimension shifts REJECT.
- Recomputation over trust: verifier does not believe `DeclaredChange` text.
- Actor self-report is not evidence (actor kind is tracked; judgment uses registries).
- Policy/authorization: kernel checks registered events; it does not mint them.
- Conservative origin: a human-authored container does not make embedded machine material HUMAN_ORIGINATED.
- Signed snapshots (0.3.0): unsigned or wrong-key snapshots fail when a signer is configured.

## 6. Inputs, Outputs & Type Contracts

```python
from conservation_kernel import ConservationKernel, VerificationResult
# VerificationResult:
#   transformation_id, input_artifact_ids, output_artifact_id
#   status: PASS | PASS_WITH_DECLARED_TRANSFORMATION | REJECT | UNVERIFIABLE
#   observed_changes, violations, unverifiable_properties, checked_dimensions
#   .accepted → PASS or PASS_WITH_DECLARED_TRANSFORMATION
```

Public surface is `conservation_kernel.__all__`. Everything else is internal.

## 7. Stack Integration Topology

```text
Gateway ACCEPT
    → PERCEIVE decision (observe-perceive)
        → ConservationKernel.submit(input, declared, output)
                ├── REJECT / UNVERIFIABLE → no execution context issued
                └── accepted → execution_guard ISSUED → caller callable
sentinel_os.governance_harness._write_decision
        → conservation/boundary.py → this verifier → else fail-close ledger write
```

Docs: `docs/INVARIANTS.md`, `docs/THREAT_MODEL.md`, `docs/LIMITATIONS.md`, `docs/HOSTILE_REVIEW.md`.

Apache-2.0.
