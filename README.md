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

## 8. Connecting to CNS (optional)

The kernel stands alone: no runtime dependency, nothing imported from CNS when
the package loads, and the whole suite passes without CNS installed. If CNS is
present, `conservation_kernel.cns_connector` expresses the kernel's verdicts as
CNS gate results so they can be resolved alongside gates from other
repositories. The kernel's own verdicts and behavior are unchanged.

The `cns` extra pins CNS by git commit, which PyPI does not accept, so this
package is installed from git or from a checkout rather than from an index:

```
pip install 'conservation-kernel[cns] @ git+https://github.com/wking53214/conservation_kernel@<commit>'
pip install -e '.[cns]'      # from a checkout
```

```python
from conservation_kernel.cns_connector import submit_to_cns
from cns.gate import resolve

verdict = submit_to_cns(kernel, input_artifact, output, record, subject="summary-7")
resolve([verdict])       # PASS or TERMINAL_BREACH, fail-closed
```

`submit_to_cns` does what `kernel.submit` does (verify, then commit or record
the rejection) and returns the verdict as a bound `cns.gate.GateResult`.
`verify_to_cns` and `CnsGate` judge without touching a ledger.

| Conservation Kernel | CNS |
|---|---|
| where it judges a transformation | `OMEGA`: `verify` takes the produced output as an argument, so it judges a result that already exists, and a rejection means the output never enters the ledger. The verifier cannot run before the output exists. |
| `PASS`, `PASS_WITH_DECLARED_TRANSFORMATION` (`.accepted`) | `PASS`. The reason keeps what was left unverified, for example `semantic_content_equivalence`. See the note below on stricter consumers. |
| `REJECT` | `TERMINAL_BREACH`; the reason lists every violation code |
| `UNVERIFIABLE` | `TERMINAL_BREACH` (the kernel never treats it as a pass) |
| accepted, then the ledger refuses (`LedgerError`; `submit_to_cns` only) | `TERMINAL_BREACH` with the ledger's reason. `kernel.submit` raises here. |
| root registration (`CnsRootAdmissionGate`, `root_refusals`) | `ALPHA`: judged before the root is registered. Nothing refuses it is `PASS`. Any refusal is `TERMINAL_BREACH`, whether from `admit_root` (the propositions) or from the ledger (the artifact already has parents, or its id is already registered). `admit_root` alone does not see the ledger's refusals, so the gate does not rely on it alone. |
| retry | never produced. The kernel models no retry or repair (`docs/GATEWAY.md`), and the connector does not invent one. |
| judged content | `subject` label plus `subject_digest` over the ids, the kernel's own `artifact_digest` of every input and the output, and `TransformationRecord.canonical_digest()`. The evidence registry is the witness, not the judged content, so it is not in the digest. |

What the digest does not do, all of it the kernel's own limit:

- `artifact_digest` is computed when an `Artifact` is constructed, and a
  proposition's nested `metadata` is only shallow-frozen. An artifact whose
  nested metadata is mutated in place keeps its digest while a verdict on it
  can change. The kernel's `input_hashes` check has the same blind spot.
- `VerificationResult` carries ids and no content digest. `to_cns_result`
  therefore refuses a result issued for other ids, but it cannot tell a result
  for the same ids over different content, and it would bind that result to the
  content you handed it. Pair a result with the candidate it was computed from,
  or use `CnsGate`, `verify_to_cns` or `submit_to_cns`, which run the verifier
  on the candidate they bind.

A consumer with a stricter policy has to read the reason. `PASS_WITH_DECLARED_TRANSFORMATION`
maps to `PASS` for every unverifiable property, as the kernel's own `.accepted`
does, and every rejection maps to the same `TERMINAL_BREACH`. `sentinel_os`'s
`ConservationGateway` is stricter on both counts: it refuses an accepted result
that carries any unverifiable property other than `semantic_content_equivalence`,
and it splits a rejection into authorization-required, verification-required
and rejected. The connector does neither.

The two gates judge different candidates (a transformation, and an asserted
root artifact), so the connector does not pair them into one chain:
`cns_chain(...).complete()` is `False` by design. Run `CnsRootAdmissionGate` on
its own, on a root artifact. Putting it in the `alpha` slot beside `CnsGate` in
`omega` of one `GateChain` is accepted by CNS and then reports `complete()` as
`True`, but each gate raises `TypeError` for the other's candidate, so the two
ends share no request: that is the false completeness `cns_chain` avoids.

A `DeclaredChange` holding NaN or an infinity cannot be digested by the kernel
or by CNS, and the connector never turns it into a `PASS`:

- The kernel rejects it: the verdict is `TERMINAL_BREACH` and unbound
  (`cns.gate.unbound` names it).
- The kernel accepts it. A matching declaration followed by a second
  declaration for the same subject and dimension with the non-finite value is
  accepted, because the verifier stops at the first match, and the kernel
  commits it. The verdict is still the unbound `TERMINAL_BREACH`, so here the
  CNS verdict and the ledger disagree, and `submit_to_cns` says so in the
  reason. That is a kernel inconsistency the connector surfaces and does not
  fix.
- The kernel raises `ValueError` while verifying. There is no verdict to
  translate, so the connector propagates the error unchanged.

A declared value nested past the interpreter's recursion limit is handled like
the first case.

Without CNS installed, the connector's functions raise `CnsNotInstalled` with
the install command, before the kernel is touched. Nothing else changes.

CI installs only `.[dev]`, so the connected tests (which need the `cns` extra)
are skipped there and only the independence tests run. Run the connected tests
in an environment where the extra is installed.

Apache-2.0.
