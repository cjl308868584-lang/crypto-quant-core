# v0.76 Public Simulation and Research Bundle Design

**Date:** 2026-08-26
**Target release:** `v0.76.0`
**Status:** in-chat design and public-input correction approved; corrected exact
written spec awaiting review
**Release class:** code, schemas, deterministic fixtures and candidate
configuration only; no installation, activation, credential, account, order or
fund authority

## 1. Decision

v0.76 completes the public-simulation and research half of the accelerated
`CODE_COMPLETE_NOT_ACTIVATED` program frozen by v0.75. It does this by composing
the already released replacement-specific components rather than creating a
second scheduler, storage engine, broker, exchange platform or Web application.

The release adds five narrowly bounded capabilities:

1. a production-qualified, public-market deterministic simulation path over the
   existing DecisionOpportunity fact source;
2. a four-hour installed-runtime candidate and v3 deployment/start trust
   bindings, without executing installation or start;
3. a pure 72-hour operational qualification evaluator and strict result loader;
4. the final v0.74-bound 90-day economic evaluator and strict result loader; and
5. a versioned read-only operations projection consumed by the existing v0.61
   loopback console.

The append-only canonical DecisionOpportunity event log remains the sole fact
source. Projections, evaluator results, exports and the Web console are
read-only derivatives. v0.76 does not install or start a service, create a
production root or start receipt, issue a network request during release, read
economic outcomes, access a Binance account, read a credential, submit an order
or move funds.

The only valid release claim is:

```text
PUBLIC_SIMULATION_AND_RESEARCH_CODE_RELEASED_NOT_ACTIVATED
```

It is not `CODE_COMPLETE_NOT_ACTIVATED`, a 72-hour qualification result, a
90-day economic result, ceremony authority, E0 authority, a profitability
claim or an AI-advantage claim.

## 2. Immutable foundation

### 2.1 v0.75 release identity

The candidate must bind and test the exact public predecessor:

```text
repository = cjl308868584-lang/crypto-quant-core
visibility = PUBLIC
release_tag = v0.75.0
tag_object = 4bd4b2e21c760d6fad2a27903c67ee509ac116c9
peeled_commit = a51ed15d5a484e5bb9a54dc75a7fef4e8876e4d5
package_version = 0.75.0
manifest_version = 1.69.0
manifest_hash = b15479590536c302e173a41a758c9113cd7452b0000d8b6c5cb5c2ad8b9404d9
manifest_file_sha256 = df1695827975cbeb9c094b8182839e132219a52a19dc4166677a742d48442220
build_input_tree_hash = 07812c0a352dabab3742aa1c3417eaa8a8363e46a5059e49323f2b1c0d8a4a78
main_ci_run = 32869868571
```

The main CI identity is valid only because its Python 3.9, Python 3.12 and
macOS 15 arm64 jobs all completed successfully against the exact peeled
commit.

### 2.2 Frozen governance and economic artifacts

The following exact bytes remain immutable:

```text
v0.69 replacement-v3 plan file SHA-256
  6fae2ae0df4b8402ddc1df1b5bca611e11df41eee8d42f591d5d7b5fb24a31c3
v0.69 plan ID
  challenger_replacement_plan_v3_e1b6a4187cb4bb4b371ea503f83284056d4f0c6c504feb7827971869a52f666f
v0.69 plan hash
  f29474a1700b0c3cf313047e2d6e85182e68104d9584ec9df7b492aa7ab00486

v0.74 economic plan file SHA-256
  24fba7579ac36c037aaef4fbf34a69b56503358edbd64addbe01f30a70c33297
v0.74 plan ID
  challenger_replacement_economic_evaluation_plan_13ba2b74dd8c330732789a3fccd36f017847047f9fd07ea0bcf36b66f54a943e
v0.74 plan hash
  7c02267a0895cb3d8ceea79b6a38415140de23fb1cfcf3350c7fddff62089fa4

v0.75 accelerated plan file SHA-256
  31b9545a18850d068e858ae434a79e43967efd584df2cee9ff0833b1b203d6ee
v0.75 accelerated plan ID
  challenger_replacement_accelerated_canary_plan_b63c7416d6e317c2b4515bcfdbf72653cbaf64cb70b2c86f5a2c17995c9c3859
v0.75 accelerated plan hash
  3e86dc07d2cc96f3ea6f9005e1e02d4c8ddc9b2261f0abe28d53d029d2e53a80

v0.75 supersession file SHA-256
  8f7d2d551b20154dc5bc26316376386e721929fc81a2392fcb1ea692ad09049e
v0.75 supersession ID
  challenger_replacement_accelerated_canary_supersession_a89b315ad23b3e4616f6e64dcada5dd9c1fdea7056cff6cf225d055740bdef62
v0.75 supersession hash
  6829feedd51c397d2847329a237eb1188d8344894008d5a9ca38617c12be73cd
```

