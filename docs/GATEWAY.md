# The transport / gateway boundary

This kernel enforces conservation only at the boundary where it is invoked. A
caller who never submits a transformation stays outside the mechanism. Making
enforcement mandatory needs a transport boundary — a choke point that every
downstream artifact must pass through. That is out of scope here (see
[`THREAT_MODEL.md`](THREAT_MODEL.md), [`REPORT.md`](REPORT.md) where "a
library alone prevents bypass" is `FALSIFIED`).

This document records that the boundary now has a **working reference
implementation** outside this repository, and the design points that make it
work — so the "would need a gateway" statement is no longer purely
hypothetical.

## Reference implementation

`wking53214/GEMS`, directory `transport/` (landed in commit `5dbfeb7`).
`ConservationGateway` (`transport/gems_transport/transport.py`) wraps this
kernel as the only accepted-artifact boundary; `Pipeline` only forwards
artifacts the gateway accepted. It is unwired salvage there, has no unit
tests, and is verified only by an experiment — but the experiment runs
against the current kernel and is reproducible.

Result against this kernel (`dbbb22b`):

| metric | value |
| --- | --- |
| hostile transformations rejected or contained at the gateway | 20 / 20 |
| same transformations accepted on the bypass (no-gateway) control path | 20 / 20 |
| reference 5-Gem pipeline + human-approval fixture | accepted |

The control column is the point: the kernel does not change behaviour: the
transformations are bad either way. The gateway is what makes the rejection
unavoidable for anything downstream.

## What makes a gateway sound

Three properties, all present in the reference implementation:

1. **A transformer's output is an untrusted proposal, never an accepted
   artifact.** It becomes an artifact only after the kernel accepts it.
2. **The gateway resolves the input artifact from its own accepted-artifact
   map**, not from whatever the request declares its input to be. A request
   cannot name an artifact the gateway never accepted.
3. **Only one path promotes a candidate** — the gateway's `submit()`, and
   only if the kernel accepts. There is no side door that writes to the
   accepted set.

A gateway missing any of these re-opens the bypass it was meant to close.

## What this does not add

No core kernel code changed. The kernel still verifies; it still cannot stop
an application that refuses to call the gateway. Custody of the gateway's own
accepted-artifact store, and durable/witnessed persistence, remain separate
unsolved problems (see [`LIMITATIONS.md`](LIMITATIONS.md)).
