# Conservation Kernel

## Adversarial Enforcement of Epistemic Conservation

The Conservation Kernel is an independently testable mechanism for evaluating whether machine-mediated transformations preserve protected epistemic and provenance distinctions.

Its central question is not:

> "Is this claim true?"

The kernel asks a narrower and more fundamental question:

> "Did this transformation preserve the properties that were supposed to remain conserved?"

This distinction is important because a transformation can produce output that appears reasonable while silently changing its provenance, evidence, authority, certainty, or historical state.

The Conservation Kernel is designed to detect those changes.

---

## Core Principle

Machine-mediated systems continuously transform information.

A source becomes an interpretation.

An interpretation becomes a claim.

A claim becomes a structured artifact.

An artifact may then be passed through additional systems.

At every transformation boundary, information can be silently promoted, degraded, detached from its origin, or otherwise altered.

The Conservation Kernel treats certain properties as protected state.

Conceptually:

    INPUT ARTIFACT
          │
          ▼
    MACHINE TRANSFORMATION
          │
          ▼
    OUTPUT ARTIFACT
          │
          ▼
    CONSERVATION CHECK
          │
       ┌──┴──┐
       │     │
    PRESERVE  VIOLATE
       │     │
       ▼     ▼
     ACCEPT  REJECT

The purpose is to make silent epistemic transformation detectable.

---

## What Is Conserved?

The kernel focuses on distinctions that can be lost during machine transformation.

These include:

- provenance;
- evidence;
- authority;
- certainty;
- historical state;
- and the relationships connecting those properties to an artifact.

The exact protected properties depend on the artifact and transformation being evaluated.

The governing principle is:

> A transformation must not silently change a protected epistemic property merely because the resulting output appears plausible.

---

## Immutable Input and Output

The kernel operates over explicit input and output artifacts.

The input represents the state before transformation.

The output represents the state after transformation.

The comparison is performed against immutable representations rather than relying solely on mutable application state.

Conceptually:

    IMMUTABLE INPUT
          +
    DECLARED TRANSFORMATION
          +
    OBSERVED EFFECTS
          +
    EXTERNAL REGISTRIES
          ↓
    CONSERVATION EVALUATION
          ↓
    RESULT

This provides a concrete boundary at which conservation can be evaluated.

---

## Declared Transformation

A transformation is not treated as an unexplained change from one object to another.

The kernel models the transformation itself.

This allows the evaluator to distinguish:

    WHAT WAS SUPPOSED TO CHANGE

from:

    WHAT ACTUALLY CHANGED

That distinction is central to detecting silent promotion or degradation.

---

## Observed Transformation Effects

The kernel evaluates observed effects against the declared transformation and the protected state of the artifacts.

A transformation may legitimately change some properties while being prohibited from changing others.

For example:

    CONTENT
       MAY CHANGE

    PROVENANCE
       MAY NOT CHANGE SILENTLY

    AUTHORITY
       MAY NOT BE SELF-PROMOTED

    CERTAINTY
       MAY NOT BE SILENTLY INCREASED

The conservation check therefore focuses on whether protected distinctions survived the transformation.

---

## External Evidence and Authorization

The kernel does not assume that all required information is contained inside the transformed artifact.

Evidence and authorization can be represented through external registries.

This allows the evaluator to ask questions such as:

- Is the claimed evidence actually present?
- Does the transformation have the required authority?
- Is the authority applicable to this operation?
- Does the resulting artifact remain supported?
- Did the transformation create an unsupported promotion?

This separates the artifact being transformed from the external facts required to validate the transformation.

---

## Epistemic Conservation

The central concept is epistemic conservation.

Epistemic conservation means preserving the distinctions that determine what an artifact represents and how strongly it can be treated as supported.

A transformation should not silently perform transitions such as:

    INFERENCE
       ↓
    FACT

    PROPOSAL
       ↓
    AUTHORITY

    INTERPRETATION
       ↓
    HISTORICAL RECORD

    UNSUPPORTED CLAIM
       ↓
    EVIDENCE-BACKED CLAIM

unless the required supporting conditions for that transition are explicitly satisfied.

The kernel exists to make these transitions observable and testable.

---

## Provenance Conservation

Provenance identifies where information came from.

A transformation may alter representation without altering origin.

The kernel therefore treats provenance as a protected property rather than assuming that a new output object automatically inherits legitimate provenance.

This helps expose transformations in which:

    MACHINE OUTPUT
          ↓
    NEW ARTIFACT
          ↓
    HUMAN-ORIGINATED APPEARANCE