v0.76 must not rewrite any released plan, attestation, supersession, fixture,
manifest, tag or historical result. It must not reinterpret the old failed
cohort, v2 plan or 540-slot receipt as replacement-v3 authority.

### 2.3 Release authority

The v0.76 code release and all committed artifacts require:

```text
production_activation = false
runtime_install_authorized = false
replacement_start_authorized = false
credentials_allowed = false
account_requests_allowed = false
broker_requests_allowed = false
real_orders_allowed = false
fund_movement_allowed = false
ceremony_authorized = false
e0_activation_authorized = false
market_requests = 0
private_account_requests = 0
production_state_writes = 0
economic_outcome_reads = 0
operational_timer_started = false
economic_timer_started = false
```

Unit and integration tests may use explicit temporary owner-only roots and
deterministic fixtures. Test writes and fixture time never qualify as
production evidence.

## 3. Existing components and exact disposition

v0.76 is an integration release. The disposition of existing components is:

| Released component | Disposition in v0.76 |
|---|---|
| v0.67 public Binance time/kline adapter | Retain as the strict clock/Kline sub-capture; reuse its bounded HTTP transport in a versioned v0.76 composite public-market capture rather than create a second client |
| v0.67 four-hour LaunchAgent schedule | Retain six calendar invocations at minute 02; no generic scheduler |
| v0.68 snapshot/install/preflight/start primitives | Reuse descriptor and publication safety; add v3 directional bindings rather than rewrite v0.68 history |
| v0.70 DecisionOpportunity event protocol | Remains canonical fact source; add production-simulation evidence qualification through versioned schemas |
| v0.71 Decimal accounting and deterministic simulation contract | Remains the exact economic-math predecessor; its fixture-only contract, build whitelist and `CONFIRMED_FIXTURE` labels remain fixture-only and are not relabelled as public evidence |
| v0.72 lifecycle fixtures | Retain as golden fault/conformance inputs; fixture-labelled events never become production facts |
| v0.73 readiness evaluator | Retain historical seven-day behavior for v0.73 fixtures; implement a new v0.75-bound 72-hour evaluator rather than mutate it |
| v0.61 loopback console | Reuse server and safe rendering; add strict version dispatch only |

The following approaches remain rejected:

- copying System Paper SQLite/WAL deployment and observer code;
- importing the retired 540-slot evaluator;
- using a generic exchange, broker, scheduler, storage or UI framework;
- relabelling fixture lifecycle events as production simulation;
- treating an export or dashboard projection as authoritative;
- placing v0.77 private Binance behavior into v0.76.

## 4. Architecture and data flow

The only production-candidate flow is:

```text
verified local clock + fixed Binance public HTTPS GET set
                         |
                         v
strict v0.76 PublicMarketCaptureV2
  (exact v0.67 time/Kline sub-capture + Spot/perpetual rules,
   bid/ask, perpetual mark and exact-interval funding)
                         |
                         v
v3 public-simulation input + public-model contract adapter
                         |
                         v
v0.71-preserving decision/Decimal kernel + public simulation profile
                         |
                         v
versioned DecisionOpportunity canonical event bytes
        INPUT_PREPARED -> RESULT_PREPARED -> OBSERVED
                     or OPPORTUNITY_MISSED
                         |
                         v
append-only canonical event log (sole authority)
                  /                         \
                 v                           v
OperationalQualificationProjectionV2  EconomicResearchProjectionV1
                 |                           |
                 v                           v
72-hour strict result/observer         v0.74 final evaluator/result
                 \                           /
                  v                         v
          operations-projection-v3 (read-only derivative)
                            |
                            v
             existing 127.0.0.1 read-only console
```

No evaluator, observer, projection or UI route may append an event. The runtime
does not read evaluator outputs when deciding. A 72-hour operational status
cannot change the 90-day start, population or result, and the economic result
cannot grant account, order or fund authority.

## 5. Versioned production-simulation evidence

### 5.1 Qualification boundary

Existing v0.72 evidence is explicitly fixture-only. v0.76 introduces a new
schema and loader for public-market deterministic simulation:

```text
src/crypto_quant/schemas/
  challenger-replacement-public-simulation-result-v1.schema.json
```

The qualification string is exactly:

```text
PUBLIC_MARKET_DETERMINISTIC_SIMULATION_NO_ACCOUNT_NO_BROKER_NO_REAL_ORDER
```

The document binds:

- exact v0.69, v0.71, v0.74 and v0.75 plan/contract identities;
- the v0.76 release-candidate build identity;
- opportunity ID, sequence, scheduled time and parent event hash;
- exact validated PublicMarketCaptureV2 hash, its nested v0.67 capture hash and
  normalized source rows, quotes, mark, funding and rule metadata;
- previous canonical accounting snapshot hash;
- deterministic decision, risk, order intent, simulated fill, fee, funding,
  position and resulting accounting snapshot;
- lifecycle invariants and reconciliation status;
- public request count inherited from PublicMarketCaptureV2;
- account, credential, Broker, venue-order and fund counts fixed to zero; and
- canonical self-hash and stable result ID.

The simulated lifecycle uses distinct event names such as
`SIMULATED_ORDER_ACCEPTED` and `SIMULATED_FILL_APPLIED`. Fixture event names
ending in `_FIXTURE` and future v0.77 venue event names are forbidden. A
simulated fill is an economic model output, never a claim that Binance accepted
or filled an order.

### 5.2 PublicMarketCaptureV2

The v0.67 capture proves trusted time and the exact 21 closed Spot ETHUSDT 4h
rows, but it does not contain the bid/ask, perpetual mark, funding or product
rules required by v0.71 accounting. It therefore remains an immutable
sub-capture rather than being misrepresented as a complete simulation input.

`PublicMarketCaptureV2` embeds the exact validated v0.67 canonical bytes and
adds the following six fixed, unauthenticated request identities in this exact
order:

```text
https://data-api.binance.vision/api/v3/exchangeInfo?symbol=ETHUSDT
https://data-api.binance.vision/api/v3/ticker/bookTicker?symbol=ETHUSDT
https://fapi.binance.com/fapi/v1/exchangeInfo
https://fapi.binance.com/fapi/v1/ticker/bookTicker?symbol=ETHUSDT
https://fapi.binance.com/fapi/v1/premiumIndex?symbol=ETHUSDT
https://fapi.binance.com/fapi/v1/fundingRate?endTime={scheduled_ms}&limit=16&startTime={scheduled_ms_minus_14399999}&symbol=ETHUSDT
```

No URL, host, path, symbol, query order or endpoint is caller supplied. Each
request has one initial attempt and at most two retries under the existing
bounded transport rules. Including the three clock probes and the Kline
request, one capture therefore records between 10 and 24 public requests. The
request ledger preserves exact request identity, attempt order, status,
selected headers, response size, response SHA-256 and exact response bytes.
Release tests use fixtures only and issue zero network requests.

The USDⓈ-M exchange-info response is bounded to 4 MiB because Binance exposes
no symbol parameter on that endpoint. Every other added response is bounded to
1 MiB. An over-size body fails before JSON interpretation; no truncation is
accepted as evidence.

The strict loader requires:

- exactly one trading `ETHUSDT` Spot symbol and exactly one trading perpetual
  `ETHUSDT` USDⓈ-M symbol;
- unambiguous price-tick, market-quantity and minimum-notional rules for both
  products under the exact selection rules below;
- positive Spot and perpetual bid/ask with `bid <= ask`;
- one positive perpetual mark whose exchange timestamp lies inside the trusted
  capture window;
- a chronologically ordered Funding response containing every regular record
  in the half-open four-hour interval `(scheduled_for - 4h, scheduled_for]`,
  with no duplicate `fundingTime` and with each record's associated positive
  mark price; and
- unchanged account, credential, Broker, venue-order and fund authority fixed
  to zero/false.

The query uses `startTime = scheduled_ms - 14399999`, `endTime = scheduled_ms`
and `limit = 16`, so the preceding decision boundary is excluded and the
current boundary is included. This captures multiple funding cashflows if
Binance temporarily uses an interval shorter than four hours and prevents the
same record from being charged twice. An empty result means the authoritative
public history returned no funding cashflow in that exact interval; the model
does not manufacture a zero-rate record. More than 16 records, a record outside
the interval, duplicate time, nonascending order, a special or unknown rate
type, missing associated mark, revised fields, an ambiguous filter or any
missing required response fails the opportunity closed. Raw responses remain
evidence; normalized fields are recomputed during every replay.

