# v0.72 Binance Lifecycle Evidence Design

## 1. Decision and authority

v0.72 implements the lifecycle work explicitly deferred by the released v0.71
split.  It adds a fixture-only, product-specific Binance order/fill/stop and
reconciliation state machine, strict opportunity result evidence v2, and
binding to the existing append-only DecisionOpportunity event log.

The release begins at annotated `v0.71.0`, peeled commit
`ba81e48a572e75806bba8b859471f0a7345572dd`.  It preserves the v0.69 plan,
v0.70 event bytes and v0.71 accounting contract artifact byte-for-byte.

The exact release claim is:

```text
FIXTURE_LIFECYCLE_EVIDENCE_VERIFIED_NOT_OPERATIONAL
```

It does not claim a running Paper system, operational qualification, economic
profitability, AI advantage, Canary eligibility or live-trading authority.

All v0.72 execution remains credential-free and in memory or in owner-only
test roots.  The following are fixed at zero or false:

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
```

## 2. Relationship to prior designs

This design implements the v0.72 handoff in
`2026-08-24-v071-accounting-core-version-split-design.md`.  That split
supersedes the old downstream version numbers in Sections 14 and 16 and Tasks
5-8 of `2026-08-24-binance-deterministic-simulation-design.md` and its plan.

The economic formulas, product rules, risk thresholds, stop policy,
reconciliation requirements and failure reasons in the original design remain
normative unless this document narrows an implementation boundary.  No v0.71
observed artifact, test result, manifest, commit or tag is rewritten.

v0.72 contains only:

- deterministic Spot-long and perpetual-short simulated lifecycle semantics;
- result-evidence-v2 strict codec;
- fixture runner and v2 projection dispatch against the retained event-root
  capability;
- committed fixture-only complete-cycle goldens;
- crash, replay, concurrency, fault and zero-authority tests;
- release metadata and verification evidence.

v0.72 excludes:

- public-market capture, account or user-stream access;
- Binance SDK, REST, WebSocket, API key or credential handling;
- a generic Broker, exchange adapter or reusable trading platform;
- scheduler, Runner, LaunchAgent, installer, observer or start receipt;
- operational or economic evaluator and UI wiring;
- testnet or real order submission and any production-root write.

The earliest version for evaluator/observer/UI integration is v0.73.  The
earliest deployment/start version is v0.74 or a later separately designed
release.

## 3. Alternatives

### 3.1 Selected: product-specific thin lifecycle

Add a small Binance fixture lifecycle module whose input is the frozen v0.71
decision/accounting context and whose output is an immutable internal result.
The module knows only Spot long and USDⓈ-M perpetual short.  It owns stable
intent identity, attempt aggregation, simulated stop semantics and exact
three-way reconciliation.  The existing v0.71 simulation remains the sole
accounting and risk implementation.

This keeps project-specific evidence and failure-closed semantics under local
control without growing a second general trading engine.

### 3.2 Rejected: extend the v0.71 simulation monolith

The released simulation module is already 517 physical lines.  Adding order,
stop, recovery and evidence dispatch there would exceed the 700-line module
gate and couple independent responsibilities.

### 3.3 Rejected: embed the generic System Paper Broker or `orders.py`

Existing generic primitives may be consumed only after exact signed-position
semantics are proven by focused tests.  v0.72 must not adapt its contract to fit
a generic engine or add new generic order abstractions.  Deep reuse would
resume the platform-building work that the project explicitly stopped.

## 4. Module boundaries

### 4.1 Frozen v0.71 accounting core

`challenger_replacement_simulation.py` remains responsible for:

- input/plan/contract/build validation;
- genesis and parent snapshot validation;
- decision and risk transition;
- price, quantity, fee, funding, cash, margin, PnL and equity formulas;
- the normal pure transition result.

Its public v0.71 functions remain compatible.  v0.72 may extract a private
typed internal transition only when behavior and committed v0.71 tests remain
byte-identical.  It may not duplicate the accounting formulas elsewhere.

### 4.2 Product-specific lifecycle

Create `challenger_replacement_binance_lifecycle.py`.  It owns:

- deterministic economic-intent, attempt and client identifiers;
- exact order-event aggregation for the two frozen products;
- normal immediate-full-fill simulation;
- protective-stop create/ack/cancel/replace/trigger semantics;
- UNKNOWN, partial, duplicate, late-fill and overfill classification;
- order/venue/ledger reconciliation;
- immutable internal lifecycle result types.

It has no filesystem, time, network, account, credential, Broker or event-log
authority.  It does not accept arbitrary mappings as already-computed results.

### 4.3 Result evidence v2

Extend `challenger_replacement_opportunity_evidence.py` with strict v1/v2
dispatch and add mirrored schemas:

```text
config/challenger-replacement-opportunity-result-evidence-v2.schema.json
src/crypto_quant/schemas/challenger-replacement-opportunity-result-evidence-v2.schema.json
```

The v1 loader remains able to replay committed v0.70 fixture bytes.  The v2
builder accepts only the internal lifecycle result type.  No public builder
accepts caller-provided action, fill, fee, PnL, status, reason or snapshot.

### 4.4 Opportunity projection and fixture runner

`challenger_replacement_opportunity_projection.py` remains the only semantic
event state machine.  It dispatches result evidence by exact schema/version and
projects the v2 next snapshot.

Create `challenger_replacement_fixture_simulation.py` as a thin fixture-only
orchestrator.  Its public entry point accepts only:

- a retained `ChallengerReplacementOpportunityState`;
- canonical validated input bytes;
- a fixed non-empty worker identity used only for event evidence.

It derives opportunity and recorded times from the canonical input.  It has no
path, URL, clock, price, PnL, outcome, fault, scenario or callback parameter.

## 5. Stable identities and product rules

The economic-intent identity is a stable hash over exactly:

```text
plan_id
plan_hash
simulation_contract_id
simulation_contract_hash
opportunity_id
decision_hash
position_before
action
product_or_null
side_or_null
reduce_only
approved_quantity
approved_notional
instrument_metadata_hash_or_null
```

The caller cannot supply intent, attempt or client IDs.  Attempt ID is derived
from intent ID plus the fixed attempt ordinal `1`; client ID is derived from
intent ID and product.  There is one normal attempt per opportunity.

Product behavior is exact:

- Spot open: BUY, not reduce-only, quantity no greater than the legal size;
- Spot close: SELL, quantity exactly the verified Spot position;
- perpetual open: SELL, one-way and isolated, not reduce-only;
- perpetual close: BUY, reduce-only, quantity exactly the absolute verified
  short position;
- configured leverage remains the frozen integer `1`; effective and technical
  leverage may never exceed `2`; E0 gross exposure remains at most `0.5`;
- hold/no-trade decisions create no economic intent;
- a close or risk flatten cannot open the opposite product;
- an opposite signal first requires cancel/reconcile/verified-flat and waits
  until the next DecisionOpportunity.

Same-intent exact retry returns the exact prior aggregate.  Same intent with
different economic bytes is `DUPLICATE_ECONOMIC_ORDER`.  The state layer does
not silently rebuild or rebase a different intent.

## 6. Lifecycle state machine

### 6.1 Canonical event envelope

Every lifecycle event has exactly these keys:

```text
ordinal
event_type
event_hash
parent_event_hash_or_null
intent_id_or_null
attempt_id_or_null
payload
```

`ordinal` starts at 1 and increases by one.  `parent_event_hash_or_null` is null
only for ordinal 1 and otherwise equals the preceding event hash.  `event_hash`
is the canonical self-hash of the complete event excluding only its own value.
Intent and attempt fields are null only for events whose table row explicitly
allows null.  No event has extra payload keys.

The exact event vocabulary and payload keys are:

| `event_type` | exact `payload` keys | identity rule |
|---|---|---|
| `NO_INTENT_RECONCILED` | `action`, `reason_code` | both IDs null |
| `INTENT_PREPARED` | `product`, `side`, `reduce_only`, `order_type`, `quantity`, `approved_notional`, `instrument_metadata_hash` | intent non-null, attempt null |
| `ATTEMPT_SUBMITTED_FIXTURE` | `client_order_id` | both non-null |
| `ORDER_ACKNOWLEDGED_FIXTURE` | `client_order_id` | both non-null |
| `FILL_OBSERVED_FIXTURE` | `fill_id`, `quantity`, `price`, `notional`, `fee_asset`, `fee`, `cumulative_filled_quantity` | both non-null |
| `ORDER_UNKNOWN_FIXTURE` | `reason_code`, `last_known_cumulative_filled_quantity` | both non-null |
| `ORDER_RECONCILED_FIXTURE` | `terminal_state`, `cumulative_filled_quantity`, `average_fill_price_or_null`, `cumulative_fee` | both non-null |
| `STOP_INTENT_PREPARED` | `stop_intent_id`, `side`, `reduce_only`, `quantity`, `trigger_price`, `order_type` | header intent equals stop intent, attempt null |
| `STOP_ACKNOWLEDGED_FIXTURE` | `stop_intent_id`, `stop_client_order_id` | header intent equals stop intent, stop attempt non-null |
| `STOP_CANCEL_REQUESTED_FIXTURE` | `stop_intent_id` | header intent equals stop intent, stop attempt non-null |
| `STOP_CANCEL_ACKNOWLEDGED_FIXTURE` | `stop_intent_id` | header intent equals stop intent, stop attempt non-null |
| `STOP_TRIGGERED_FIXTURE` | `stop_intent_id`, `bar_open`, `bar_high`, `bar_low`, `gap_reference` | header intent equals stop intent, stop attempt non-null |
| `LIFECYCLE_RECONCILED_FIXTURE` | `engine_projection_hash`, `venue_projection_hash`, `ledger_projection_hash` | both IDs null |
| `LIFECYCLE_FAILED_CLOSED` | `reason_code`, `position_certainty`, `unresolved_intent_ids` | both IDs null |

`fee_asset` is exactly `USDT`; normal order type is `MARKET`; stop order type is
`STOP_MARKET`.  `terminal_state` is one of `FILLED`, `PARTIALLY_FILLED`,
`CANCELED`, `REJECTED` or `UNKNOWN`.  UNKNOWN reason is exactly
`TIMEOUT` or `DISCONNECT`.  All quantities, prices, notionals and fees are
canonical Decimal strings.  Stop intent ID is deterministically derived from
the protected position intent, protected cumulative quantity, trigger and stop
ordinal; its attempt/client IDs are derived from that stop intent and are
stored in the protective-stop snapshot for a later opportunity.  A triggered
stop fill therefore binds the pre-existing stop attempt rather than inventing a
new attempt.  Partial-fill replacement cannot reuse different stop content.

### 6.2 Legal transitions

Normal no-intent/hold:

```text
NO_INTENT_RECONCILED
→ LIFECYCLE_RECONCILED_FIXTURE
```

Normal open:

```text
INTENT_PREPARED
→ ATTEMPT_SUBMITTED_FIXTURE
→ ORDER_ACKNOWLEDGED_FIXTURE
→ FILL_OBSERVED_FIXTURE
→ ORDER_RECONCILED_FIXTURE(FILLED)
→ STOP_INTENT_PREPARED
→ STOP_ACKNOWLEDGED_FIXTURE
→ LIFECYCLE_RECONCILED_FIXTURE
```

Normal strategy close:

```text
STOP_CANCEL_REQUESTED_FIXTURE
→ STOP_CANCEL_ACKNOWLEDGED_FIXTURE
→ INTENT_PREPARED
→ ATTEMPT_SUBMITTED_FIXTURE
→ ORDER_ACKNOWLEDGED_FIXTURE
→ FILL_OBSERVED_FIXTURE
→ ORDER_RECONCILED_FIXTURE(FILLED)
→ LIFECYCLE_RECONCILED_FIXTURE
```

Normal stop close:

```text
STOP_TRIGGERED_FIXTURE
→ FILL_OBSERVED_FIXTURE
→ ORDER_RECONCILED_FIXTURE(FILLED)
→ LIFECYCLE_RECONCILED_FIXTURE
```

A fault observation may place `FILL_OBSERVED_FIXTURE` before acknowledgement;
the later exact acknowledgement is accepted without reordering the evidence.
Multiple fills require strictly increasing cumulative quantity.  Every partial
opening fill must be followed by a new exact `STOP_INTENT_PREPARED` and
`STOP_ACKNOWLEDGED_FIXTURE` for the cumulative position before another
risk-increasing fill is legal.  `ORDER_UNKNOWN_FIXTURE` may be followed only by
an exact `ORDER_RECONCILED_FIXTURE` or terminal `LIFECYCLE_FAILED_CLOSED`.
Conflicting duplicate, overfill, missing stop, unexplained late fill or any
event after a terminal lifecycle event is invalid.

Fault tests construct an immutable private `LifecycleObservation` tuple by
patching the single existing private simulated-venue observation boundary.
That type is not public, serializable, configurable or durable.  A “fresh
reconciliation” fault test means a new pure reducer instance consumes the same
immutable observation tuple; it does not mean that an undurable fault
observation can be rediscovered by a fresh interpreter.  Fresh-interpreter
recovery applies only at the canonical opportunity event boundaries in Section
12.  Production/public code exposes no fault enum, callback, environment flag,
CLI or scenario selector.

Duplicate exact observations are normalized once; conflicting duplicates fail
closed.  Cumulative fill quantity may never decrease or exceed intended
quantity.

## 7. Fill, cost and accounting authority

The lifecycle module does not implement a second economic formula.  It asks the
v0.71 core for the exact adverse fill, legal quantity and signed transition.
Order events bind those results.

All business numbers remain canonical Decimal strings.  No float, random,
ambient Decimal context, wall clock or caller rounding is allowed.  Fee,
funding, cash, isolated margin, realized/unrealized PnL, marked equity and gross
exposure in evidence must equal the v0.71 transition result exactly.

The normal simulated venue cannot improve the core fill or increase approved
risk.  An order-event fill with a different price, quantity, fee or product is
`UNRECORDED_OR_CONFLICTING_FILL`.

## 8. Protective stop semantics

After every opening or partial-opening fill, the simulated position must have
one confirmed persistent stop:

- Spot long trigger: entry × 0.98, rounded down to price tick;
- perpetual short trigger: entry × 1.02, rounded up to price tick;
- stop quantity: exact absolute current position;
- Spot stop side: SELL;
- perpetual stop side: BUY reduce-only.

Non-null `protective_stop_or_null` has exactly:

```text
stop_intent_id
stop_attempt_id
stop_client_order_id
product
side
reduce_only
quantity
trigger_price
status
```

`status` is exactly `CONFIRMED_FIXTURE`; the three identities, product, side,
quantity and trigger must equal the acknowledged stop lifecycle events.  A
close, trigger or replacement consumes these stored identities.

On each completed bar, stop evaluation precedes strategy exit.  Spot triggers
when `low <= trigger`; perpetual triggers when `high >= trigger`.  Gap reference
is `min(open, trigger)` for Spot SELL and `max(open, trigger)` for perpetual BUY,
followed by the frozen adverse slippage and tick rounding.

Normal strategy close requires stop-cancel acknowledgement first.  If the close
is not a reconciled terminal full fill, the known remaining position must have
a newly confirmed stop.  If that cannot be proven, attempt the fixed simulated
flatten.  If flatten remains ambiguous, set:

```text
position_certainty = UNRESOLVED
risk_state = STAGE_FAILED_LOCKED
lifecycle_status = FAILED_CLOSED
reason_code = DISASTER_STOP_MISSING_OR_UNCONFIRMED
```

A late stop fill conflicting with a close may never be silently netted or
corrected.

## 9. Reconciliation and failure closure

Each result records three independently derived projections:

1. **engine order aggregate** is reduced only from the canonical normalized
   lifecycle-event sequence;
2. **simulated venue projection** is reduced independently from the immutable
   raw `LifecycleObservation` tuple and previous venue position; it may not
   read or copy the engine aggregate;
3. **canonical ledger projection** is derived only from the previous canonical
   snapshot plus the v0.71 accounting transition; it may not read or copy the
   engine aggregate or venue projection.

The three reducers have distinct typed inputs and return distinct immutable
types.  The reconciliation function accepts their three completed values; it
does not accept a caller mapping and cannot create one projection from another.
Focused tests separately tamper each reducer output after derivation and require
`LEDGER_POSITION_MISMATCH`, proving the equality check is not a comparison of
three aliases of one postcomputed mapping.

Product, signed quantity, average price, fee, funding and terminal state must
match exactly.  An exact match yields `RECONCILED_FIXTURE`.  Any unexplained
difference yields `LEDGER_POSITION_MISMATCH` and locks new risk.

The following reasons always prevent risk increase:

```text
UNRESOLVED_UNKNOWN
DUPLICATE_ECONOMIC_ORDER
UNRECORDED_OR_CONFLICTING_FILL
LEDGER_POSITION_MISMATCH
DISASTER_STOP_MISSING_OR_UNCONFIRMED
EVIDENCE_DURABILITY_OR_IDENTITY_FAILURE
```

If exact remaining exposure is known, the next snapshot records it as VERIFIED
and locked.  If it is not known, the next snapshot retains the last verified
economic position, marks `position_certainty=UNRESOLVED`, and binds all
unresolved intent IDs.  It never invents a flat position.

## 10. Result evidence v2

The v2 canonical document has exact top-level fields:

```text
$schema
schema_version
mode
result_id
result_hash
evidence_qualification
plan
simulation_contract
build_identity
opportunity
source
decision
previous_snapshot
risk
lifecycle
accounting
next_snapshot
authority
```

Exact constants are:

```text
schema_version = 2.0.0
mode = FIXTURE_SIMULATION_NO_NETWORK_NO_ACCOUNT_NO_BROKER_NO_REAL_ORDER
evidence_qualification = COMMITTED_FIXTURE_NOT_LIVE_MARKET_OR_ACCOUNT
```

The result binds exact plan/contract/build/opportunity identities, input hash,
decision bytes/hash, previous snapshot hash, risk approval/reason, intent and
ordered lifecycle events, fills, fees, funding, stop, reconciliation, exact
accounting and canonical next snapshot.  `result_hash` covers the entire
canonical document excluding only its own value through the existing
self-hash convention.

The maximum canonical result size is 1 MiB.  The bytes loader checks `len(data)`
before JSON parse, decode into nested objects or defensive copy.  The loader
rejects duplicate keys, floats, noncanonical JSON, unknown
or missing fields, wrong schema/version, unsafe integers, malformed Decimal
strings, self-hash mismatch and inconsistent derived identities.  `authority`
must equal the exact fixed object from Section 1: all five counts are zero and
the credential boolean is false; numeric/boolean substitution is invalid.

The fixture build identity uses an explicit non-authoritative test identity;
it does not claim a future commit, tag or CI run.  Committed goldens therefore
do not create a manifest/hash cycle.

## 11. Event integration and terminal mapping

No new event type is added.  v0.72 uses the existing envelope:

```text
INPUT_PREPARED
RESULT_PREPARED
OPPORTUNITY_OBSERVED
OPPORTUNITY_MISSED
```

`RESULT_PREPARED` embeds exact decision bytes and v2 result bytes.  The
projection dispatches v1/v2 by exact `$schema` and `schema_version`; a v2 result
is accepted only in a v0.72 fixture root/build identity.  v1 committed bytes
remain replayable only in their existing isolated v0.70 fixtures.

An opportunity with no durable v2 `RESULT_PREPARED` may become MISSED only
through the existing explicit catch-up API after capture close.  A v2
`RESULT_PREPARED` is an irreversible complete source/decision/lifecycle
observation boundary: catch-up must reject it with
`CHALLENGER_REPLACEMENT_OPPORTUNITY_ACTIVE_CONFLICT`; it can only be recovered
and completed as `OPPORTUNITY_OBSERVED`.  Existing committed v1 bytes retain
their historical replay semantics, but no v1 event is appended to a v0.72
root.  A crash after v2 RESULT and before OBSERVED therefore cannot be
reclassified as MISSED.  Lifecycle failure is terminal
`OPPORTUNITY_OBSERVED` with:

```text
lifecycle_status = FAILED_CLOSED
operationally_complete = false
risk_state = STAGE_FAILED_LOCKED
```

It may count toward observation coverage but never toward lifecycle
completeness.  The projector carries `next_snapshot` from the previous OBSERVED
v2 result.  Genesis alone uses the frozen 100-USDT verified-flat snapshot.
MISSED preserves the prior snapshot; if it was non-flat, the next OBSERVED
transition is economically gap-locked and cannot add risk.

## 12. Crash, retry and concurrency semantics

The runner replays before every append and carries the optimistic
`expected_last_event_hash`.  A stale projection raises the existing fixed
sequence conflict; it does not retry, rebase, replay-to-success or choose a
winner inside that invocation.

Durable boundaries are:

```text
before INPUT
  zero event; exact retry

