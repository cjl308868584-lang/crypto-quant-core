# Replacement v3 90-Day Economic Preregistration Design

**Status:** Approved design; plan-only implementation not yet started
**Target release:** v0.74.0
**Authority:** v0.69 replacement-v3 governance and the exact v0.73.0 release

## 1. Purpose

v0.73 deliberately withheld every economic value and final economic decision
because the replacement-v3 plan did not yet freeze exact metrics, thresholds,
cost treatment, missingness sensitivity or final-result semantics. v0.74 closes
that governance gap before any production economic start receipt or canonical
production DecisionOpportunity event can exist.

This release preregisters one deterministic 90-day research-continuation
evaluation. It does not evaluate an outcome, install or start a service, create
a production root, access Binance, use credentials, submit an order, move funds
or authorize a Canary stage.

## 2. Non-negotiable authority boundary

The release must preserve these values:

```text
production_activation = false
runtime_install_authorized = false
replacement_start_authorized = false
account_requests_allowed = false
credentials_allowed = false
broker_requests_allowed = false
real_orders_allowed = false
market_requests = 0
production_state_writes = 0
economic_outcome_reads = 0
```

The exact v0.69 plan, machine evidence, accountable owner attestation and
supersession record remain immutable. The user's exact acknowledgement
`I_SIGN_AND_ACCEPT_ACCOUNTABILITY_FOR_THE_EXACT_V3_DECLARATION` confirms the
existing v3 governance declaration; v0.74 does not create a replacement
attestation or broaden it into install, start, credential, order or funds
authority.

The plan binds the v0.69 plan and owner-attestation identities, the v0.70-v0.72
contracts and the annotated v0.73.0 release foundation. It never embeds a
mutable branch name or an unpeeled tag as authority.

## 3. Considered approaches

### 3.1 Reuse the v0.44 episode evaluator

Rejected. v0.44 is bound to a long-only, 540-slot, fixed-notional proxy cohort.
Replacement v3 uses DecisionOpportunity outcomes, mutually exclusive Spot-long
and perpetual-short positions, marked equity, funding and recoverable flat
misses. Reusing the old population would silently change the current research
question.

### 3.2 Total PnL plus drawdown only

Rejected. It is deterministic and inexpensive, but a small number of lucky
cycles could pass. It provides no time-stability, uncertainty or missingness
protection.

### 3.3 Daily marked-equity series with fixed robustness gates

Selected. The primary endpoint is a one-sided moving-block-bootstrap lower
confidence bound on mean daily net return. Deterministic secondary gates cover
total net PnL, drawdown, fixed time blocks, stressed frictions, product/cycle
coverage and missing-opportunity sensitivity.

## 4. Formal artifact

v0.74 publishes exactly one formal research artifact:

```text
artifacts/challenger-replacement/
  challenger-replacement-economic-evaluation-plan-v0.74.0.json
```

Its repository-relative schema is:

```text
src/crypto_quant/schemas/
  challenger-replacement-economic-evaluation-plan-v1.schema.json
```

The artifact uses canonical JSON, a self-excluding `plan_hash`, a stable
`plan_id`, exact-key schemas and no caller-provided economic values. A strict
loader rebuilds the expected plan and requires byte equality, file SHA-256,
self-hash, stable ID, foundation identities and all nested policy hashes.

The artifact contains no result, daily return, fill, fee, funding, PnL,
drawdown, bootstrap sample, confidence interval or pass/fail observation.

## 5. Source population and start boundary

The future evaluator may consume only a strict projection of the append-only
canonical DecisionOpportunity event log. Export files, dashboard projections,
account balances, exchange responses and manually supplied values are not
authority.

The independent economic start receipt must bind the same first verified
natural `OBSERVED` opportunity used by the operational start receipt. The two
receipts remain distinct artifacts, but these fields must be identical:

```text
opportunity_id
event_hash
scheduled_for
observed_at
plan_id
plan_hash
deployment_identity
event_root_identity
```

