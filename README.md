# Conservation Kernel v0.1

This is the first independently testable mechanism for the Conservation Kernel
hypothesis. It is deliberately small and hostile. It compares an immutable
input artifact, an immutable output artifact, a transformation declaration,
and an external evidence/authorization registry.

The kernel does not decide whether a claim is true in the external world. It
checks whether a claimed transition is structurally supported and whether
protected distinctions were silently changed.

## Run it

```bash
python3 -m pytest -q
PYTHONPATH=src python3 experiments/run_experiment.py
```

The implementation has no runtime dependencies outside Python 3.11+. Pytest
is only a development dependency.

## What exists in this phase

- immutable proposition-oriented artifacts with deterministic hashes;
- explicit epistemic, origin, authority, uncertainty, temporal, evidence,
  canonicality, provenance, lineage, and functional-contract fields;
- typed transformation records with declared changes separated from observed
  changes;
- an external registry for human authorizations and evidence;
- an independent verifier with fail-closed results;
- an append-only in-memory ledger and reconstruction engine;
- a 10-boundary deterministic control/treatment experiment;
- hostile regression cases and legitimate content-transformation cases.

## What this does not make

Passing a verifier does not prove an assertion is true. A human authorization
does not prove truth. A citation does not prove truth. A model consensus does
not prove truth. A SHA-256 digest is used here for deterministic identity and
change detection, not for signatures, custody, or tamper-proof storage.

The treatment can detect and reject the classes of unauthorized structural
promotion represented in the hostile corpus. It cannot stop a downstream
system that never submits its output to the kernel. That is a protocol/gateway
problem, not something a library can solve by assertion.

See `docs/REPORT.md` for the current claim classification.
