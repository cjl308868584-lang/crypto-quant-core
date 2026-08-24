# ADR 0071: Fixture-only Binance accounting core

## Status

Accepted for the v0.71 candidate. The order lifecycle and event integration are
not implemented and are preregistered for v0.72.

## Decision

Keep v0.71 as a pure, credential-free, fixture-only boundary. It validates
canonical Binance fixture inputs and deterministically computes plan-bound
decisions, signed Spot-long/perpetual-short accounting, conservative fills,
fees, funding, margin, equity, exposure, and risk transitions. The products are
mutually exclusive and reversal requires a later opportunity.

The Task 4 checkpoint consumed 1,199 of the 1,200 approved net production-line
budget. We therefore rejected post-hoc expansion of the budget and moved order,
fill, UNKNOWN, stop, reconciliation, crash recovery, v2 result evidence, and
complete-cycle goldens to v0.72.

The only formal v0.71 artifact is the canonical simulation contract. It retains
the exact negative authority object. It is not a runtime or trading contract.

## Safety boundary

`production_activation=false`

`runtime_install_authorized=false`

`replacement_start_authorized=false`

`real_orders_allowed=false`

`no seven-day timer started`

`no 90-day timer started`

No service was installed or started; no production root, network, account,
credential, Broker, order, or funds were used. This fixture-only release does
not establish profitability, AI advantage, Paper completion, Canary eligibility,
or live-trading readiness. The lifecycle not implemented boundary is explicit.
