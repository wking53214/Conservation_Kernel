# Conservation Kernel v0.1

The Conservation Kernel is an independently testable mechanism for evaluating
whether machine-mediated transformations preserve protected epistemic and
provenance distinctions.

The implementation is deliberately small and adversarial. It compares:

- an immutable input artifact;
- an immutable output artifact;
- a declared transformation;
- observed transformation effects; and
- an external evidence and authorization registry.

The kernel does not determine whether a claim is true in the external world.
It evaluates whether a claimed transition is structurally supported and whether
protected distinctions have been silently changed.

## Run

```bash
python3 -m pytest -q
PYTHONPATH=src python3 experiments/run_experiment.py