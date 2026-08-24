# ADR 0072: Fixture-only Binance lifecycle evidence

## Status

Accepted for the v0.72 release candidate. This decision authorizes deterministic
fixture evidence only; it does not authorize installation, service start,
accounts, credentials, exchange requests, orders or funds.

## Decision

Keep the project-specific decision/risk contract as authority and add the
smallest product-specific lifecycle needed to prove Spot-long and perpetual-
short intent, acknowledgement, fill, fee, stop, reconciliation and recovery
semantics. Three independent engine, venue and ledger projections must agree.
UNKNOWN, duplicate economic orders, conflicting fills, missing protection and
identity/durability failures remain fail closed.

The retained append-only opportunity event log remains the sole authority.
Result evidence v2 is constructed only from the typed lifecycle result. A
durable v2 RESULT cannot later become MISSED; fresh recovery must finish it as
OBSERVED. Portable Spot and perpetual complete-cycle goldens are fixture-only
and contain no event-root inode identity.

We rejected a generic Broker/order platform, a second scheduler, a monolithic
runtime and importing a third-party engine into the core. Those alternatives
would add infrastructure without improving this release's distinctive evidence
trust boundary. Nautilus remains isolated behind its separate comparison work.

## Verification boundary

The candidate proves deterministic fixture lifecycle, exact byte replay,
fresh-process crash recovery, stale optimistic conflict, canonical evidence and
complete-cycle reproduction. It makes no install, no account, no credential,
no real order, no funds, no Paper completion and no profitability claim.

`production_activation=false`

`runtime_install_authorized=false`

`replacement_start_authorized=false`

`real_orders_allowed=false`

`no seven-day timer started`

`no 90-day timer started`

No service or production root is created. This fixture-only result does not
establish profitability, AI advantage, Canary eligibility or live readiness.
