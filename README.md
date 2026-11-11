# Conservation_Kernel

Independently testable **hostile baseline** for transformation conservation. It checks whether a transformation of an artifact preserved protected epistemic and provenance distinctions.

Version 0.3.0, not yet tagged (`CHANGELOG.md` lists it under Unreleased). Stdlib only. Python 3.11 or later. Consumers install it by commit, not by tag.

## 1. Position in the spine

The kernel is the third of five repositories in the evidence spine. One document passes through them in order:

```text
HERALD ──signed export──> TIE ──evidence──> Conservation_Kernel ──root──> Governance_Gateway ──> CCC
 extracts claims          records the          judges a root artifact      judges the             judges the
                          export, refuses      before it becomes           admission door         ingest attempt
                          a changed export     ancestry (this repo)
```

- **HERALD** reads the document and extracts claims. It judges the document and each claim.
- **TIE** records HERALD's signed export as evidence and refuses a changed export.
- **Conservation_Kernel** (this repo) judges a root artifact built from that evidence before it becomes ancestry.
- **Governance_Gateway** judges the artifact at its admission door.
- **CCC** judges the attempt to ingest into its store.

Wider pipeline (described by sentinel_os; an order, not an import chain): the kernel sits after the policy decision and before trusted downstream use or execution (`Admission → Observe/Keys → Locks → PERCEIVE → Decision → Conservation → Execution → Custody`).

The kernel asks one question: *did this transformation preserve protected epistemic and provenance distinctions, or did it silently change one of them?* It does not ask whether a claim is true, whether a request is permitted, or whether a human authorized it. It checks registered authorization events. It does not issue them.

Cross-repo wiring was checked against cloned source on 2026-11-08. The CNS spine script ran end to end on that date, with 56 checks passing, no failures, and the three gaps the script records as stated facts. The run used each repo's current default branch, not the pins CI uses, so it shows the stack works together at those heads, not that the pinned stack does. Commits: CNS `fa40197`, HERALD `392dfd0`, TIE `3c93ef9`, Governance_Gateway `6342d7a`, CCC `8923a18`, Conservation_Kernel `c4719bc`. To reproduce, clone those five repos, put each one's package directory on `PYTHONPATH`, and run `python chains/evidence_spine.py` from the CNS checkout. Still not checked: GEMS's 20/20 experiment (it does not run against current main), sentinel_os's gateway strictness, and downstream suites.

## Where this fits

The kernel is shared infrastructure inside ≡TACK, the whole library of repos (it is not STACK-kernel, which is one separate repo). Other repos depend on it by pinned commit: observe-perceive, sentinel_os and GEMS. CNS, the cross-cutting layer, connects to it through an optional two-way link (section 7). In this README, "spine" means the five-repo evidence chain above.

## 2. How it works

The kernel compares an immutable **input artifact** and a **declared transformation** against **observed effects it recomputes itself**, using **external registries** as the trust boundary.

```text
INPUT ARTIFACT + DECLARED CHANGE + OBSERVED EFFECTS + EVIDENCE/AUTH REGISTRY
        → ConservationKernel.submit
        → PASS | PASS_WITH_DECLARED_TRANSFORMATION | REJECT | UNVERIFIABLE
```

- **Proposition and Artifact.** Each proposition carries explicit epistemic, authority and origin state. Artifacts hash to SHA-256 over canonical JSON. Sets and non-finite floats are forbidden.
- **IndependentVerifier.** Recomputes observed changes and never trusts the declaration text. An undeclared shift in a protected dimension is a REJECT.
- **EvidenceRegistry.** The external witness. Changing a proposition's source references is refused (`SOURCE_SUBSTITUTION_UNVERIFIED`), and a registered source observation does not approve the change. A proposition must have registered source observations before it can become canonical.
- **AuthorizationEvent.** Checked, not issued. Authorizations can carry a validity window, be ended by a revocation from that moment forward, or be delegated within listed subjects and change kinds (re-delegation only narrower, at most 3 links). All of this is judged against the kernel's clock.
- **Proposition conditions.** Dropping or rewording a condition, or deriving a proposition that leaves out a parent's condition, needs a human `SCOPE_WIDENING` authorization. A summary must not turn a conditional claim into an absolute one.
- **ConservationLedger.** Append-only by API, in memory. SHA-256 detects inconsistency on recompute. It is not a tamper-proof durable store.
- **ConservationKernel façade.** `register_root` → `submit` → `reconstruct`. Snapshots are signed from 0.3.0 (`signing.py`).
- **Hostile corpus.** `tests/test_attack_NN_*.py` covers cross-subject authorization, recursive self-verification, provenance forgery, evidence-subject binding, human-origin reclassification, evidence deactivation, and evidence addition binding. Attack #13 (historical-content mutation) is a deferred design decision.