Rule normalization is deterministic and includes only values used by the
simulation. Price tick is `PRICE_FILTER.tickSize`. Market quantity uses a
positive `MARKET_LOT_SIZE` tuple, or falls back to a positive `LOT_SIZE` tuple
only when the market-specific filter is absent or explicitly disabled. Spot
minimum notional is the maximum of every applicable `NOTIONAL.minNotional`
with `applyMinToMarket=true` and `MIN_NOTIONAL.minNotional` with
`applyToMarket=true`; USDⓈ-M minimum notional is `MIN_NOTIONAL.notional`.
Missing, duplicate-with-conflicting-value, nonpositive or structurally unknown
applicable rules fail closed. Unused display precision, time-in-force and
non-market-order fields are not promoted into the accounting input.

The public input deliberately has no `last` field. The v0.71 fixture loader
validated `last`, but the accounting kernel never consumes it. v0.76 neither
adds a seventh endpoint nor invents a midpoint merely to preserve an unused
fixture shape.

### 5.3 Public simulation contract and fill rules

v0.76 creates a distinct public-simulation contract that binds the exact v0.71
contract ID, hash and file SHA as its accounting predecessor. It copies no
caller-selected economic parameters. Its fixed public labels include:

```text
mode = PUBLIC_MARKET_DETERMINISTIC_BINANCE_SIMULATION
fill_model = DETERMINISTIC_IMMEDIATE_FULL_MARKET_MODEL
funding_source = EXACT_PUBLIC_FUNDING_RECORDS_IN_OPPORTUNITY_INTERVAL
protective_stop_status = CONFIRMED_SIMULATED
```

The released v0.71 contract remains byte-for-byte fixture-only. The existing
v0.71/v0.72 public APIs must retain their exact fixture outputs. If the
implementation extracts an evidence-neutral private Decimal kernel, the only
profiles are fixed internal fixture and public-simulation constants; callers
cannot provide a profile, label, fee, slippage or status override. A new public
snapshot schema uses `CONFIRMED_SIMULATED`; `CONFIRMED_FIXTURE` is rejected by
the public loader and remains accepted only by the historical fixture loader.

Price tick, market quantity step, minimum/maximum quantity and minimum-notional
come from strict exchange-info evidence. Product mutual exclusion and direction
come from the frozen v0.69/v0.75 policies. The linear USDⓈ-M contract
multiplier is the fixed Decimal `1` model assumption inherited from the v0.71
ETH-quantity fixtures and explicitly rebound by the public contract; it is not
claimed as an exchange-info field. Fee, adverse slippage and conservative-mark
rules come from the exact v0.71/v0.74 economic model and are labelled model
assumptions, not account or venue fee observations. The resulting narrow
simulation-rules record binds both its public response hashes and frozen-model
fields so neither can be silently substituted.

The public Decimal profile applies zero or more Funding records before the
current decision, in ascending `fundingTime` order. Each cashflow uses that
record's exact rate and associated mark price with the frozen v0.71 signed
quantity and multiplier formula. The current position mark still comes only
from `premiumIndex.markPrice`. Historical fixture APIs retain their original
single-boundary Funding shape and exact output bytes.

The adapter accepts only the strict PublicMarketCaptureV2, v0.69 plan, exact
v0.71 predecessor contract, v0.76 public contract and replayed previous public
accounting state. Public APIs accept no URL, symbol, price, fee, funding,
slippage, position, decision, timestamp or result override. If required input
is unavailable, invalid or not derivable from canonical public evidence, the
opportunity becomes `MISSED` or the stream fails according to the v0.69/v0.75
classification; the runtime never invents a fill or substitutes zero cost.

### 5.4 Runtime recovery

Every invocation first replays the retained canonical event root. It then does
exactly one of:

- return the already terminal opportunity without network or write activity;
- resume the unique prepared durable boundary;
- derive the one next due opportunity and attempt public acquisition; or
- append the one canonical `MISSED` or failure boundary permitted by policy.

The runtime never catches up by issuing historical market requests. Multiple
past due opportunities are recorded as `MISSED` in canonical schedule order,
without decision or fill backfill, before the current eligible opportunity is
considered. Optimistic event tokens prevent two workers from appending the same
stage. A loser replays and returns or fails with the fixed conflict code; the
state layer does not silently rebase a stale result.

## 6. Four-hour service and v3 deployment trust chain

### 6.1 Schedule

