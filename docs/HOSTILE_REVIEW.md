# Hostile review

This review is intentionally not a success narrative.

1. **Can a Gem bypass the kernel?** Yes. A caller can construct an artifact
   and never submit it. This is a library limitation and is `FALSIFIED` as a
   claim of universal enforcement. A gateway/protocol is required.
2. **Can a malicious transformer fabricate authorization?** Not if the
   transformer cannot write the external registry; fake IDs are rejected. If
   the transformer controls the registry, the trust boundary is invalid and
   the result is `UNVERIFIED`.
3. **Can metadata be forged?** Typed status fields are independently compared.
   Metadata loss is rejected and metadata additions are not treated as proof.
   Arbitrary metadata semantics remain `UNVERIFIABLE`.
4. **Can provenance be stripped?** Source-reference removal is rejected as
   `PROVENANCE_STRIPPED`.
5. **Can uncertainty be collapsed?** Removing an uncertainty state requires
   registered independent verification; the hostile tests reject collapse.
6. **Can historical state be rewritten?** An occurred/observed/scope change
   needs a matching temporal event. The in-memory ledger is not a durable
   tamper-proof store, so privileged storage rewriting remains out of scope.
7. **Can AI output acquire human origin?** Direct conversion is rejected;
   explicit adoption retains `HUMAN_ADOPTED_MACHINE_OUTPUT` rather than
   rewriting origin to `HUMAN_ORIGINATED`.
8. **Can a model self-certify?** No. Claimed validation fields are ignored and
   model consensus cannot satisfy independent verification.
9. **Can conventional logging reproduce the result?** The deterministic
   control accepted the hostile outputs while the treatment blocked all five
   scheduled attacks. General production equivalence is still `UNVERIFIED`.
10. **Is conservation merely metadata persistence?** Partially. The verifier
    does enforce typed transition conditions and hashes, but it cannot prove
    arbitrary natural-language meaning. The broad claim is only partially
    supported.
11. **Is the invariant actually enforced?** Yes at the `submit` boundary, as
    `TEST-VERIFIED`; no at an uncooperative downstream boundary.
12. **What if the verifier is wrong?** There is no verifier-of-verifier in
    v0.1. This remains `UNVERIFIED` and is a major next-phase risk.
13. **What if evidence conflicts?** Conflict is retained as a typed state and
    strong promotion is blocked without independent support. Multi-source
    adjudication policy is not implemented.
14. **What if two transformations legitimately change epistemic status?**
    Explicit positive tests cover `UNKNOWN -> INFERENCE` and
    `RECOMMENDATION -> DECISION` with the required records.
15. **What if a human intentionally changes a truth state?** The kernel records
    the human transition; it does not decide whether the human is objectively
    correct.
16. **Can the full history be reconstructed?** Ten accepted transformations
    reconstruct to the original artifact and proposition histories from the
    ledger. This is `TEST-VERIFIED` for the bounded fixture.
17. **What if an artifact or evidence is deleted?** Inactive evidence retained
    by a strong/canonical proposition is rejected. Durable deletion custody is
    not implemented.
18. **What if a downstream system ignores the envelope?** The kernel cannot
    observe or stop it. This is `FALSIFIED` for library-only enforcement.
19. **What if a downstream system creates a new artifact instead of
    transforming the old one?** Submitted unrooted artifacts are rejected;
    artifacts never submitted remain outside the mechanism.
20. **Can the kernel distinguish legitimate change from corruption?** It can
    distinguish structural, explicitly supported transitions from silent
    promotion. Arbitrary semantic equivalence is not independently verifiable
    and remains explicitly unverified.

## Bottom line

The narrow mechanism survives the first hostile corpus under a stated external
registry boundary. The universal architecture claim does not survive unchanged:
it needs an enforced transport boundary, independent custody, and a stronger
semantic verification story before it can be generalized.
