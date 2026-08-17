# Architecture assessment

## Decision

Create a dedicated project. No existing checkout is a suitable home for a
cross-repository verifier without making the experiment look like an
integration claim.

The first mechanism is a combination of:

1. an artifact format carrying a typed envelope;
2. a transformation protocol carrying declarations and hashes;
3. an independent verifier comparing input and output;
4. an external evidence/authorization registry; and
5. an append-only lineage store.

It is not yet a gateway, service, cryptographic ledger, or LLM integration.

## Inspected repositories

The local checkouts were inspected at the following heads:

| Repository | Current local head | Finding relevant to the kernel |
| --- | --- | --- |
| `CCC` | `7daad9eed81dad8091fa8255f724bf3a38b97e75` | Strong typed provenance/epistemic/evidence/lineage managers; JSON persistence and lower-level store mutation remain distinct from independent transition verification. |
| `Triad-42` | `ef3b1962e19f8643725ff13014c3052be7428ffd` | Explicit epistemic labels, human authorization, support roots, and erasure cascade; the package intentionally does not perform substantive truth reasoning. |
| `innovation_os` | `d8fd9b844de032ff6af71a689172c0775c8a95b4` | Typed provenance statuses and events, but lineage/provenance components are local mechanisms rather than a shared runtime protocol. |
| `sentinel_os` | `7755e6772d2c937c558076b7da72394eac231be2` | EventV1 separates verified, attested, and estimated observations; cassette validation and ledger controls are domain/governance mechanisms. |
| `GSA-815` | `9bbd6e2efa8df11de7e7b231635850df22205029` | `DEPENDENCIES.md` explicitly describes a source/runtime dependency on Sentinel modules, not a repository-native semantic transmission contract. |
| `synapsis` | local branch is ahead and has user modifications | Code-intelligence/memory models and snapshots; not used as a conservation authority. |
| `resume_os` | `6acdfb9843589ed79ee7375eafbebcafc38eecf2` | Source hashing, draft/promotion gates, line-level provenance, and drift checks; useful local pattern, not a cross-system verifier. |
| `Ecology` | GitHub `590c90e0fffa04741f168c1d147b2049aa3639be` | Corpus/extraction/research environment with large extracted corpus and tests; deliberately excluded from the first runtime experiment. |

The `sentinel_os` checkout contains an unrelated untracked synthetic CSV and a
permission-restricted `ledger_data` directory. No files there were changed.
The existing user modifications in `synapsis` were also left untouched.

## Reusable ideas and unsafe assumptions

Reusable ideas include CCC's separate provenance/evidence chains, Triad-42's
human-root requirement, Sentinel's verified/attested/estimated distinction,
and Resume OS's promotion gate and drift checks.

The kernel does not import those packages. Importing them would inherit their
caller discipline and would make a passing local test ambiguous: it would no
longer be clear whether the new mechanism independently verified a transition
or merely used an existing manager correctly.

## Minimum invariant

For every submitted transformation:

> A protected proposition-level distinction may change only when the output,
> declaration, and external event/evidence records jointly satisfy the
> transition rule. If the verifier cannot establish that condition, the
> result is not `PASS`.

Content may change. The minimum implementation therefore permits a declared
content transformation while explicitly reporting semantic content
equivalence as unverified.
