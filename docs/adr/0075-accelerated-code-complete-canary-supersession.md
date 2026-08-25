# ADR 0075: Accelerated code-complete and Canary supersession

## Status

Accepted for the v0.75 plan-only release candidate. This decision changes only
future operational qualification and incident-block recovery. It does not
install or start a service, grant credentials or account access, submit an
order, move funds, activate E0, start a 72-hour clock, or change the v0.74
90-day economic research contract.

## Decision

One append-only canonical DecisionOpportunity log remains the fact source.
The released v0.74 economic projection remains immutable. A separate future
operational projection will require one uninterrupted 72-hour healthy segment,
the frozen fault matrix, and a separately approved minimum-size Binance
operational ceremony before E0 may be considered.

Ceremony events carry the label
`OPERATIONAL_CEREMONY_NOT_STRATEGY_EVIDENCE` and are excluded from strategy
cycles, simulation performance, stage cycle counts, and the 90-day economic
population. Operational failures and incident unlocks cannot rewrite events,
failed blocks, or the economic start/window.

The four absolute stage-block hard stops are unresolved economic-order
UNKNOWN, venue/local position mismatch, perpetual exposure without a valid
protective stop, and an attempt to add risk after the stage loss limit. Each
fails the current block; after verified flatness, immutable incident evidence,
and separate unlock approval, a new block may start without erasing history.

## Rejected alternatives

1. Rewrite v0.74 in place. Rejected because it would retrospectively alter a
   preregistered economic question.
2. Reset replacement v3 as a new research generation. Rejected because an
   operational eligibility change does not justify discarding research facts.
3. Count deliberately forced ceremony trades as strategy evidence. Rejected
   because they do not represent natural strategy decisions.

## No-authority boundary

`ACCELERATED_CANARY_PLAN_PREREGISTERED_NOT_ACTIVATED`

`production_activation=false`

`runtime_install_authorized=false`

`credentials_allowed=false`

`real_orders_allowed=false`

`fund_movement_allowed=false`

`no 72-hour timer started`

`no 90-day timer started`

The v0.76/v0.77 code-complete bundles and every real installation, credential,
ceremony, funding, E0/E1/E2, and incident-unlock action remain separate future
gates.