after INPUT
  replay exact source bytes from the event; no recapture; deterministic
  decision/lifecycle recomputation is allowed because no external side effect
  exists

after RESULT
  replay exact decision and result bytes; decision/lifecycle/accounting
  recomputation count = 0

after OBSERVED
  return exact terminal projection; append/build/recompute count = 0

rename visible before directory fsync
  use the existing event-store durability confirmation before success
```

Concurrency has two different, noninterchangeable cases:

- two processes racing the same single event from the same parent may yield
  `COMMITTED` and `ALREADY_COMMITTED` only when their final event bytes are
  exact; different bytes yield conflict;
- two complete runner invocations racing one opportunity may let one process
  advance beyond the other process's optimistic token.  The stale invocation
  returns `CHALLENGER_REPLACEMENT_OPPORTUNITY_SEQUENCE_CONFLICT` and does not
  convert the winner's terminal result into its own success.  A new, separate
  invocation that begins by replaying an already-terminal exact opportunity
  may return the stored terminal result with zero append/build/recompute.

Replay contains exactly one intent and one set of economic fills.

Because v0.72 has no external Broker/order side effect, replay idempotence is
proved entirely by canonical bytes and zero recomputation after RESULT.  This
must not be generalized as proof of real-exchange exactly-once semantics.

## 13. Golden fixtures

Commit two ordered fixture streams under
`tests/fixtures/challenger_replacement_v072/`:

- `spot-cycle`: open, hold and close;
- `perp-cycle`: open, hold/funding and close.

Each stream contains alternating canonical input/result documents and an exact
manifest with ordered path, byte length and SHA-256.  A fixture-only runner in a
fresh owner-only event root must reproduce every result byte and final
projection exactly.  Root-bound event device/inode/hash values are verified by
the event loader but are not normalized into portable goldens.

Fault lifecycle evidence is tested through fixed private-boundary tests.  It is
not published as an unversioned or caller-selectable portable scenario.

## 14. Test matrix

### 14.1 Normal lifecycle

- Spot open/hold/close with exact intent, fill, fee, stop and verified-flat;
- perpetual short open/hold/funding/close with isolated margin and reduce-only;
- no-trade and hold create no intent;
- stop trigger and conservative gap fill;
- stop-cancel before strategy close;
- reverse blocked until the next opportunity;
- three-way reconciliation exact equality.

### 14.2 Fault and risk

- partial fill and stop quantity replacement;
- fill-before-ack, duplicate exact fill and conflicting duplicate;
- timeout/UNKNOWN and disconnect classification; a new pure reducer instance
  reconciles the same immutable in-process fault-observation tuple;
- late close/stop fill, impossible overfill and wrong product/side;
- missing stop, failed stop rebuild and failed flatten;
- ledger/venue/order mismatch;
- no risk increase under every frozen lock reason;
- known remaining position versus unresolved last-verified position.

### 14.3 Evidence and event log

- mirrored schema exact bytes and valid Draft 2020-12 schema;
- strict canonical/self-hash/binding/authority checks;
- committed v1 replay and v1/v2 root/build mixing rejection;
- genesis and second-opportunity snapshot parent chain;
- MISSED while flat and economic gap after non-flat MISSED;
- failed lifecycle maps to OBSERVED, not MISSED;
- malformed input fails before INPUT with zero event;
- fresh interpreter recovery at canonical INPUT/RESULT/OBSERVED boundaries,
  including RESULT-visible-before-OBSERVED followed by expired catch-up;
- true two-process same/different-result competition.

### 14.4 Static and side effects

- patch socket, HTTP, SDK, keyring, filesystem path, wall clock, Broker and
  order submission boundaries; all counts remain zero;
- no public fault/scenario/path/time/price/PnL/outcome callback;
- no float, random, SQLite, scheduler, deployment, Runner or UI import;
- v0.69 plan, v0.70 event fixtures and v0.71 contract bytes remain unchanged.

## 15. File and size budget

Expected production changes:

```text
Create challenger_replacement_binance_lifecycle.py
Create challenger_replacement_fixture_simulation.py
Modify challenger_replacement_simulation.py minimally
Modify challenger_replacement_opportunity_evidence.py
Modify challenger_replacement_opportunity_projection.py
Modify challenger_replacement_opportunities.py only as a public facade
Add two mirrored v2 schemas
```

Every production module remains at most 700 physical lines.  Net-new production
logic relative to `v0.71.0^{}` is at most 1,500 physical lines across the exact
modules above; pure line moves are neutral and unrelated deletions cannot be
credited.  The v0.70 opportunities facade may not grow a second state machine.

If RED tests prove the bound insufficient, stop and create another semantic
split before adding artifacts or changing the approved budget.  Do not replace
the product-specific boundary with a generic framework to evade the count.

## 16. Verification and release gates

1. design spec committed and independently reviewed;
2. detailed TDD implementation plan committed;
3. each behavior implemented through exact RED then minimal GREEN;
4. focused lifecycle/evidence/opportunity/event tests;
5. adjacent v0.69/v0.70/v0.71 and System Paper primitive regressions;
6. fixed fault, crash, concurrency and complete-cycle golden matrices;
7. final code state complete local suite once, compileall and `make validate`;
8. exact line budgets and forbidden-authority static scan;
9. one independent complete review with Critical/Important zero, followed only
   by targeted review for fixes;
10. public Draft PR with Python 3.9/3.12 and macOS arm64 CI;
11. merge to main and successful exact-main CI;
12. annotated `v0.72.0` whose peeled commit equals `origin/main`.

Healthy fixture evidence does not authorize installation or a running Paper
service.  v0.72 release is complete only when all gates above are evidenced and
the exact status remains
`FIXTURE_LIFECYCLE_EVIDENCE_VERIFIED_NOT_OPERATIONAL`.
