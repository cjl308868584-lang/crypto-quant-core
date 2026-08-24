# v0.73 Replacement v3 Readiness Evaluator, Observer and Operations Integration Design

## 1. Decision and release authority

v0.73 integrates the released replacement-v3 DecisionOpportunity and Binance
lifecycle evidence into a pure operational-qualification evaluator, a
tail-blind economic-evidence observer, and the existing loopback-only read-only
operations console.

The release base is public repository `cjl308868584-lang/crypto-quant-core`,
annotated `v0.72.0`, peeled commit
`44d294a8fbc55a0fb4f9fe0537bb868824815d80`. The following released bytes stay
unchanged:

- v0.69 plan, machine evidence, accountable owner attestation and supersession
  record;
- v0.70 DecisionOpportunity event protocol and committed fixtures;
- v0.71 deterministic accounting contract;
- v0.72 lifecycle result-evidence-v2 schemas and committed complete-cycle
  fixtures;
- v0.60 operations-projection-v1 and v0.61 console behavior for v1 inputs.

The exact v0.73 release claim is:

```text
READINESS_EVALUATOR_AND_READ_ONLY_INTEGRATION_VERIFIED_NOT_STARTED
```

It is a code, schema, fixture, test and documentation release. It does not
install or start a service, create a production start receipt, write a
production event root, contact Binance, read credentials, submit orders, move
funds, begin either wall-clock timer, grant Canary eligibility or make a
profitability/AI-advantage claim.

The authority boundary remains:

```text
network_requests = 0
account_requests = 0
broker_requests = 0
orders_submitted_to_venue = 0
credentials_used = false
production_state_writes = 0
production_activation = false
runtime_install_authorized = false
replacement_start_authorized = false
real_orders_allowed = false
operational_timer_started = false
economic_timer_started = false
```

## 2. Scope correction and governance gap

The v0.69 governance design originally grouped event runtime, evaluators,
observer and UI under v0.70. Subsequent reviewed splits released event runtime
as v0.70, accounting as v0.71 and lifecycle evidence as v0.72. The v0.72 design
therefore explicitly makes v0.73 the earliest evaluator/observer/UI integration
version. This document records the actual split without rewriting prior tags,
artifacts or claims.

The operational policy is sufficiently exact to implement:

- at least seven complete real calendar days from a future strict operational
  start receipt bound to the first verified natural OBSERVED opportunity;
- terminal coverage of every due opportunity and OBSERVED coverage at least
  `0.95`;
- at least three complete FLAT-to-product-to-FLAT strategy cycles;
- at least one complete Spot-long roundtrip and one complete perpetual-short
  roundtrip;
- no unresolved opportunity, order, fill, position, stop, reconciliation,
  evidence or S0/S1 safety failure;
- automatic extension without deleting MISSED history or resetting start.

The economic policy is not yet sufficiently exact for a final profitability
evaluator. The released v0.69 plan fixes 90 calendar days, terminal coverage
`1`, OBSERVED coverage `0.95`, no interim PASS and the three terminal status
names, but it does not contain the numerical return, drawdown, cost and
confidence-interval thresholds referenced by the narrative design. v0.73 must
not invent those values after fixture results exist.

Consequently v0.73 implements only a tail-blind economic progress observer. A
later plan-only preregistration must freeze the missing economic metrics and
thresholds before any production economic start receipt or production
opportunity. No v0.73 API can emit `RESEARCH_CONTINUATION_GATE_PASS`,
`RESEARCH_CONTINUATION_GATE_DID_NOT_PASS` or a final economic artifact.

## 3. Alternatives

### 3.1 Selected: separate pure evaluator, tail-blind observer and projection-v2

Build a narrow replacement-v3 readiness module over strict event projection
and lifecycle evidence. It returns typed in-memory observations. A separate
operations adapter creates a version-2 projection consumed by the existing
console. Existing v1 projection and console input remain supported through
strict schema dispatch.

This separates three questions:

1. is the append-only evidence internally valid;
2. what operational gate status follows from already verified facts;
3. which allowlisted facts may be displayed.

It reuses the v0.61 HTTP/static presentation boundary and does not create a
second dashboard or general monitoring framework.

### 3.2 Rejected: map v3 facts into operations-projection-v1

The v1 fields `verified_slot_count`, `completed_episode_count` and
`WITHHELD_PRE_TAIL` describe the retired cohort model. Mapping
DecisionOpportunity coverage and lifecycle cycles into them would be
semantically false even if the JSON passed its old schema.

### 3.3 Rejected: implement a final economic evaluator now

