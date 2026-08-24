# ADR-0070: DecisionOpportunity Event Runtime

## Status

Accepted for v0.70.0. Installation and runtime execution are not authorized.

## Context

The v0.69 preregistration replaced the old all-540-slots-or-fail rule with a
four-hour `DecisionOpportunity` whose immutable outcome is `OBSERVED` or
`MISSED`. The project needs a durable implementation of that fact model before
adding Binance simulation, lifecycle evaluators or deployment authority.

The v0.66 event store already provides retained directory capabilities,
canonical bytes, no-overwrite publication, fsync durability, optimistic parent
hashes and fresh-process replay. Rebuilding that storage would add risk without
adding project-specific value.

## Decision

v0.70.0 keeps the v0.66 event store unchanged and adds a separate v3 semantic
projection. The same append-only canonical log remains the only authority.
The storage envelope's legacy `slot_id` field must equal the v3
`opportunity_id`, but all new public semantics use opportunity terminology.

An observed fixture follows
`INPUT_PREPARED -> RESULT_PREPARED -> OPPORTUNITY_OBSERVED`. An expired
opportunity can terminate directly, after INPUT, or after RESULT as
`OPPORTUNITY_MISSED`. MISSED is never rewritten or backfilled, but the next
natural four-hour opportunity may continue. Catch-up only accepts explicit
fixture/orchestration time boundaries, records expired opportunities in order,
and performs no market, decision, simulation, Broker, order or export call.

v0.70's result evidence is fixture-only structural evidence. It binds canonical
opaque source/decision hashes, observation time and zero authority counts. It
does not validate Binance market semantics or the v3 trading policy and cannot
be consumed as production observation evidence. That work remains v0.71.

Canonical event projection is boundary-free. Coverage health is a separate
read-only overlay requiring explicit start/detected boundaries. Coverage is an
exact integer fraction and the 95% threshold uses integer cross multiplication;
there is no float/Decimal context dependence and no PnL field.

## Rejected alternatives

- Modifying the v2 runtime in place would mix permanent-failure slot semantics
  with recoverable v3 opportunities and weaken replay isolation.
- Adding SQLite, a derived authoritative export, or a second scheduler would
  duplicate infrastructure and create competing facts.
- Implementing Binance fills, risk, lifecycle evaluators and deployment in the
  same release would make review boundaries too large and could overstate a
  fixture-only state machine as trading readiness.
- Treating a missed opportunity as observed from historical data would violate
  the frozen no-backfill contract.

## Authority boundary

- `production_activation=false`
- `runtime_install_authorized=false`
- `replacement_start_authorized=false`
- `real_orders_allowed=false`
- `no seven-day timer started`
- `no 90-day timer started`

This release is fixture-only. It installs no service, opens no production root,
reads no credential, makes no market/account/Broker request, creates no order
and moves no funds. It is not evidence of profitability, AI advantage, Paper
completion, operational qualification, Canary eligibility or live fitness.

## Consequences

v0.71 may bind real deterministic Binance Spot/perpetual simulation semantics
to the event stages. v0.72 may add the independent operational/economic
evaluators and observer/UI wiring. Deployment, start, credentials and Canary
activation remain a later exact trust-chain decision.