is incorrectly inferred merely from the transformation itself.

---

## Evidence Conservation

Evidence must remain connected to the claims it supports.

The kernel can evaluate whether the resulting state remains structurally supported by the available evidence relationships and registries.

The objective is not to determine whether evidence is philosophically sufficient.

The objective is to detect structural loss or fabrication of support across a transformation boundary.

---

## Authority Conservation

Authority is distinct from provenance and evidence.

An artifact can have:

- valid provenance;
- supporting evidence;
- and still lack the authority required for a particular transition.

The kernel therefore treats authorization as an independently evaluable property.

This prevents a transformation from implicitly deriving authority merely because information was available to the system.

---

## Certainty Conservation

A transformation can unintentionally increase apparent certainty.

For example:

    POSSIBLE
       ↓
    LIKELY
       ↓
    ESTABLISHED
       ↓
    FACT

Each promotion changes the epistemic meaning of the information.

The kernel treats such changes as conservation-sensitive when the transformation has not established the conditions necessary to justify them.

---

## Historical-State Conservation

Historical state is not equivalent to current interpretation.

A later transformation may reinterpret an earlier artifact without rewriting the fact that the earlier state existed.

The kernel therefore treats historical state as a protected distinction.

Conceptually:

    HISTORICAL STATE
          │
          ├── later interpretation
          ├── correction
          └── supersession

The later state does not automatically erase the earlier state.

---

## Hostile Baseline

The kernel is intentionally small and adversarial.

It is not designed to make transformations appear safe.

It is designed to attempt to falsify the claim that they are safe.

The testing philosophy is therefore:

> Assume the transformation can cheat.

Then attempt to demonstrate that it did.

The hostile baseline focuses on adversarial conditions such as:

- provenance manipulation;
- unsupported evidence;
- authority substitution;
- certainty promotion;
- historical-state alteration;
- transformation mismatch;
- and transactional failure.

---

## Transactional Integrity

The repository also contains explicit testing around transactional rollback.

This addresses an important failure mode:

> What happens if a transformation or validation process fails after partially modifying state?

A failed operation should not leave the system in an invalid intermediate condition.

The transactional objective is therefore:

    BEGIN
      ↓
    APPLY
      ↓
    VALIDATE
      │
    ┌─┴─┐
    │   │
   PASS FAIL
    │   │
    ▼   ▼
 COMMIT ROLLBACK

Conservation is therefore evaluated not only as a logical property but also in the presence of operational failure.

---

## What the Kernel Does Not Do

The Conservation Kernel does not determine whether a claim is true in the external world.

It does not function as:

- a general-purpose fact checker;
- a truth oracle;
- a complete authorization system;
- a production database;
- an identity provider;
- or a universal AI governance platform.

Its scope is deliberately narrower.

The kernel evaluates whether a claimed transformation is structurally supported and whether protected distinctions have been silently changed.

---

## Why This Boundary Matters

A system may be unable to determine whether a claim is objectively true while still being able to determine that:

- its provenance was changed;
- its evidence disappeared;
- its authority was fabricated;
- its certainty was promoted;
- its historical state was altered;
- or its declared transformation does not explain its observed effects.

That creates a useful enforcement boundary.

The kernel does not need to solve truth in order to detect certain forms of epistemic corruption.

---

## Architecture

The repository separates the conservation problem into independently testable components.

At a conceptual level:

    ARTIFACT
       │
       ├── provenance
       ├── evidence
       ├── authority
       ├── certainty
       └── historical state
              │
              ▼
       TRANSFORMATION
              │
              ▼
       OBSERVED OUTPUT
              │
              ▼
       CONSERVATION EVALUATION
              │
       ┌──────┴──────┐
       │             │
    CONSERVED     VIOLATED
       │             │
       ▼             ▼
     ACCEPT        REJECT

The repository is intentionally structured so the conservation mechanism can be tested independently of a larger application.

---

## Repository Independence

The Conservation Kernel is not architecturally bound to a single repository or application.

It operates on artifacts, transformations, evidence, and authorization rather than on a hard-coded repository connection.

This allows the same conservation mechanism to serve as a reusable enforcement primitive across different systems.

Conceptually:

    REPOSITORY A ─┐
    REPOSITORY B ─┤
    REPOSITORY C ─┼──► CONSERVATION KERNEL
    REPOSITORY D ─┤
    REPOSITORY E ─┘

The kernel evaluates the transformation boundary.