Natural-language equivalence is **unverifiable** when content changes. `PASS_WITH_DECLARED_TRANSFORMATION` means envelope invariants survived. It does not mean a summary kept every nuance.

Core guarantees:

- Undeclared protected-dimension shifts REJECT (fail-closed).
- The verifier does not believe the `DeclaredChange` text.
- Actor self-report is not evidence. Actor kind is tracked, and judgment uses registries.
- A human-authored container does not make embedded machine material HUMAN_ORIGINATED.
- Signed snapshots with an unsigned or wrong-key file fail when a signer is configured.

## 3. Non-goals and known gaps

Does **not**:

- judge truth, usefulness, or policy permission;
- issue authorizations (it enforces the lifecycle of what is registered, not who should hold a grant);
- execute anything;
- provide KMS/HSM, non-repudiation, or a grant protocol. Snapshot signatures show authenticity under a deployed key only;
- crypto-shred (canonical fields are hashed in the clear);
- replace Gateway admission, PERCEIVE gates, or sentinel_os Postgres custody.

Known gaps:

| Gap | Detail |
|---|---|
| In-memory ledger | Durable custody lives in sentinel_os or observe-perceive JSONL, not in this package. |
| Trust boundary | Registry independence is a **deployment** property. Nothing stops a caller from adding HUMAN_AUTHORIZED events. |
| Clock | Windows and revocations are only as good as the clock given to the kernel. A stale registry snapshot still honours a revoked grant. |
| NL equivalence | Explicitly unverified. |
| Vocabulary drift | The Gateway's epistemic enum differs from this one. Adapters must map. |
| Consumer pins | On 2026-11-08, observe-perceive's main pins commit `4e7c0d9`. sentinel_os pins commit `7b08c79` in `sentinel_os/sentinel_os/requirements.txt` (not in its top-level files); GEMS CI pins `570c2c7`. Do not move the default branch without re-running those suites. |
| Scale | Single-process verifier. No Raft, no multi-region. |

## 4. Which doors write, and what protects each

| Door | Protection |
|---|---|
| `register_root`, `ledger.add_initial` | A root guard must answer exactly `True`. On a ledger the kernel owns, the kernel's `admit_root` also runs. A kernel refuses to be built without a root guard unless `allow_unguarded_roots=True`. |
| `ledger.commit` | Takes only a result the verifier produced for this record and output (its proof). A hand-written or edited result is refused. |
| `ConservationKernel.submit` | The verifier decides. Any caller may submit. An input sharing an id with a ledger artifact must be that artifact. |
| `registry.add_authorization`, `add_delegation`, `revoke` | Only from a human in `trusted_humans`, when the deployer sets it. If unset, any actor id is accepted. An authorization with a `subject_digest` counts only for that proposition. |
| `registry.add_evidence` | With an `evidence_guard`, a record is added only if the guard answers exactly `True`. Snapshot-restored evidence goes through the guard too. A kernel refuses to be built without one unless `allow_unguarded_evidence=True`. A bare `EvidenceRegistry` takes any caller's evidence. |
| `ledger.record_rejection` | Takes only a verifier result whose proof checks, for the record and output given. |
| Times on roots and transformations | Set by the kernel's clock. There is no public door to stamp a time. |
| `from_snapshot`, `load` | Digest check and re-verification. A signature is checked only if the loader passes a signer. |