The retained schedule is six natural invocations per day at local hours
`00, 04, 08, 12, 16, 20`, minute `02`. Asia/Shanghai is an integer multiple of
the four-hour UTC grid, so these remain aligned with the closed ETHUSDT 4h
boundaries. `RunAtLoad=false` and `KeepAlive=false` remain fixed. No catch-up
loop, manual slot argument, bootstrap retry or high-frequency polling is added.

### 6.2 New candidate identity

The v0.76 deployment candidate binds:

- v0.75 predecessor release identity;
- exact v0.69, v0.71, v0.74 and v0.75 artifact identities;
- the reviewed inventory of the v0.67 public adapter, v0.70 event protocol,
  v0.71 accounting core, v0.76 public capture/contract and new v0.76
  composition modules;
- fixed service label and owner-only paths already established by v0.68;
- a v0.76 candidate package version and manifest version without embedding a
  future merge commit or tag object; and
- all activation and money authority set to false.

The v0.76 tag/main/CI identity is bound later by a future, separately approved
install ceremony. This avoids a manifest self-reference and does not authorize
that ceremony.

### 6.3 Start receipts

The old v0.68 receipt schema with `required_slot_count=540` remains historical.
v0.76 introduces a v3 start-receipt schema. A future valid receipt must bind the
same first natural production-qualified `OBSERVED` opportunity into two
directional starts:

1. operational qualification start; and
2. v0.74 economic research start.

The shared fields are:

```text
opportunity_id
event_hash
scheduled_for
observed_at
v069_plan_id
v069_plan_hash
v074_plan_id
v074_plan_hash
v075_plan_id
v075_plan_hash
deployment_identity
event_root_identity
```

The operational start uses the observed time for its continuous-segment clock.
The economic half-open window uses scheduled time. Install, release, preflight,
fixture or manually supplied time cannot start either clock. v0.76 includes
builders and strict loaders but creates no production receipt.

## 7. Operational 72-hour qualification

### 7.1 Pure projection

`challenger_replacement_operational_qualification.py` is a pure deterministic
module. It consumes only strict typed facts derived from:

- the exact v0.75 plan;
- the v3 start receipt;
- canonical DecisionOpportunity replay;
- strict simulation-result evidence; and
- the exact offline fault-matrix receipt for the same released build.

It imports no filesystem, network, subprocess, launchd, credential, account,
Broker, order-submission or UI code. Production policy is not caller supplied.

### 7.2 State machine

The public result states are exactly:

```text
NOT_STARTED
ACTIVE
INTERRUPTED_RECOVERABLE
BLOCK_FAILED
QUALIFIED
```

Qualification requires one final uninterrupted healthy segment of at least
`259200` real seconds. Disconnected segments never sum. The segment begins at a
natural production-qualified `OBSERVED` opportunity. Every due four-hour
opportunity through the observation boundary must have exactly one terminal
`OBSERVED` or `MISSED` outcome.

A flat `MISSED` or safely reconciled short disconnection closes the current
segment as `INTERRUPTED_RECOVERABLE`. A later natural `OBSERVED` may begin a
new segment, while all previous facts remain visible. Fixture time, untrusted
clock time and incomplete evidence contribute zero seconds.

An exposed miss or inability to manage an existing position rejects new risk,
requires safe flattening and returns `BLOCK_FAILED`. Restarting the process
cannot turn the same block into qualified. A future block requires immutable
incident acceptance and a separately approved unlock; v0.76 does not provide
that approval.

### 7.3 Fault-matrix receipt

The qualification evaluator accepts only a strict, exact-build offline receipt
covering every frozen case:

- process termination before and after each durable boundary;
- fresh-process replay and idempotent retry;
- network loss before request, after request and after response receipt;
- clock offset, spread, backward wall clock and monotonic inconsistency;
- duplicate invocation and stale optimistic token;
- malformed, partial, revised or unavailable market input;
- partial simulated fill, late simulated fill and cancel race;
- unresolved UNKNOWN classification;
- protective-stop loss/replace model failure;
- engine/venue-model/ledger disagreement;
- fee and funding replay;
- daily-loss and drawdown lock;
- disk write, file fsync and directory fsync failure; and
- unavailable or invalid read-only projection source.

All cases must pass against the exact v0.76 build. One missing, skipped,
unexpected or failed case prevents `QUALIFIED`. The receipt does not contribute
wall-clock seconds and cannot qualify a production service by itself.

## 8. Final v0.74 economic evaluator

