# Model

An `Artifact` is a versioned payload plus a typed proposition envelope.
Propositions have stable IDs across ordinary transformations. Each carries:

- epistemic status;
- human/machine/external origin;
- authority status;
- explicit uncertainty state and reason;
- occurred/observed/valid temporal metadata;
- source and evidence references;
- authorization references;
- canonical lifecycle state;
- parent proposition IDs; and
- an optional derivation method and metadata map.

An artifact also carries parent artifact IDs, producer identity, a functional
contract, a content hash, and a hash of its canonical representation.

`TransformationRecord` is separate from the artifact. It records the input
and output hashes, transformer, declared changes, evidence references, and
authorization references. `claimed_validation_results` exists only to test
the anti-self-ratification rule; the verifier ignores it.

`EvidenceRegistry` is a separate witness boundary. A model can name an
authorization ID, but a model-created object with that ID is not an
authorization. Only a registered event created by a human actor can satisfy
human authorization checks. Likewise, independent verification cannot be
provided by a model.

## Result semantics

| Result | Meaning |
| --- | --- |
| `PASS` | No protected field changed, or all observed changes were structurally verified and no semantic equivalence claim is needed. |
| `PASS_WITH_DECLARED_TRANSFORMATION` | A declared change was structurally admissible. Content/semantic equivalence may remain explicitly unverified. |
| `REJECT` | A prohibited, unauthorized, undeclared, malformed, or unsupported change was observed. |
| `UNVERIFIABLE` | No prohibited change was proven, but a required property could not be independently established. It is never treated as pass. |

## Truth boundary

The verifier can establish facts about the record and transition:

- whether hashes and lineage agree;
- whether fields changed;
- whether an event exists in the external registry;
- whether an authorization was human and matched the transition; and
- whether required evidence/functional records are present.

It cannot establish that a proposition corresponds to the external world.
