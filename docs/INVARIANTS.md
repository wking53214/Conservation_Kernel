# Invariants

1. A transformed artifact has a new identity and names exactly the input
   artifact(s) as parents.
2. Transformation hashes are recomputed; transformer-supplied validation
   claims are ignored.
3. Every observed protected-field change must be declared with matching
   before/after values.
4. Every declared change must be observed.
5. A model cannot turn machine-originated material into human-originated
   material.
6. Machine output can become `HUMAN_ADOPTED_MACHINE_OUTPUT` only through an
   external human adoption authorization.
7. `RECOMMENDATION -> DECISION` requires a matching human authorization.
8. `UNKNOWN -> INFERENCE` requires a named derivation and active non-consensus
   support.
9. `ESTIMATED`, `INFERENCE`, or `CONFLICTED` cannot become `FACT` or
   `OBSERVATION` without independent verification; strong promotions also
   require human authorization where applicable.
10. `SIMULATED -> FACT/OBSERVATION` is rejected as a same-proposition relabel.
11. Model consensus, citations, execution, and actor self-report are not
   independent verification.
12. Uncertainty cannot disappear silently.
13. `occurred_at` and `observed_at` are distinct fields; changing either is an
   explicit temporal transition.
14. Evidence loss, inactive evidence, provenance stripping, and false lineage
   are visible failures.
15. Functional contracts cannot be dropped or changed without a separate
   functional validation record.
16. Initial registration does not retroactively prove a proposition; the
   verifier evaluates transformations and records its bounded scope.
