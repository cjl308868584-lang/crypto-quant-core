# ADR 0073: Replacement v3 readiness and tail-blind observation

## Status

Accepted for the v0.73 release candidate. This decision authorizes deterministic
fixture evaluation and read-only presentation only. It does not authorize
installation, service start, production roots, accounts, credentials, exchange
requests, Broker calls, orders, funds or Canary execution.

## Decision

Reduce the released append-only DecisionOpportunity evidence into two distinct
typed views. The operational view evaluates real-duration, coverage, lifecycle,
product-cycle and confirmed safety gates without granting operational authority.
The economic view exposes structural progress only and withholds all economic
values until a separately preregistered final evaluator exists.

The start boundary must bind the first verified natural OBSERVED opportunity.
MISSED events remain immutable: a flat miss may recover coverage through later
opportunities, while a miss during exposure preserves the released economic gap
lock and cannot be cleared by later good fixtures. Healthy, reconciled and
protected in-progress exposure remains collecting or pending; UNKNOWN,
unreconciled state, missing protection, risk locks, boundary breaches and
confirmed evidence failures fail closed.

Operations projection v2 consumes typed release, legacy Challenger, replacement
and System Paper observations. Its strict loader revalidates canonical UTC,
Decimal, identity, counts and self-hash. The existing loopback-only console uses
strict v1/v2 dispatch, keeps the same four GET routes, performs one same-origin
read and has no control surface. v1 projection and status bytes remain frozen.

We rejected a post-hoc economic evaluator, a second dashboard, a generic trading
engine and any install/start work in this version. Numerical economic thresholds
are not preregistered, so reaching 90 days can only report that the final
evaluator is unavailable; it cannot inspect economics or select a favorable
rule afterward.

## Verification and authority boundary

Independent complete review and targeted rereviews reached Critical 0 and
Important 0. Cross-component tests cover Spot and perpetual fixture streams,
confirmed safety failures, exposed and flat MISSED semantics, evidence-status
precedence, strict projection replay, deterministic alerts and read-only UI.

`production_activation=false`

`runtime_install_authorized=false`

`replacement_start_authorized=false`

`real_orders_allowed=false`

`no seven-day timer started`

`no 90-day timer started`

This candidate does not prove Paper completion, profitability, AI advantage,
Canary eligibility or live readiness.