Choosing profitability thresholds now would be post-hoc research governance.
Reusing the retired cohort evaluator would also import a different hypothesis,
sample model, cost model and tail contract. Both paths are fail-open and are
forbidden.

### 3.4 Rejected: build a new Web application

The v0.61 console already provides loopback binding, fixed read-only routes,
strict response handling and safe DOM rendering. Rebuilding these mechanics
would add generic infrastructure without improving evidence trust.

## 4. Component boundaries

### 4.1 `challenger_replacement_readiness.py`

This new pure module owns:

- typed operational and tail-blind observation inputs;
- due/terminal/OBSERVED/MISSED coverage calculations;
- strategy-cycle and product-roundtrip reduction from ordered, strict v2
  lifecycle results;
- unresolved-safety classification;
- operational status selection;
- economic tail-blind progress selection.

It imports no filesystem, network, subprocess, LaunchAgent, credential,
Broker, order-submission, wall-clock or dashboard code. It accepts no arbitrary
path, current time, PnL, status, result, callback or policy mapping.

Its calculation consumes only typed values created from strict v0.69 plan,
v0.70 event projection and v0.72 lifecycle evidence loaders. Tests may create
explicit fixture-qualified typed observations; those objects never constitute
a production receipt or final artifact.

### 4.2 `challenger_replacement_readiness_observer.py`

This module is a read-only composition boundary. Its public builder consumes:

- exact v0.69 plan bytes;
- a reviewed replay façade around the retained replacement event root;
- a typed readiness-boundary object containing the optional strict start
  binding and canonical observation time;
- the event-evidence identity already bound into the v0.72 fixture root;
- a separate real release-provenance identity for displayed software.

v0.73 includes no public constructor for arbitrary boundary fields and no
production start-binding loader. The only accepted boundary qualification is a
committed fixture identity created by a private test helper in owner-only test
roots. Without a future production-qualified receipt adapter, the operational
and economic phases are exactly `NOT_STARTED` and no authoritative PASS is
possible. A later deployment/start version must add the strict receipt loader
and boundary adapter without changing the pure evaluator.

The two identities are directional and noninterchangeable. The event identity
is the frozen `0.72.0-fixture`/package `0.72.0`/manifest `1.66.0` identity
accepted by the released event projector. Release provenance is the actual
annotated release/main identity, including v0.72 peeled commit
`44d294a8fbc55a0fb4f9fe0537bb868824815d80` and the future v0.73 release
identity. They are never compared for equality or used as substitutes. A
future production event identity requires explicit deployment/start-version
dispatch.

The observer calls the façade's `replay()` once and has no append/publish
import or callable symbol. It never repairs, discovers paths or reads exports.
Failures retain a typed distinction without including exception text or source
bytes: a readable fact that proves a hash, parent, attachment, durability or
identity contract violation is
`CONFIRMED_EVIDENCE_DURABILITY_OR_IDENTITY_FAILURE`; a missing/unreadable source
or a qualification that cannot be established is
`EVIDENCE_SOURCE_UNAVAILABLE_OR_QUALIFICATION_UNKNOWN`.

### 4.3 `operations_projection_v2.py`

A new module builds and strictly loads `operations-projection-v2`. It does not
modify the v1 schema or v1 loader. Its sources are typed strict-loader outputs:

- released build identity;
- immutable predecessor/cohort failure summary;
- replacement-v3 readiness observation;
- existing System Paper observation.

The v2 replacement section contains only:

```text
phase
service_health
evidence_health
due_opportunity_count
terminal_opportunity_count
observed_opportunity_count
missed_opportunity_count
observed_coverage_numerator
observed_coverage_denominator
meets_minimum_observed_coverage
terminal_coverage_complete
current_consecutive_missed
maximum_consecutive_missed
last_missed_reason_or_null
next_required_opportunity
operational_elapsed_days
operational_minimum_days
operational_strategy_cycle_count
spot_roundtrip_count
perpetual_roundtrip_count
operational_gate_status
economic_elapsed_days
economic_minimum_days
economic_tail_status
current_product
gross_exposure
open_order_count
unknown_order_count
reconciliation_status
protective_stop_status
risk_state
daily_loss_boundary_state
drawdown_boundary_state
incident_count
new_risk_advisory
provenance
```

Counts are safe nonnegative integers. Coverage is represented only by exact
integer numerator/denominator and threshold boolean; an arbitrary rational is
never mislabeled as a finite exact Decimal. The UI renders `numerator /
denominator` and the boolean and never feeds a rounded presentation percentage
back into policy. Times are canonical UTC milliseconds. The projection
self-hash covers every field except its own value. Schema mirrors under
`config/` and package resources must be byte-identical.