Install time, release time, preflight time, a fixture or a manually selected
opportunity cannot start the economic clock.

Define:

```text
start_scheduled_for = bound first OBSERVED scheduled_for
tail_scheduled_for = start_scheduled_for + 90 * 86400 seconds
window = scheduled_for >= start_scheduled_for
         and scheduled_for < tail_scheduled_for
```

Because 90 days is exactly divisible by the four-hour cadence, the tail remains
on the frozen opportunity grid. Every scheduled opportunity in the half-open
window must have exactly one canonical terminal outcome, `OBSERVED` or
`MISSED`. No historical decision backfill, reset or alternate start is allowed.

The future evaluator requires a tail-boundary pre-action mark derived from the
canonical source and prior projection at `tail_scheduled_for`. It must not
include a new entry or reversal at the tail. If that exact boundary cannot be
derived without an untrusted input, the result is inconclusive rather than
using the last convenient price.

## 6. Canonical economic series

The research capital and exposure baseline are frozen to the E0 simulation
contract:

```text
starting_virtual_equity_usdt = 100
capital_limit_usdt = 100
gross_exposure_limit = 0.5
technical_leverage_cap = 2
configured_simulation_leverage = 1
```

For each observed opportunity, the future evaluator replays the released
decision, lifecycle and accounting evidence. It accepts only exact Decimal
strings and reconciled Spot-long or perpetual-short projections. Economic
equity is:

```text
marked_equity = cash
                + conservative_marked_position_value
                - all accrued fees
                + signed funding cashflow
```

The production implementation must use the already released accounting
semantics rather than redefine this formula independently. Spot uses the
conservative bid mark; perpetual uses the canonical mark price and contract
multiplier. Fees, slippage and funding are included once and only once.

The evaluator constructs 91 pre-action UTC-aligned daily boundary equities at
`start_scheduled_for + k * 86400`, for `k = 0..90`. Daily net return is the
simple fixed-capital return:

```text
daily_net_return[k] =
    (boundary_equity[k] - boundary_equity[k - 1]) / 100
```

Binary float is forbidden. Intermediate Decimal arithmetic is unrounded;
canonical output uses the repository Decimal encoder. The primary series has
exactly 90 values and is not compounded or annualized.

## 7. Opportunity completeness and missingness sensitivity

An exposed `MISSED`, unresolved position, economic gap lock, unrecorded fill,
duplicate economic order or reconciliation failure is a confirmed failure
boundary. It is never imputed or repaired.

A flat `MISSED` remains in the population and does not alter history. The
future evaluator computes two preregistered bounds:

1. **optimistic flat-miss bound:** zero economic change for that opportunity;
2. **pessimistic flat-miss bound:** subtract one frozen E0 stopped-cycle loss
   for each distinct flat missed opportunity.

The pessimistic loss is:

```text
notional = 100 * 0.5 = 50 USDT
loss_rate = protective_stop_distance
            + 2 * market_order_slippage_per_side
            + 2 * taker_fee_per_side
          = 0.02 + 2 * 0.001 + 2 * 0.0015
          = 0.025
flat_miss_loss_usdt = 50 * 0.025 = 1.25
```

The fee term uses the greater of the frozen Spot and perpetual taker rates; a
future unequal-rate contract therefore cannot reduce the penalty. Funding
benefit is zero in this imputation. The same miss cannot be charged twice.

PASS requires both bounds to pass every applicable economic gate. If the
optimistic result passes and the pessimistic result does not, the only result
is `INCONCLUSIVE_INSUFFICIENT_EVIDENCE`. The evaluator may not select the
favorable bound.

Observed coverage is `OBSERVED / (OBSERVED + MISSED)` for the exact half-open
window and must be at least `0.95`. Terminal coverage must equal `1`.

## 8. Statistical design

The primary hypothesis is:

```text
H0: mean daily net return <= 0
H1: mean daily net return > 0
```

The one-sided family-wise alpha is `0.05`; there is one primary hypothesis and
no multiple-testing adjustment. The fixed moving-block-bootstrap design is:

```text
method = OVERLAPPING_NON_CIRCULAR_MOVING_BLOCK_BOOTSTRAP
block_length_days = 7
sample_length = 90
resample_count = 10000
seed = 2026082574
draw_start_method = SHA256_REJECTION_SAMPLED_MBB_V1
quantile = CONSERVATIVE_NEAREST_RANK_0_05
confidence_level = 0.95
primary_endpoint = MEAN_DAILY_NET_RETURN_LCB95
minimum_economic_effect_daily = 0.0005
```

Each resample concatenates uniformly selected overlapping seven-day blocks in
original within-block order and truncates to 90 values. The lower bound is the
conservative nearest-rank fifth percentile of the 10,000 resampled means.

Block starts use the already released deterministic `_draw_start` contract.
For zero-based `replicate`, `draw` and `attempt`, hash the exact ASCII bytes
`MBB_V1:{seed}:{replicate}:{draw}:{start_count}:{attempt}`. Interpret SHA-256
as an unsigned big-endian integer and use rejection sampling below
`2^256 - (2^256 mod start_count)` before reducing modulo `start_count`. No
language PRNG is permitted.

The minimum economic effect is a power/reporting input, not an alternate PASS
threshold. PASS still requires the observed LCB to be strictly greater than
zero. For the fixed achieved-power calculation, subtract the observed sample
mean from every bootstrap mean, take the conservative nearest-rank 95th
percentile of those centered errors as the critical value, and report the
fraction of all 10,000 errors for which
`minimum_economic_effect_daily + error > critical_value`. Achieved power must
be at least `0.80`; otherwise the result is inconclusive.

## 9. Fixed sample gates

All gates are preregistered and conjunctive:

```text
calendar_days == 90
daily_return_count == 90
terminal_coverage == 1
observed_coverage >= 0.95
completed_cycle_count >= 12
spot_completed_cycle_count >= 3
perpetual_completed_cycle_count >= 3
nonempty_15_day_block_count == 6
moving_block_count >= 12
achieved_power_at_mere >= 0.80
```

A completed cycle begins with a verified flat-to-exposed transition and ends
with the matching verified exposed-to-flat transition. Partial fills belong to
one economic cycle; retries and duplicate observations never create another
cycle.

Insufficient sample gates yield `INCONCLUSIVE_INSUFFICIENT_EVIDENCE`; they do
not permit window extension, threshold changes or another start. This avoids
optional stopping. Technical evidence may continue to be retained after the
tail, but it cannot change the frozen evaluation population.

## 10. Economic gates

All gates must pass under both flat-miss bounds:

```text
MEAN_DAILY_NET_RETURN_LCB95 > 0
TOTAL_NET_PNL_USDT > 0
MAX_DRAWDOWN_FRACTION < 0.05
NONNEGATIVE_FIXED_15_DAY_BLOCKS >= 5 of 6
STRESS_1_5X_ADVERSE_FRICTION_TOTAL_NET_PNL_USDT >= 0
```

Maximum drawdown uses continuous high-water marked equity and the formula
`(peak - current) / peak`. Nonpositive equity is a confirmed gate failure.

The stress replay multiplies every nonnegative fee and adverse slippage cost by
`1.5`. Negative funding cashflow is multiplied by `1.5`; positive funding
benefit is multiplied by `0.5`. Gross market movement, quantities, product
selection and event order remain unchanged. Any cost component that cannot be
reconstructed exactly from released evidence makes the result inconclusive;
zero substitution is forbidden.

The six time blocks are the half-open intervals starting at
`start_scheduled_for + n * 15 days`, for `n = 0..5`. A block is nonnegative
when its sum of daily net returns is greater than or equal to zero.

