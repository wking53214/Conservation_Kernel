# Conservation_Kernel

Independently testable **hostile baseline** for transformation conservation. Version 0.3.0, not yet tagged (`CHANGELOG.md` lists it under Unreleased; consumers pin it by commit, see Section 4). Stdlib only. Python ≥ 3.11.

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
- `Proposition.conditions` (optional): the circumstances a claim holds under. Adding one passes; dropping or rewording one (`UNAUTHORIZED_SCOPE_WIDENING`), or deriving a proposition that leaves out a parent's condition (`CONDITION_DROPPED_IN_DERIVATION`), needs a human `SCOPE_WIDENING` authorization. A summary must not turn a conditional claim into an absolute one. Omitted from the digest when empty, so existing artifacts and snapshots are unchanged.

### Mechanics

- **`Proposition` / `Artifact`**: proposition-oriented envelope. Wording may change while each proposition keeps explicit epistemic/authority/origin state. Canonical JSON → SHA-256 (`canonical_json` / `_digest`). Sets forbidden; non-finite floats forbidden.
- **`IndependentVerifier`**: recomputes observed changes; **never trusts the declaration string**. Undeclared shifts → REJECT.
- **`EvidenceRegistry`**: external witness. Source-reference changes require a registered source observation.
- **`AuthorizationEvent`**: checked, not issued. If the transformer can write the authorization registry, independence is gone (`docs/LIMITATIONS.md`).
- **Authorization lifecycle**: an authorization may hold for a window (`valid_from`, `valid_until`), be ended by a `RevocationEvent` from a moment forward (never backward), or be issued under a `DelegationEvent` that lets a named delegate authorize listed subjects, kinds of change and target values (re-delegation only narrower, at most 3 links). All of it is judged as of the kernel's clock (`ConservationKernel(clock=...)`), stamped on every decision and root admission, so a restore re-verifies history as of when it was decided. `EvidenceRegistry(require_bounded=True)` refuses anything open-ended.
- **`ConservationLedger`**: append-only **by API**, in-memory. SHA-256 detects inconsistency on recompute; it is not a tamper-proof durable store.
- **`ConservationKernel` façade**: `register_root` → `submit` → `reconstruct`. Root admission and born-authoritative rules exist (0.2.0+). Signed snapshots in 0.3.0 (`signing.py`).
- **Hostile corpus** (`experiments.py`, numbered `test_attack_0*.py`): cross-subject authorization, recursive self-verification, provenance forgery, evidence-subject binding, human-origin reclassification, evidence deactivation.

Natural-language semantic equivalence is **unverifiable** when content changes. `PASS_WITH_DECLARED_TRANSFORMATION` means envelope invariants survived, not that a summary preserved every nuance.

## 3. What It Does NOT Do / Non-Goals

- Does **not** judge truth, usefulness, or policy permission.
- Does **not** issue authorization. It enforces the lifecycle of what is registered (windows, revocation, delegation scope); it does not decide who should hold a grant.
- Does **not** execute.
- Does **not** provide KMS/HSM, authenticity, or non-repudiation (HMAC/signatures in 0.3.0 are snapshot authenticity for a deployed key, not a grant protocol).
- Does **not** crypto-shred. Canonical fields are hashed in the clear.
- Does **not** replace Gateway admission, PERCEIVE gates, or sentinel_os Postgres custody.

## 4. Brutally Honest Current Status & Gaps

| Gap | Detail |
|---|---|
| In-memory ledger | Durable custody is sentinel_os / observe-perceive JSONL, not this package. |
| Trust boundary | Registry independence is a **deployment** property. Nothing stops a caller from stuffing HUMAN_AUTHORIZED events. |
| Clock | Windows and revocations are only as good as the clock handed to the kernel. A deployment should hand in its ledger's clock. A stale registry snapshot still honours a since-revoked grant. |
| NL equivalence | Explicitly unverified. |
| Vocab drift | Gateway epistemic enum ≠ this enum. Adapters must map. |
| Pinned by consumers | Consumers install this package by commit, not by tag. As read on 2026-10-31, observe-perceive pins `4e7c0d9` (`pyproject.toml`, `requirements-demo.txt`); this README no longer states a sentinel_os pin because none was found in its `pyproject.toml` or requirements files. Do not "fix" the default branch without re-running those suites. |
| Not a product | Commercial red team: receipt library is a **component of the spine**, not a purchase. |
| No Raft, no multi-region | Single-process verifier. |

### Release and test status

Measured 2026-10-31 at main `c51a246`, Python 3.13.