`daily_loss_boundary_state` and `drawdown_boundary_state` expose only
`NOT_AVAILABLE`, `NORMAL` or `BREACHED`; they never expose an economic amount
or percentage. This preserves the pre-tail economics embargo while still
showing whether the frozen safety boundary has locked risk.

`new_risk_advisory` is false unless the strict evidence is healthy, the
lifecycle is reconciled, risk is normal, no unknown/open conflict exists and
the operational status permits continued simulation. It is presentation-only:
it cannot authorize install, start, credentials, Canary or orders.

### 4.4 Existing operations console

`operations_alerts.py` and `operations_dashboard.py` gain strict v1/v2 input
dispatch. v1 bytes keep exact existing behavior. v2 bytes are loaded only by
the new v2 loader and converted field-by-field to a canonical status response.

The HTTP contract remains unchanged:

```text
GET /
GET /app.js
GET /styles.css
GET /api/v1/status
```

The `/api/v1/status` route name is a transport route, not a projection-schema
claim. No new route, write method, WebSocket, auto-refresh loop, external
resource or action button is added. The server still binds only literal
`127.0.0.1` and receives projection bytes from an injected provider.

Static UI code may render new allowlisted labels but must use `textContent` and
must not render raw JSON, paths, credentials, PnL, returns, win rate,
confidence intervals or early economic conclusions.

## 5. Operational evaluator semantics

### 5.1 Boundary and duration

The start boundary is the first verified natural OBSERVED opportunity selected
by a future immutable operational start receipt. Fixture tests use an explicit
fixture qualification. Neither install time, tag time, preflight time nor a
caller-selected date is eligible.

Elapsed complete days are:

```text
floor((observed_at - start_observed_at) / 86400 seconds)
```

Negative time, noncanonical time, a start not bound to the first eligible
OBSERVED event, or an event before the start produces a fixed invalid-input
failure. Seven elapsed days alone never produces PASS.

### 5.2 Coverage

Every scheduled opportunity from the start schedule through the last due
capture-close boundary must have exactly one terminal outcome. Define:

```text
terminal_coverage = terminal_count / due_count
observed_coverage = observed_count / due_count
```

Both are exact rational comparisons using integer cross multiplication; no
float is permitted. PASS requires terminal coverage exactly `1` and
`observed_count * 100 >= due_count * 95`. MISSED remains permanently visible.

An opportunity currently inside its capture window is not yet due. An expired
opportunity lacking a terminal outcome is unresolved and prevents PASS; the
observer never appends a synthetic MISSED event.

### 5.3 Strategy cycles

A complete strategy cycle begins at verified `FLAT`, enters exactly one of
`SPOT_LONG` or `PERP_SHORT`, and returns to verified `FLAT` through ordered
OBSERVED v2 evidence. HOLD opportunities within the position do not create a
new cycle. A flat MISSED affects coverage only. A MISSED while exposed creates
the released permanent `economic_gap_locked`/stage-failed evidence. The current
frozen stream may flatten conservatively but cannot clear that lock or regain
risk/cycle eligibility through later good opportunities. Only a future explicit
governance supersession could define a new stream. Automatic extension repairs
only coverage; it never clears this safety failure.

PASS requires at least three cycles total, at least one Spot cycle and at
least one perpetual cycle. A failed, unknown, unreconciled or non-flat terminal
result does not count as a completed cycle.

### 5.4 Safety and status order

Safety and evidence qualification precede duration and coverage. Confirmed
operational failures yield:

```text
OPERATIONAL_QUALIFICATION_DID_NOT_PASS
```

This category includes a confirmed unresolved UNKNOWN, duplicate economic
order, unrecorded/conflicting fill, ledger-position mismatch,
missing/unconfirmed protective stop for non-flat exposure, account/margin/
leverage mismatch, exposed MISSED gap lock, stage-failed lock, confirmed
clock/connectivity insufficiency, credential/IP boundary failure, S0/S1
incident, `CONFIRMED_EVIDENCE_DURABILITY_OR_IDENTITY_FAILURE` or another
frozen safety failure.

Evidence that is unavailable, unreadable, ambiguous or not qualified to decide
the policy yields:

```text
INCONCLUSIVE_INSUFFICIENT_EVIDENCE
```

This category includes an unavailable/unreadable source, ambiguous start
binding, malformed boundary whose provenance cannot be established or another
qualification-unknown condition. It is used only when the available evidence
cannot prove that the system actually violated durability or identity. A
readable hash/parent/attachment/identity mismatch is a confirmed failure and
therefore DID_NOT_PASS. Absence of a start is not a terminal result: it remains
the observer state `NOT_STARTED`.