The surrounding application determines when and how that boundary is invoked.

This distinction is important:

    REUSABLE CONSERVATION MECHANISM
              ≠
    SINGLE-APPLICATION CONNECTOR

---

## Experiments

The repository contains an `experiments/` area for executable exploration of the conservation model.

Experiments are intended to demonstrate the behavior of the kernel under controlled transformations and hostile conditions.

The purpose is not merely to demonstrate successful cases.

The more important objective is to expose where conservation fails.

---

## Tests

The repository contains a dedicated test suite covering the kernel and its failure modes.

Run:

    python3 -m pytest -q

Run the executable experiment:

    PYTHONPATH=src python3 experiments/run_experiment.py

---

## Adversarial Testing Philosophy

A normal unit test often asks:

> "Does the system behave correctly when used correctly?"

The Conservation Kernel asks an additional question:

> "Can the system be tricked into accepting a transformation that violates the protected invariant?"

This changes the testing objective.

The adversarial test attempts to produce a false acceptance.

A strong result is therefore not simply:

    TEST PASSED

It is:

    HOSTILE TRANSFORMATION ATTEMPTED
              ↓
        INVARIANT HELD
              ↓
           REJECTED

---

## Conservation Boundary

The kernel establishes an important conceptual boundary:

    BEFORE TRANSFORMATION
             │
             ▼
       CONSERVATION KERNEL
             │
             ▼
    AFTER TRANSFORMATION

The kernel evaluates the transition rather than assuming that downstream systems will preserve the properties of the input.

This is important because a library can define an invariant without guaranteeing that every downstream consumer respects it.

The Conservation Kernel therefore serves as a foundation for a stronger enforcement architecture in which transformations must pass through a mandatory conservation boundary.

---

## Relationship to Governance

The kernel is not itself a complete governance system.

It provides a lower-level mechanism that governance systems can use to enforce continuity of epistemic and provenance properties.

Governance can determine:

- which properties are protected;
- who has authority;
- what transitions are permitted;
- and what policies apply.

The Conservation Kernel can then evaluate whether a transformation actually preserved those protected properties.

Conceptually:

    GOVERNANCE
         │
         │ defines constraints
         ▼
    CONSERVATION KERNEL
         │
         │ evaluates transformation
         ▼
    MACHINE TRANSFORMATION
         │
         ▼
       OUTPUT

This separates policy from the mechanism used to test conservation.

---

## Current Scope

The current repository is a focused hostile baseline.

It is intentionally small enough to reason about and independently test.

Its value is not in providing every capability required by a production governance system.

Its value is in establishing a concrete, testable answer to a narrower question:

> Can machine-mediated transformations be evaluated for preservation of protected epistemic and provenance distinctions?

---

## Known Architectural Boundary

The kernel can enforce conservation at the boundary where it is actually invoked.

It cannot, by itself, guarantee that every downstream system in a larger architecture will use the kernel.

This is a fundamental systems distinction:

    LOCAL ENFORCEMENT
          ≠
    UNIVERSAL ENFORCEMENT

Universal enforcement requires an architectural mechanism that makes the conservation boundary mandatory.

The kernel therefore represents the enforcement primitive, not the entire system-level enforcement architecture.

---

## Design Principles

### Preserve Provenance

Do not allow transformations to silently change where information came from.

### Preserve Evidence

Do not allow support relationships to disappear while the resulting claim remains represented as supported.

### Preserve Authority

Do not derive authority merely from possession of information or the ability to generate an output.

### Preserve Certainty

Do not silently increase epistemic certainty.

### Preserve Historical State

Do not rewrite the past to match the present.

### Explain Transformations

The resulting state should be explainable in terms of the declared transformation and observed effects.

### Fail Closed

When a protected invariant cannot be established, the safe result is rejection rather than silent acceptance.

### Attack the Invariant

Testing should attempt to falsify the conservation guarantee rather than merely demonstrating normal operation.

---

## Status

Conservation Kernel is an experimental, independently testable hostile baseline for epistemic conservation.

It provides a concrete mechanism for evaluating machine-mediated transformations against protected provenance, evidence, authority, certainty, and historical-state distinctions.

The repository is intentionally focused.

Its purpose is to establish the conservation problem, demonstrate executable enforcement of the core invariant, expose failure modes, and provide a foundation from which mandatory transformation-boundary enforcement can be developed.

The central proposition is:

> Machine transformation should not be allowed to silently change what an artifact means, where it came from, what supports it, who has authority over it, how certain it is, or what historical state it represents.