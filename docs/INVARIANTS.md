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
17. A proposition's source references cannot change. A change is refused
   (`SOURCE_SUBSTITUTION_UNVERIFIED`), and a registered source observation does
   not override the refusal. Removing source references is refused
   (`PROVENANCE_STRIPPED`).
18. Evidence attached to a proposition must be about that proposition or one of
   its parents. Foreign evidence added to an existing or new proposition is
   refused (`FOREIGN_EVIDENCE_ADDED`).
19. A proposition cannot become canonical without registered source
   observations and supporting evidence (`CANONICAL_WITHOUT_EVIDENCE`). A new
   proposition must be rooted (`UNROOTED_NEW_PROPOSITION`).
20. A proposition's conditions cannot be dropped or reworded without a human
   `SCOPE_WIDENING` authorization (`UNAUTHORIZED_SCOPE_WIDENING`). A derivation
   cannot omit a parent's condition (`CONDITION_DROPPED_IN_DERIVATION`).
21. Authorizations are judged against the kernel's clock. Windows apply,
   revocation takes effect only from the time it is recorded, and delegation can
   only narrow on re-delegation.
22. Root admission and evidence registration require their guards to answer
   exactly `True`. A kernel without a guard must opt out explicitly.

Items 17 to 22 were added to match the current code. Items 1 to 16 are unchanged.