| What | State |
|---|---|
| Version | 0.3.0 (`pyproject.toml` and `__version__`). `ConservationKernel.version` still reads 0.2.0 and is what snapshots record as `kernel_version`; the two have not been brought together. |
| Tag and GitHub Release | None yet. The changelog has no 0.2.0 or 0.3.0 heading; both are under Unreleased. Tagging is the owner's decision. |
| CI on main | Green (tests on Python 3.11 and 3.12, with and without CNS, plus ruff 0.15.22) |
| Tests | Without CNS importable: 250 passed, 2 skipped, 0 failed (`python3 -m pytest -q` with `cns`, `cns_interop` and `cns_composition` blocked). With CNS installed: 396 passed, 0 failed, 0 skipped (396 collected), measured on Python 3.11, 3.12 and 3.13 on 2026-10-31. Not re-measured: GitHub Actions status. |
| Known failing tests | None with CNS installed. The seven failures recorded before 2026-10-31 came from the verifier's proof stamp crashing on records holding NaN or infinity (six tests) and from `add_initial` checking parents before root admission (one test); both are fixed on this branch. |
| CNS pin | `pyproject.toml` pins the optional `cns` extra to tag v2.3.0 (an earlier version of this README, and the comment in `pyproject.toml`, still say v2.2.0). |

### Which doors write, and what protects each

| Door | Protection today |
|---|---|
| `register_root` and `ledger.add_initial` | The root guard, and on a ledger a kernel owns the kernel's `admit_root` (every reference a root cites must exist and back what it claims), asked first. A kernel refuses to be built without a guard unless `allow_unguarded_roots=True` says so. The guard answers only `True` to permit. |
| `ledger.commit` | Takes only a result the verifier produced for this record and output (`VerificationResult.proof`); a result written by hand, or edited after verification, is refused. A ledger a kernel owns also refuses one reached against any registry but that kernel's. |
| `ConservationKernel.submit` | The verifier decides. Any caller may submit, but an input that shares an id with a ledger artifact must be that artifact. |
| `registry.add_authorization`, `add_delegation`, `revoke` | Only from a human in `trusted_humans`, when the deployer sets that. With it unset, any actor id is accepted. An authorization that carries a `subject_digest` counts only for the proposition with that digest, and with `require_content_bound` one without a digest is refused. |
| `registry.add_evidence` | Optional. With `evidence_guard` on the registry (or on the kernel that builds it), a record is added only if the guard answers exactly `True`; a raise or any other answer refuses and leaves the registry unchanged. A duplicate id is refused before the guard is asked, and evidence restored from a snapshot is put to it too, so a file cannot plant what the guard would refuse. A kernel refuses to be built without an evidence guard unless `allow_unguarded_evidence=True` says so (the same rule as `allow_unguarded_roots`), because with no guard any caller can add active evidence that declares itself independent. A bare `EvidenceRegistry` with no guard still takes any caller's evidence. |
| `ledger.record_rejection` | Takes only a result the verifier produced for the record and output it is given (its proof must check), and on a ledger a kernel owns only one reached against that kernel's registry. |
| times on roots and transformations | Set by the kernel's clock when it admits or accepts, and once by its own reload for history that has none. There is no public door to stamp a time. |
| `from_snapshot` and `load` | Digest check and re-verification; a signature only if the loader passes a signer. |

Evidence is the first of the open doors to get an optional caller permission, because the verifier trusts evidence to approve strong claims. Whether `submit` should get one too is an open decision for the owner, and the CNS evidence spine does not yet pass an evidence guard.

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

### Role in the STACK spine

The evidence spine is the five repositories one document passes through in order: HERALD reads it and extracts claims (judging the document and each claim), TIE records HERALD's signed export as evidence and refuses a changed export, Conservation_Kernel judges a root artifact built from that evidence before it becomes ancestry, Governance_Gateway judges the artifact at its admission door, and CCC judges the attempt to ingest into its store. `chains/evidence_spine.py` in CNS drives all five (it imports `conservation_kernel`, `Artifact`, `ConservationKernel` and `CnsRootAdmissionGate` at lines 137-141 of that file).

```text
HERALD ──signed export──> TIE ──evidence──> Conservation_Kernel ──root──> Governance_Gateway ──> CCC
 claims                  records,           judges a root artifact       judges the            judges the
                         refuses a          before it is ancestry        admission door        ingest attempt
                         changed export     (this repo)
              CNS: gate shapes, roster, one-use DecisionGuard (moves objects, decides nothing)
```

**Purpose.** Decide whether a root artifact (or a declared transformation of an existing artifact) may enter the ledger, by recomputing what changed and checking it against registered evidence and authorizations.

**Responsibilities (this repo).**
- Recompute observed changes and reject undeclared shifts in protected dimensions (`verifier.py`).
- Judge a root before it is registered (`ConservationKernel.admit_root`, `kernel.py:114`; `register_root`, `kernel.py:172`).
- Hold the evidence and authorization registries and the append-only in-memory ledger (`registry.py`, `ledger.py`), and snapshot and reload them (`kernel.py:223`, `kernel.py:311`).

**Inputs and outputs.** In: an input `Artifact`, a `TransformationRecord` with declared changes, an output `Artifact`, evidence and authorization events. Out: a `VerificationResult` (`PASS`, `PASS_WITH_DECLARED_TRANSFORMATION`, `REJECT`, `UNVERIFIABLE`), ledger entries, and signed snapshots. For roots, the list of refusals from `admit_root`.

