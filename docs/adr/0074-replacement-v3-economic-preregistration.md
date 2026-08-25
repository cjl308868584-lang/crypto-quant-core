# ADR 0074: Replacement v3 economic preregistration

## Status

Accepted for the v0.74 release candidate. This decision freezes a plan for a
future 90-day economic evaluation. It does not implement that final evaluator,
read an economic outcome, install or start runtime services, or grant trading
authority.

## Considered alternatives

1. Reuse the v0.44 episode evaluator. Rejected because its long-only,
   540-slot fixed-notional proxy population does not represent replacement-v3
   DecisionOpportunity outcomes, mutually exclusive Spot-long/perpetual-short
   positions, marked equity, funding, or recoverable flat misses.
2. Evaluate only total PnL and drawdown. Rejected because a small number of
   lucky cycles could pass without time-stability, uncertainty, or missingness
   protection.
3. Use a daily marked-equity series with fixed robustness gates. Selected.
   The primary endpoint is the one-sided lower confidence bound on mean daily
   net return from the preregistered moving-block bootstrap (MBB), with
   deterministic secondary economic, coverage, cycle, product, time-block,
   drawdown, and stressed-friction gates.

## Decision

The future evaluator will derive 91 pre-action UTC daily boundary equities and
90 simple fixed-capital daily net returns from the exact half-open 90-day
DecisionOpportunity population. The fixed MBB uses overlapping non-circular
seven-day blocks, 10,000 resamples, seed `2026082574`, deterministic SHA-256
rejection-sampled block starts, and a conservative nearest-rank 5th-percentile
lower bound. PASS requires that bound to be strictly positive and every other
sample and economic gate to pass.

Missingness is bounded rather than selected away. An optimistic flat-miss bound
assigns zero economic change; a pessimistic bound deducts one frozen E0
stopped-cycle loss of `1.25 USDT` for each distinct flat miss. Both bounds must
pass. Their disagreement is `INCONCLUSIVE_INSUFFICIENT_EVIDENCE`. Observed
coverage must be at least `0.95`, terminal coverage must equal `1`, and exposed
misses, gap locks, unresolved positions, duplicate economic orders, unrecorded
fills, and reconciliation failures remain fail-closed boundaries.

## No-outcome and no-authority boundary

The v0.74 artifact contains only preregistered inputs, policies, gates, and
terminal semantics. It contains no result, observed price, fill, fee, funding,
PnL, drawdown, daily return, confidence interval, bootstrap replicate, or
provisional gate value. The package adds no final evaluator, event reader,
installer, service launcher, network client, production writer, or outcome
reader.

`production_activation=false`

`runtime_install_authorized=false`

`replacement_start_authorized=false`

`real_orders_allowed=false`

`economic_outcome_reads=0`

`no seven-day timer started`

`no 90-day timer started`

Any final evaluator and any installation/start ceremony are future independent
milestones requiring their own reviewed authority. Even a future research gate
PASS would not prove profitability, AI advantage, Canary eligibility, or live
trading readiness.