The read-only projection additionally exposes
`FAILED_CLOSED_REQUIRES_INCIDENT_REVIEW`; this is a health state, not an extra
terminal evaluator status. It cannot automatically clear through later good
opportunities. Incident unlock remains a separate user-authorized future
action.

Status precedence is:

1. confirmed frozen safety or evidence durability/identity failure ->
   `OPERATIONAL_QUALIFICATION_DID_NOT_PASS`;
2. unavailable/unreadable/ambiguous/unqualified evidence needed for a
   decision -> `INCONCLUSIVE_INSUFFICIENT_EVIDENCE`;
3. no production-qualified start -> `NOT_STARTED`;
4. fewer than seven complete days -> `COLLECTING_BEFORE_MINIMUM_DURATION`;
5. insufficient coverage/cycles/product roundtrips ->
   `PENDING_AUTOMATIC_EXTENSION`;
6. all exact gates satisfied -> `OPERATIONAL_QUALIFICATION_PASS`.

When both a confirmed failure and a qualification-unknown condition are
present, the confirmed failure wins and the result is DID_NOT_PASS. An
unavailable secondary source cannot hide a readable proven violation.

`COLLECTING_BEFORE_MINIMUM_DURATION` and `NOT_STARTED` are observer states, not
final evaluator artifacts. v0.73 publishes no runtime result artifact.

## 6. Tail-blind economic observation

The released v0.72 strict loader necessarily parses and validates the complete
canonical result, including economic subtrees, to establish schema/hash/
identity integrity. Immediately after that loader, a reviewed sanitizing
boundary selects only opportunity, lifecycle, position, stop, risk-boundary
and structural-count facts into immutable readiness types. Readiness and UI
code must not read, branch on, aggregate, return or log accounting, PnL, fee,
funding, return or drawdown values. Tests count semantic accesses after this
sanitizing boundary; they do not falsely claim the JSON parser never parsed the
bytes.

Before 90 complete days, the economic observer may expose only:

- start bound or not;
- elapsed complete days;
- minimum days (`90`);
- due, terminal, OBSERVED and MISSED counts;
- terminal and OBSERVED coverage health;
- lifecycle completeness and unresolved-safety boolean;
- next time boundary.

It must not semantically read, branch on, aggregate, serialize or display
per-opportunity or cumulative PnL, return, win rate, drawdown, fee, funding,
rank, confidence interval, effect size, power or an early final status after
the strict-loader/sanitizer boundary.

The statuses are exactly:

```text
NOT_STARTED
WITHHELD_PRE_TAIL
TAIL_REACHED_FINAL_EVALUATOR_NOT_PREREGISTERED
FAILED_CLOSED
```

At 90 days, v0.73 still cannot emit a final result because numerical economic
thresholds are not frozen. `TAIL_REACHED_FINAL_EVALUATOR_NOT_PREREGISTERED` is
a governance blocker, not an invitation to inspect results or choose metrics.

## 7. Alert and UI semantics

Deterministic critical alerts are emitted for:

- any failed-closed evidence or observer status;
- terminal opportunity gap;
- unresolved UNKNOWN/order/fill/position/reconciliation;
- missing/unconfirmed stop while non-flat;
- stage-failed risk lock or S0/S1 incident;
- release/tag identity mismatch.

Warnings are emitted for stale evidence, any MISSED opportunity, coverage below
`0.95`, automatic extension, or incomplete product/cycle coverage after seven
days. Information alerts may show collecting or not-started states.

Every CRITICAL alert sets `new_risk_allowed=false`. The UI's advisory flag is
always false in v0.73 fixtures and NOT_STARTED state. No alert acknowledgement,
incident unlock or trading control exists in the console.

## 8. Strict loading and failure closure

All new JSON loaders require:

- byte input with size checked before parse;
- UTF-8, duplicate-key rejection, no floats and safe integers only;
- canonical JSON byte equality;
- exact schema/version/key sets and mirrored-schema byte equality;
- exact v0.69 plan, v0.71 contract and v0.72 build bindings;
- self-hash and parent/evidence hash verification;
- canonical Decimal and UTC-millisecond encodings;
- fixed reason-code errors without source bytes or exception strings.

Projection construction uses typed strict-loader results rather than arbitrary
caller mappings. A stale optimistic event projection, ambiguous start,
duplicate opportunity, lifecycle-v1 fixture evidence, mixed build identity,
unknown schema or unallowlisted enum fails closed.

The observer has no recovery or write behavior. It never chmods, repairs,
renames, appends, creates exports or follows symlinks. Future production path
opening remains the deployment/start version's responsibility.