## 11. Final state machine

Before `tail_scheduled_for`, the observer may expose structural progress only.
No component may read, print, log, persist or serve interim PnL, returns,
drawdown, fees, funding, confidence intervals, block ranks or provisional gate
values.

At the first eligible final evaluation:

1. an invalid plan, identity mismatch, malformed event, duplicate authority,
   missing tail mark or unreadable evidence returns
   `INCONCLUSIVE_INSUFFICIENT_EVIDENCE` and denies research continuation;
2. a confirmed safety/risk boundary, exposed miss, economic gap lock,
   nonpositive equity or trusted sufficient evidence failing an economic gate
   returns `RESEARCH_CONTINUATION_GATE_DID_NOT_PASS`;
3. trusted evidence with any sample gate shortfall or disagreement between the
   optimistic and pessimistic flat-miss bounds returns
   `INCONCLUSIVE_INSUFFICIENT_EVIDENCE`;
4. only trusted sufficient evidence passing every gate under both bounds
   returns `RESEARCH_CONTINUATION_GATE_PASS`.

The first canonical final artifact is immutable. PASS, DID_NOT_PASS and
INCONCLUSIVE are all publishable outcomes. No rerun, threshold override,
sample deletion, alternate seed, alternate start or favorable-result selection
is allowed.

PASS grants only permission to discuss the next research stage. It does not
prove sustainable profitability, AI advantage, Canary eligibility or live
trading readiness.

## 12. Plan implementation boundary

v0.74 may add only:

```text
src/crypto_quant/challenger_replacement_economic_plan.py
src/crypto_quant/schemas/
  challenger-replacement-economic-evaluation-plan-v1.schema.json
artifacts/challenger-replacement/
  challenger-replacement-economic-evaluation-plan-v0.74.0.json
tests/test_challenger_replacement_economic_plan.py
tests/test_challenger_replacement_v074_release.py
docs/adr/0074-replacement-v3-economic-preregistration.md
docs/implementation-status-v0.74.0.md
```

plus the minimal package/build manifest/current-release documentation changes
required for a semantic release. A parameterless production builder and strict
loader are allowed. A final evaluator, runtime event reader, network client,
installer, observer, scheduler, dashboard change, credential interface,
Broker, order adapter or production-root writer is not.

## 13. Verifiable acceptance criteria

1. v0.69-v0.73 formal artifact bytes and peeled release identities remain
   unchanged;
2. schema, builder, loader and committed artifact agree byte-for-byte;
3. every metric, threshold, cost formula, seed, block rule, missingness bound
   and final status is explicit and caller-invariant;
4. builder and loader expose no PnL, price, fee, funding, threshold, seed, start,
   tail or result override;
5. no code path reads an event log, production root, account, credential,
   network, Broker, order, funds or economic outcome;
6. mutation tests reject every foundation, policy, sample, economic and
   state-machine change;
7. frozen v0.69-v0.73 loaders and fixture hashes replay unchanged;
8. focused and adjacent tests, one final local full suite, compileall,
   `make validate`, diff-check and forbidden-authority scan pass;
9. independent complete review reaches Critical 0 and Important 0;
10. public PR CI, merged-main CI and annotated `v0.74.0` tag identity are
    verified only after the separately applicable remote-release gate.

Healthy completion proves only
`ECONOMIC_EVALUATION_PLAN_PREREGISTERED_NOT_STARTED`. It does not start either
the seven-day operational clock or the 90-day economic clock.

## 14. Subsequent milestones

After v0.74, independently reviewed versions may implement the frozen final
evaluator and strict deployment/start adapter. Installation and natural start
remain separate explicit actions. A future first natural start receipt must
bind the exact v0.74 plan and evaluator build identity before either real-time
clock begins.

No later version may change this plan after a production economic start. A new
hypothesis would require a separately named research generation, a new
pre-start governance decision and no reuse of the v3 outcome.