### 8.1 Inputs and tail boundary

`challenger_replacement_economic_evaluation.py` consumes only:

- exact v0.74 plan bytes through its released strict loader;
- the strict v3 economic start binding;
- canonical DecisionOpportunity replay for the exact half-open 90-day window;
- strict v0.76 public-simulation evidence for observed opportunities;
- strict lifecycle/accounting projections derived from released v0.71
  semantics; and
- the canonical pre-action tail mark at
  `start_scheduled_for + 7776000 seconds`.

`EconomicOpportunityFact.result_or_null` is an exact replay envelope, not a
bare result summary. Its keys are exactly `source`, `previous_projection`,
`result`, `sequence` and `parent_event_hash`. The evaluator derives the v0.69
plan and public contract from frozen builders, then invokes the released public
simulation result loader on canonical bytes before reading accounting. A tail
mark envelope contains exactly `source`, `previous_projection` and
`marked_equity`; the source is strictly replayed and `marked_equity` is rebuilt
from the frozen conservative mark function. This is required because a result
summary contains source hashes but not the price evidence needed to reconstruct
friction or an open-position tail mark. No caller may provide a precomputed
return, cost, PnL or mark without these replay inputs.

No public evaluator accepts a path, start, price, fee, funding, PnL, daily
return, bootstrap seed, threshold, status, result ID or filename from the
caller. A thin fixed-path production CLI may be released for future use, but it
must refuse before the tail and must not be invoked during v0.76 release.

Before the tail the observer may expose only due/terminal/observed/missed
counts, evidence health, elapsed days and next required opportunity. It must
not calculate, read, log or return PnL, return, drawdown, confidence interval,
power, rank, block result or preliminary PASS.

### 8.2 Economic series

The evaluator replays Decimal accounting without binary float and constructs:

```text
91 pre-action boundary equities
90 daily fixed-capital net returns
6 non-overlapping 15-day block returns
continuous high-water maximum drawdown
base-friction and frozen stress-friction replays
optimistic and pessimistic flat-miss series
```

Fees, adverse slippage and signed funding cashflow are included once and only
once. Missing costs cannot be replaced with zero. A nonpositive equity is a
confirmed `DID_NOT_PASS` boundary. An untrusted or missing tail mark yields
`INCONCLUSIVE_INSUFFICIENT_EVIDENCE`.

Each distinct flat `MISSED` is retained. The optimistic series assigns zero
economic change; the pessimistic series subtracts exactly `1.25 USDT`. The
same miss cannot be charged twice. PASS requires both series to pass every
applicable gate. Favorable-bound selection is forbidden.

### 8.3 Statistical algorithm

The primary endpoint is the v0.74 one-sided 95% lower confidence bound on mean
daily net return. The implementation is fixed to:

```text
method = OVERLAPPING_NON_CIRCULAR_MOVING_BLOCK_BOOTSTRAP
block_length_days = 7
sample_length = 90
resample_count = 10000
seed = 2026082574
draw_start = SHA256_REJECTION_SAMPLED_MBB_V1
quantile = CONSERVATIVE_NEAREST_RANK_0_05
language_prng_allowed = false
```

The evaluator must implement the exact SHA-256 rejection-sampling byte string
specified by v0.74 and test it with committed known-answer vectors. It reports
the preregistered achieved-power calculation, but power is not an alternate
PASS threshold.

### 8.4 Terminal result

The result schema permits exactly:

```text
RESEARCH_CONTINUATION_GATE_PASS
RESEARCH_CONTINUATION_GATE_DID_NOT_PASS
INCONCLUSIVE_INSUFFICIENT_EVIDENCE
```

Confirmed safety/evidence failures and failed economic gates map exactly as
v0.74 specifies. Sample or reconstructability shortfall is inconclusive; it is
not silently extended beyond the frozen window. The first valid final artifact
is immutable. No rerun, alternate seed, alternate start, threshold override,
sample deletion or favorable-result selection is allowed.

The result contains enough exact inputs, gate values, hashes and derivation
identities for a fresh-process strict loader to rebuild and byte-compare every
derived field. The loader validates schema, canonical encoding, result hash,
stable ID, plan/start/build bindings, gate recomputation and literal committed
schema identity. It does not infer profitability from status text alone.

## 9. Observer and read-only operations console

v0.76 adds `operations-projection-v3`; it does not mutate v1 or v2 semantics.
The projection is produced from strict typed loader outputs and includes only:

- service and evidence health;
- operational qualification block/segment status and eligible seconds;
- due, observed and missed opportunity counts;
- next required opportunity;
- fault-matrix completion status;
- economic elapsed days and tail-blind status;
- current simulated product, reconciliation and risk-lock states;
- exact provenance; and
- explicit false activation/account/order authority.

Before the economic tail it excludes all economic amounts and statistics. The
existing operations dashboard receives strict v1/v2/v3 dispatch, renders safe
text and remains bound to `127.0.0.1`. It has no POST/PUT/PATCH/DELETE route,
write API, start button, retry button, order button, credential input, external
asset or remote dependency. UI health never authorizes trading.

## 10. Error handling and failure closure

Each new domain defines a fixed public error type with a finite reason-code
set. Raw exception text, source bytes, URLs containing unexpected query data,
credentials and OS paths outside allowlisted roots are never included in
public artifacts or logs.

Rules are:

- strict JSON rejects duplicate keys, binary float, NaN, unknown keys,
  noncanonical bytes and over-size input before semantic use;
- schema validation is followed by deterministic semantic reconstruction;
- every hash, stable ID, parent, build, plan, start and event-root binding is
  recomputed;
- symlink, hardlink, wrong owner, wrong mode, nonregular object, attachment
  change or descriptor identity change fails closed;
- replay never repairs or chmods an untrusted existing object;
- close failures cannot overwrite the primary failure;
- no caller flag weakens validation or selects a favorable status;
- a failed observer cannot append a failure event; and
- any ambiguous order/position-like simulation state rejects new simulated
  risk and remains visible.

## 11. Files and interfaces

The implementation plan may refine filenames without changing boundaries. The
expected new production modules are:

```text
src/crypto_quant/challenger_replacement_public_simulation.py
src/crypto_quant/challenger_replacement_public_market_capture.py
src/crypto_quant/challenger_replacement_public_simulation_contract.py
src/crypto_quant/challenger_replacement_v3_runtime.py
src/crypto_quant/challenger_replacement_v3_deployment.py
src/crypto_quant/challenger_replacement_v3_start.py
src/crypto_quant/challenger_replacement_operational_qualification.py
src/crypto_quant/challenger_replacement_fault_matrix.py
src/crypto_quant/challenger_replacement_economic_evaluation.py
src/crypto_quant/challenger_replacement_economic_evaluation_cli.py
src/crypto_quant/challenger_replacement_v3_observer.py
src/crypto_quant/operations_projection_v3.py
```

Expected new schemas are:

```text
challenger-replacement-public-simulation-result-v1.schema.json
challenger-replacement-public-market-capture-v2.schema.json
challenger-replacement-public-simulation-contract-v1.schema.json
challenger-replacement-public-simulation-snapshot-v1.schema.json
challenger-replacement-v3-deployment-v1.schema.json
challenger-replacement-v3-start-receipt-v1.schema.json
challenger-replacement-operational-qualification-v1.schema.json
challenger-replacement-fault-matrix-receipt-v1.schema.json
challenger-replacement-economic-evaluation-v1.schema.json
operations-projection-v3.schema.json
```

The composition layer should expose narrow domain interfaces, not a generic
plugin API. Builders accept strict typed outputs rather than arbitrary
mappings where practical. Production CLIs accept no business parameters; only
`--help` is permitted unless an existing fixed CLI convention requires no
arguments at all.

## 12. TDD and verification

Implementation follows one atomic RED, minimal GREEN and refactor cycle per
behavior. Required test groups include:

1. schema and strict loader mutation tests;
2. fixed-request public capture, retry/count, exact Funding-interval and
   no-network release tests;
3. fixture/public contract isolation plus public-simulation golden and boundary
   tests;
4. fresh-process event/recovery/concurrency tests;
5. v3 deployment/start identity tests;
6. 72-hour segment and interruption state-machine tests;
7. complete fault-matrix known-answer tests;
8. 90-day population/Decimal/bootstrap/gate known-answer tests;
9. pre-tail economic non-disclosure tests;
10. v1/v2/v3 console compatibility and read-only tests;
11. static forbidden-capability and secret-absence tests; and
12. committed-artifact/build-manifest/release regressions.

The tests must include adversarial mutation of every policy or identity leaf,
not only happy paths. Multiprocessing or new-interpreter tests are required for
true publication races and crash/replay claims. Mock time never satisfies a
production 72-hour or 90-day result.