**Owns.** The verdict on conservation of protected epistemic and provenance distinctions; the authorization lifecycle rules (windows, revocation, delegation) as applied to registered events; the ledger and snapshot format.

**Does not own.**
- Truth of content. HERALD extracts and judges claims; this kernel does not read them for truth.
- Evidence provenance before it arrives. TIE records HERALD's export; the kernel only checks that a registered record backs what a root cites. An `evidence_guard` is how a deployer lets the owner of evidence permit a record, and the kernel never mints evidence.
- Permission to proceed. Governance_Gateway judges the admission door and CCC judges its own ingest; the receiver's policy permits, not this kernel.
- The roster, the cross-seat same-document check and the one-use guard. Those are CNS (`cns_composition`, `cns_interop`), and the kernel calls none of them. In the spine, CNS supplies the object passed as `root_guard`; the kernel only asks it a yes or no question.
- Issuing authorizations, durable custody, execution.

**Integration with the spine seats.** The kernel has no import of HERALD, TIE, Governance_Gateway, CCC, CCCb or Link (grep of `src/` and `docs/` found none; `docs/GATEWAY.md` names GEMS, not Governance_Gateway, as a reference gateway). TIE and HERALD reach the kernel only through the spine script: the script builds the kernel with `root_guard=DecisionGuard(...)` (`chains/evidence_spine.py:237`, `fresh_guard` at 377) and an `evidence_guard=tie_evidence_guard(...)` (`chains/evidence_spine.py:209`, `239`). Those guards are written in CNS's script, not here. As read on 2026-10-31 from `/home/user/CNS`; the spine's own run was not repeated for this README (CNS recorded 30 results, all ok, and one stated GAP, on 2026-10-30).

**CNS interaction: partial.**
- Implemented, optional, one direction: `conservation_kernel/cns_connector.py` loads `cns.gate` lazily by `importlib.import_module` (`cns_connector.py:133`, `186`) and expresses verdicts as `GateResult`s: `CnsGate` (OMEGA, `cns_connector.py:489`), `CnsRootAdmissionGate` (ALPHA, `cns_connector.py:536`), `verify_to_cns` (`:604`), `submit_to_cns` (`:624`). Nothing in `kernel.py`, `verifier.py` or `ledger.py` imports CNS, and `tests/test_cns_independence.py` covers loading without it.
- Used by the spine: CNS's `evidence_spine.py` builds `CnsRootAdmissionGate(kernel, require_guard=True, require_evidence_guard=True)` as the Conservation_Kernel seat (`chains/evidence_spine.py:476`, `922`). The spine does not use this repo's `CnsGate` (its `CnsGate` import at line 142 is Governance_Gateway's).
- Not implemented: `cns_interop` (UAI-1 signed messages) and `cns_composition` are not imported anywhere in this repo (absent). The kernel does not sign or verify UAI-1 messages itself; `signing.py` signs snapshots only.
- Not paired: `cns_chain(...).complete()` is `False` by design (Section 8).
- Known gap: 7 connector tests fail today (Release and test status, above).

Docs: `docs/INVARIANTS.md`, `docs/THREAT_MODEL.md`, `docs/LIMITATIONS.md`, `docs/HOSTILE_REVIEW.md`.

## 8. Connecting to CNS (optional)

The kernel stands alone: no runtime dependency, nothing imported from CNS when
the package loads, and the whole suite passes without CNS installed. If CNS is
present, `conservation_kernel.cns_connector` expresses the kernel's verdicts as
CNS gate results so they can be resolved alongside gates from other
repositories. The kernel's own verdicts and behavior are unchanged.

The `cns` extra pins CNS by git tag (v2.2.0), which PyPI does not accept, so this
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
| root registration (`CnsRootAdmissionGate`, `root_refusals`) | `ALPHA`: judged before the root is registered. Nothing refuses it is `PASS`. Any refusal is `TERMINAL_BREACH`, whether from `admit_root` (the propositions) or from the ledger (the artifact already has parents, or its id is already registered). `admit_root` alone does not see the ledger's refusals, so the gate does not rely on it alone. With `require_guard=True` or `require_evidence_guard=True` (both default off, independent) it also refuses a kernel built without a root guard or without an evidence guard. |
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
  (`cns.gate.unbound` names it). The verifier cannot stamp a record it cannot
  digest, so the result is unproven and nothing is kept as a report.
- The kernel accepts it. A matching declaration followed by a second
  declaration for the same subject and dimension with the non-finite value is
  accepted by the verifier, because it stops at the first match. But the
  result has no proof, so the ledger refuses to commit it: `submit` raises
  `LedgerError`, nothing is committed or kept, and the verdict is the unbound
  `TERMINAL_BREACH`. `submit_to_cns` reports the refusal in the reason, so the
  CNS verdict and the ledger agree.
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
