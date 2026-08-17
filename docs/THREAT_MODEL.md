# Threat model

The downstream transformer may be confused, careless, hallucinating,
prompt-injected, semantically lossy, intentionally deceptive, or simply
overconfident. It may remove metadata, rewrite labels, collapse uncertainty,
fabricate provenance, fabricate authorization references, or omit required
fields.

The verifier assumes that the input and output objects it receives are the
objects under review and recomputes their hashes and field differences. It
does not assume transformer declarations are true. Human authorization and
independent evidence are supplied through a separate registry.

## Out of scope

- a malicious process that can directly mutate the verifier's memory;
- a malicious operator who controls both the transformation and the external
  authorization registry;
- objective truth about the external world;
- stopping an application that bypasses the kernel entirely;
- cryptographic signatures, key custody, or tamper-proof persistence;
- semantic equivalence of arbitrary natural-language content.

Those limitations are not hidden success conditions. A production deployment
would need a protocol or gateway boundary, separate custody for the event
registry, and an independent persistence/witness design.