One independent complete review is required. Critical and Important findings
must be zero after targeted TDD fixes and targeted rereview. The final unchanged
candidate receives:

- focused and adjacent suites;
- one local full suite;
- `compileall`;
- `make validate`;
- `git diff --check` and clean status;
- PR Python 3.9, Python 3.12 and macOS arm64 CI;
- merged-main CI on the exact merge commit; and
- an annotated `v0.76.0` tag peeled exactly to `origin/main`.

The same unchanged code state is not subjected to duplicate local full suites
or duplicate whole-branch review.

## 13. YAGNI and size gate

The new production Python net addition across v0.76-specific modules is capped
at 4,200 physical lines. This is the revised hard cap approved before Task 8:
the first six completed modules measure 2,324 physical lines, so the original
2,600-line estimate cannot contain the still-mandatory fault matrix, 72-hour
qualifier, 90-day evaluator and observer without either deleting approved
safety scope or mechanically compressing auditable code. Neither is allowed.

The revised evidence-based budget is:

```text
completed capture/simulation/runtime/deployment/start   2,324 actual
72-hour qualification + fault receipt                    575 actual
90-day evaluator + strict result loader                   800 maximum
observer + operations projection integration              350 maximum
deletion/refactor and measurement contingency              151 maximum
hard cap                                                  4,200
```

The cap is a maximum, not a target. Each remaining task first reuses or deletes
existing code and records its actual increment. Crossing a task allowance
requires deletion or a documented redistribution that leaves the 4,200-line
hard cap unchanged; crossing the hard cap requires a new design amendment.

Cross-platform atomic publication, strict JSON, canonical Decimal, event replay
and existing console mechanics must be reused. If the candidate reaches the
cap, implementation pauses for deletion or a design amendment; it does not
copy generic infrastructure and promise later cleanup.

No scheduler, deployment framework, exchange abstraction, broker framework,
order platform, storage platform or second Web application may be introduced.

## 14. Release artifacts and status

v0.76 publishes code, schemas, committed deterministic fixtures, an offline
fault-matrix conformance receipt, a candidate deployment contract, ADR,
implementation status and build manifest. It does not publish a production
start receipt, 72-hour result or 90-day result.

The implementation status must state:

```text
PUBLIC_SIMULATION_AND_RESEARCH_CODE_RELEASED_NOT_ACTIVATED
CODE_COMPLETE_NOT_ACTIVATED_NOT_YET_REACHED
production_activation=false
runtime_install_authorized=false
replacement_start_authorized=false
credentials_allowed=false
account_requests_allowed=false
real_orders_allowed=false
fund_movement_allowed=false
production_state_writes=0
economic_outcome_reads=0
no 72-hour timer started
no 90-day timer started
no profitability or AI-advantage conclusion
```

Release documentation records exact plan/result-schema IDs, artifact hashes,
manifest identities, test counts, review findings, PR/main CI and tag identity.
It must distinguish offline fault-matrix success from real wall-clock service
qualification.

## 15. Completion criteria

v0.76 is complete only when all of the following are proven:

- v0.69, v0.74 and v0.75 exact artifacts replay unchanged;
- PublicMarketCaptureV2 binds the exact v0.67 sub-capture and all required
  fixed public rule/quote/mark/Funding responses without caller overrides;
- public simulation consumes only the strict v0.76 public input/contract,
  preserves historical v0.71/v0.72 fixture bytes and emits no fixture or venue
  claim;
- one canonical event log remains the sole fact source;
- restart, crash and concurrency semantics are proven in fresh processes;
- the v3 deployment/start code binds exact immutable identities but is not
  executed;
- the 72-hour evaluator implements uninterrupted-segment semantics and the
  complete exact-build fault-matrix gate;
- the 90-day evaluator implements every v0.74 population, missingness,
  Decimal, bootstrap, sample, economic and first-result rule;
- pre-tail observers and UI cannot expose economic results;
- v1/v2 console inputs retain exact behavior and v3 remains loopback-only and
  read-only;
- no installation, activation, credential, account, Broker, real order, fund
  movement or production state write occurred;
- review Critical/Important findings are zero;
- local and remote verification gates pass; and
- annotated `v0.76.0` peels exactly to merged `origin/main`.

After v0.76, v0.77 remains responsible for the fixture/mock-only Binance
private boundary, ceremony controller, E0/E1/E2 controller, alerts, runbooks,
templates and final `CODE_COMPLETE_NOT_ACTIVATED` dossier. v0.76 neither pulls
that scope forward nor grants any future activation.
