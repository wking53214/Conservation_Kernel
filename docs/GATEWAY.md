# The transport / gateway boundary

This kernel enforces conservation only at the boundary where it is invoked. A
caller who never submits a transformation stays outside the mechanism. Making
enforcement mandatory needs a transport boundary, a choke point that every
downstream artifact must pass through. That is out of scope here (see
[`THREAT_MODEL.md`](THREAT_MODEL.md), [`REPORT.md`](REPORT.md) where "a
library alone prevents bypass" is `FALSIFIED`).

This document records that the boundary now has a **working reference
implementation** outside this repository, and the design points that make it
work, so the "would need a gateway" statement is no longer purely
hypothetical.

## Reference implementation

`wking53214/GEMS`, directory `transport/` (landed in commit `5dbfeb7`, confirmed 2026-11-08).
`ConservationGateway` (`transport/gems_transport/transport.py`) wraps this
kernel as the only accepted-artifact boundary; `Pipeline` only forwards
artifacts the gateway accepted. It is unwired salvage there. Its directory has
no unit tests (GEMS' tests import the transport package only for the CNS connector, CNS independence and TIE adapter checks; none was confirmed to exercise the gateway itself),
and it is verified only by an experiment.

Result against kernel commit `dbbb22b`. This is historical, not current:

On 2026-11-08 the experiment did not run against current main. The kernel now
refuses to build without a root guard, and GEMS does not pass one. With those
guards switched off in a scratch run, the GEMS root artifacts are refused,
because a root FACT must cite evidence about its own proposition and the
fixtures do not. The 20/20 result therefore describes the kernel at `dbbb22b`.
It stays unreproduced until GEMS updates its fixtures and construction.

| metric | value |
| --- | --- |
| hostile transformations rejected or contained at the gateway | 20 / 20 |
| same transformations accepted on the bypass (no-gateway) control path | 20 / 20 |
| reference 5-Gem pipeline + human-approval fixture | accepted |

The control column is the point: the kernel does not change behaviour: the
transformations are bad either way. The gateway is what makes the rejection
unavoidable for anything downstream.

## What makes a gateway sound

Three properties a sound gateway needs. A 2026-11-08 read of GEMS' transport code confirmed the first two. The third needs qualifying, as noted below:

1. **A transformer's output is an untrusted proposal, never an accepted
   artifact.** It becomes an artifact only after the kernel accepts it.
2. **The gateway resolves the input artifact from its own accepted-artifact
   map**, not from whatever the request declares its input to be. A request
   cannot name an artifact the gateway never accepted.
3. **Only one path promotes a candidate**: the gateway's `submit()`, and only
   if the kernel accepts. Source roots are the exception. They enter through a
   separate ingest path that admits only parentless artifacts, after the kernel's
   root admission has accepted them.

A gateway missing any of these re-opens the bypass it was meant to close.

## Runtime loop safety

Retry exhaustion, repeated-output detection, and A-B/A-B or longer
oscillation detection are runtime concerns, not conservation invariants. They
belong in the gateway or orchestration layer, which can retain bounded
execution state and apply context-specific retry policy. The kernel should
remain stateless with respect to runtime history and should not reject a
repeated artifact solely because it was repeated.

## Kernel boundary

The kernel still verifies; it still cannot stop
an application that refuses to call the gateway. Custody of the gateway's own
accepted-artifact store, and durable/witnessed persistence, remain separate
unsolved problems (see [`LIMITATIONS.md`](LIMITATIONS.md)).