## 9. Test matrix

### 9.1 Operational policy

- no start; first natural OBSERVED binding; invalid/artificial start;
- day 6/7 boundaries and UTC millisecond exactness;
- terminal coverage gap, `94/100`, exact `19/20` and `20/20`;
- fewer than/at least three cycles;
- Spot-only, perpetual-only and both-product coverage;
- HOLD within cycle, flat MISSED coverage recovery, and exposed MISSED
  permanent gap/stage failure;
- every frozen failure condition and incident precedence;
- automatic extension preserves start and all MISSED history;
- same exact observation returns byte-identical projection.

### 9.2 Economic tail blindness

- no start, day 89, exact day 90 and after-tail states;
- post-sanitizer patch sentinels prove PnL/fee/funding/economic aggregate
  semantic access count is zero;
- source bytes containing economic fields cannot leak into output/errors;
- no final economic status or result artifact API exists;
- missing numerical threshold plan remains a fixed governance blocker.

### 9.3 Projection, alerts and dashboard

- v1 committed fixtures replay byte-identically;
- v2 schema mirrors and self-hash validation;
- every allowlisted field and enum; unknown/extra/missing field rejection;
- deterministic alert order and advisory false under every critical state;
- v2 UI labels use `textContent`; no economics, path or credential leakage;
- fixed loopback host, routes, methods, headers and 503 behavior unchanged;
- no UI action, write endpoint, WebSocket or external resource.

### 9.4 Side-effect and static gates

- socket/HTTP/SDK/keyring/subprocess/launchctl/Broker/order/filesystem-write
  boundaries remain at zero;
- observer has no append/publish import or callable symbol and receives only
  the reviewed replay façade;
- no public path/current-time/PnL/status/result/fault callback;
- no import from Runner, installer, scheduler, credential or live adapter;
- v0.69-v0.72 committed artifacts and fixtures remain byte-identical;
- every production module remains at most 700 physical lines;
- no duplicate general evaluator, dashboard or storage framework.

## 10. Expected file boundary

Create:

```text
src/crypto_quant/challenger_replacement_readiness.py
src/crypto_quant/challenger_replacement_readiness_observer.py
src/crypto_quant/operations_projection_v2.py
config/operations-projection-v2.schema.json
src/crypto_quant/schemas/operations-projection-v2.schema.json
tests/test_challenger_replacement_readiness.py
tests/test_challenger_replacement_readiness_observer.py
tests/test_operations_projection_v2.py
```

Modify only as required for strict v1/v2 display dispatch:

```text
src/crypto_quant/operations_alerts.py
src/crypto_quant/operations_dashboard.py
src/crypto_quant/dashboard/index.html
src/crypto_quant/dashboard/app.js
src/crypto_quant/dashboard/styles.css
tests/test_operations_alerts.py
tests/test_operations_dashboard.py
```

Release metadata, ADR, README and status changes occur only after final code
review. No deployment, install, start-receipt, credential, Binance-network,
Broker, order or production-root file is part of v0.73.

## 11. Version sequence after v0.73

The next independently reviewed milestones are:

1. plan-only preregistration of exact 90-day economic metrics, thresholds,
   costs, missingness sensitivity and final result semantics;
2. deployment/install/start receipt and strict production observer adapter;
3. credential-free public-market System Paper installation/start after explicit
   user approval;
4. at least seven real calendar days of operational evidence with automatic
   extension as required;
5. independent 90-day economic evidence and one frozen final evaluation;
6. only after operational PASS, a separate discussion and exact approval for
   E0 credentials, funding, activation and first real order.

No milestone may compress real time, backfill MISSED opportunities, reset a
bad window, select a better rerun, or treat operational PASS as profitability.

## 12. Verification and release gates

1. design spec committed and reviewed for plan/artifact consistency;
2. detailed TDD implementation plan committed;
3. exact RED before minimal GREEN for each task;
4. focused readiness/observer/projection/alerts/dashboard tests;
5. adjacent v0.69-v0.72 and v0.60-v0.61 regressions;
6. one final local full suite for the final code state, compileall,
   `make validate`, diff-check and forbidden-authority scan;
7. one independent complete review with Critical/Important zero, then only
   targeted review after fixes;
8. public Draft PR with Python 3.9/3.12 and macOS arm64 CI;
9. exact merged-main CI success;
10. annotated `v0.73.0` whose peeled commit equals `origin/main`.

Healthy fixture output proves only the evaluator and observation contracts. It
does not prove a service is running, operational qualification, profitability,
AI advantage, Canary eligibility or live-trading safety.
