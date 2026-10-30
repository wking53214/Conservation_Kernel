# Limitations

The first implementation is a structural verifier, not a truth engine.

Natural-language equivalence remains unverified whenever content changes.
The `PASS_WITH_DECLARED_TRANSFORMATION` result means the envelope invariants
survived; it does not mean a summary preserved every semantic nuance.

The in-memory ledger is append-only by API but is not a tamper-proof durable
ledger. SHA-256 catches accidental or inconsistent changes when records are
recomputed; it does not authenticate an actor or prevent a privileged process
from rewriting storage.

The registry is an explicit trust boundary in the experiment. If a deployment
lets the transformer write human authorization events, the result is not an
independent authorization protocol. The next phase would need separate
custody, signed events, or a gateway with a defined threat model.

Authorization windows, revocation and delegation (unreleased) are judged
against the clock the deployment hands the kernel, and against the registry
the kernel is given. A wrong clock, or a registry copy that has not received a
revocation, gives a wrong answer. Revocation takes effect from when the kernel
records it, never earlier, so it cannot unmake a decision already accepted.
A delegated authorization is judged when it is used; when it was issued is
the issuer's own claim and is not relied on.

Two paths sit outside these guarantees because they are the deployer's own.
`EvidenceRegistry.add_revocation(recorded_at=...)` trusts the time it is given;
a time set earlier than the truth lets a revocation reach back over accepted
decisions, so record through `ConservationKernel.revoke`. And a root or
transformation written straight to the ledger (not through the kernel) carries
no time until the kernel first re-verifies it, so a revocation recorded before
that reload reaches it.

The verifier is conservative. It rejects source-reference changes unless a
registered source observation supports them, and it does not infer that a
human-authored container makes embedded machine material human-originated.

The control/treatment run is deterministic and uses simulated transformers.
It demonstrates the mechanics of measurement, not a population-level claim
about actual LLMs or heterogeneous production systems.