Evidence is the first open door to get an optional caller permission, because the verifier trusts evidence to approve strong claims. Whether `submit` should get one too is an open decision for the owner. The CNS evidence spine does pass an evidence guard (TIE's `tie_evidence_guard`, built in the spine script). Whether that guard is independently trustworthy is a deployment question this repo does not prove.

## 5. Status and tests

Measured 2026-11-08 on Python 3.13, at main `00b0031`, from the repo root. The code changed after an earlier measurement at `3aab1ae` (a version fix), so these counts are from the measurement commit:

| What | State |
|---|---|
| Version | 0.3.0 (`pyproject.toml`, `__version__`, and `ConservationKernel.version`, which snapshots record as `kernel_version`). |
| Tag and release | None. The changelog has no 0.2.0 or 0.3.0 heading. Tagging is the owner's decision. |
| Tests, no CNS | `python3 -m pytest -q`: 285 passed, 4 skipped (connector tests skip without CNS). |
| Tests, with CNS | 440 passed, 0 skipped. The CNS pin is `v2.3.0`. |
| CI on main | Green on `a03f237` (2026-11-10): four jobs on Python 3.11 and 3.12. `test` runs the suite, the experiment and ruff with only the dev extra installed, so connector tests skip. `cns` installs the CNS extra and sets `CONSERVATION_KERNEL_REQUIRE_CNS=1`, so connector tests must run and a missing CNS fails the job. The test counts in section 5 were measured at `00b0031` and re-confirmed at `a03f237`. |

The suite must run from the repo root. `test_experiment.py` reads a relative path and fails from any other directory.

The experiment (`PYTHONPATH=src python3 experiments/run_experiment.py`) is a simulated control and treatment. It is **not** a population claim about LLMs.

## 6. Interface

This block lists the result's fields. It is a shape reference, not a runnable script. For a runnable example, use the experiment in section 5.

```python
from conservation_kernel import ConservationKernel, VerificationResult
# VerificationResult:
#   transformation_id, input_artifact_ids, output_artifact_id
#   status: PASS | PASS_WITH_DECLARED_TRANSFORMATION | REJECT | UNVERIFIABLE
#   observed_changes, violations, unverifiable_properties, checked_dimensions
#   .accepted → PASS or PASS_WITH_DECLARED_TRANSFORMATION
```

The core public API is `conservation_kernel.__all__`. `conservation_kernel.cns_connector` is a separate, optional interface, documented in section 7. Everything else is internal.

## 7. Optional CNS connection

The kernel stands alone. Nothing in `kernel.py`, `verifier.py` or `ledger.py` imports CNS. `conservation_kernel.cns_connector` loads `cns.gate` only when it is used, and it expresses the kernel's verdicts as CNS gate results. The kernel's own behavior does not change.

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

| Conservation Kernel | CNS |
|---|---|
| `PASS`, `PASS_WITH_DECLARED_TRANSFORMATION` | `PASS`. The reason keeps what was left unverified. |
| `REJECT` | `TERMINAL_BREACH`. The reason lists every violation code. |
| `UNVERIFIABLE` | `TERMINAL_BREACH`. The kernel never treats it as a pass. |
| Accepted, but the ledger refuses | `TERMINAL_BREACH` with the ledger's reason. |
| Root registration (`CnsRootAdmissionGate`) | `ALPHA`, judged before the root is registered. Any refusal is `TERMINAL_BREACH`. |

Limits of the connector:

- `artifact_digest` is computed at construction, and nested metadata is only shallow-frozen. In-place mutation of nested metadata keeps the digest while a verdict can change.
- `VerificationResult` carries ids, not a content digest. A result can be bound to content it was not computed from. Pair a result with its candidate, or use `CnsGate`, `verify_to_cns` or `submit_to_cns`, which run the verifier on the candidate they bind.
- A consumer with a stricter policy must read the reason. `sentinel_os`'s `ConservationGateway` is stricter than this connector. The connector does not split rejections or refuse unverifiable properties beyond the kernel's own `.accepted`.
- A `DeclaredChange` with NaN or infinity is never turned into a `PASS`. The kernel rejects it, or the ledger refuses to commit its result.
- `cns_chain(...).complete()` is `False` by design. The two gates judge different candidates, so run `CnsRootAdmissionGate` on its own, on a root artifact.

CI covers CNS in two jobs. The `test` job installs only `.[dev]`, so the connector tests skip there. The `cns` job installs the extra and requires CNS, so those tests run and cannot skip silently. To run them locally, install the extra first.

Apache-2.0.
