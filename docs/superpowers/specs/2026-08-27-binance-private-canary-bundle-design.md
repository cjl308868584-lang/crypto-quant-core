# v0.77 Binance Private Boundary and Canary Bundle Design

**Date:** 2026-08-27  
**Target release:** `v0.77.0`  
**Status:** original exact spec approved; independent-review safety amendment
awaiting exact written review
**Release class:** code, schemas, deterministic fixtures, disabled configuration
templates, fault evidence and completion dossier only; no installation, secret,
account request, order, transfer, funding or activation authority

## 1. Decision

v0.77 completes the private-venue and staged-Canary half of the accelerated
`CODE_COMPLETE_NOT_ACTIVATED` program preregistered by v0.75. It implements one
narrow Binance boundary for exactly two products:

- `ETHUSDT` Spot, long exposure only; and
- `ETHUSDT` USDⓈ-M perpetual, short exposure only.

The products are mutually exclusive. Futures must be one-way, single-asset and
isolated, with a technical leverage ceiling of 2×. The first active stage, E0,
is further capped at 100 USDT capital and 50 USDT gross exposure.

The release reuses the v0.71 deterministic accounting and v0.72 lifecycle
contracts. It does not create a general broker, exchange abstraction, order
management platform, scheduler, storage engine or control UI. The append-only
replacement-v3 event log remains the sole runtime fact source. Binance response
normalization, ceremony status, Canary stage status, alerts and console views
are projections or events within that authority; none becomes a second source
of position truth.

The only valid release claim is:

```text
CODE_COMPLETE_NOT_ACTIVATED
```

This means the bounded code and offline evidence are complete. It does not mean
that a service has been installed, that a secret has been read, that Binance has
been contacted, that a 72-hour or 90-day clock has started, that the ceremony or
E0 is authorized, or that profitability or an AI advantage has been shown.

## 2. Release sequencing and immutable foundation

### 2.1 v0.76 publication dependency

The v0.77 design and local TDD may use the reviewed v0.76 candidate tree:

```text
reviewed release commit = 0d7922db8fe0da716955b263ec85401003e0cfd9
CI-retrigger commit      = 3fdf26347c3983cb528732fe083a04d05a7273b7
shared tree              = 4d8e9acf8e68c037c8ad274d970bfe67c71d4766
```

The two commits have byte-identical trees. The second commit changes no file or
artifact and exists only to retrigger a GitHub pull-request event.

v0.77 must not freeze formal predecessor release metadata, create its final
build manifest, open a release PR, merge or tag until v0.76 has passed PR CI,
merged-main CI and annotated-tag verification. The final v0.77 release artifact
must bind the real `v0.76.0` tag object, peeled main commit, manifest and CI run.
This unresolved external gate is not filled with a guessed identity and cannot
be bypassed by local tests.

### 2.2 Frozen research and risk contracts

The following released artifacts remain byte-immutable and authoritative:

- v0.69 replacement-v3 plan and its DecisionOpportunity/no-backfill policy;
- v0.74 90-day economic evaluation plan;
- v0.75 accelerated-Canary plan and supersession record;
- v0.76 public simulation, qualification and economic evaluator contracts.

v0.77 must preserve:

- the independent 90-day economic projection and its start/window;
- the continuous 72-hour operational qualification;
- ceremony exclusion from all strategy and economic evidence;
- the E0/E1/E2 capital, duration, cycle and loss limits;
- four and only four absolute hard-stop classes; and
- the separately approved irreversible-action ledger.

No v0.77 result may rewrite a missed opportunity, failed block, earlier event,
research population, fee, funding value, position or result.

### 2.3 Release-time authority

Every v0.77 test, committed fixture, manifest and dossier must prove:

```text
production_activation = false
runtime_install_authorized = false
replacement_start_authorized = false
credentials_allowed = false
private_account_requests = 0
broker_requests = 0
real_orders = 0
fund_movement = 0
production_state_writes = 0
ceremony_authorized = false
e0_activation_authorized = false
```

Mocks and frozen official examples may contain obviously synthetic credentials.
No test may read environment variables, Keychain, home-directory secrets,
production roots or browser/account state.

## 3. Considered approaches

### 3.1 Selected: narrow Binance protocol boundary

Implement exact Spot and USDⓈ-M requests, parsers and state transitions behind
small product-specific capabilities. Reuse the existing lifecycle, event and
projection code. Keep transport and signing separate from policy.

Benefits:

- smallest authority and endpoint surface;
- exact deterministic tests without a live account;
- explicit UNKNOWN and reconciliation semantics;
- no new runtime dependency or generic platform expansion; and
- straightforward mapping into the existing append-only event log.

### 3.2 Rejected: embed CCXT or a generic exchange framework

CCXT would add many unsupported venues, generic order semantics and a large
mutable dependency surface while still requiring project-specific signing,
UNKNOWN resolution, protective-stop and reconciliation logic. It conflicts with
the project's decision to stop expanding generic trading infrastructure.

### 3.3 Rejected: official SDK as the position authority

An SDK may later be evaluated as a replaceable transport implementation, but it
must not own order identity, retries, state, ledger or reconciliation. v0.77 uses
the documented REST contract directly and adds no third-party runtime package.

## 4. Component boundaries

### 4.1 `binance_private_protocol`

This pure module owns:

- endpoint/method/host allowlists;
- deterministic UTF-8 form/query encoding;
- HMAC-SHA256 signature construction and official known-answer tests;
- fixed `recvWindow=5000` validation;
- server-time midpoint/skew calculation and request-authority binding;
- request and response size limits plus a fixed maximum JSON nesting depth;
- exact HTTP/error classification; and
- secret-safe structured diagnostics.

It does not open a socket, read a file or decide whether an order is allowed.
HMAC is the single v0.77 key type. RSA and Ed25519 are not silently accepted;
adding either requires a later versioned design.

Every signed private request binds a fresh server-time observation from the
correct Spot or Futures time endpoint. The observation records local time
immediately before and after the request, derives the midpoint, validates the
maximum round-trip duration and skew, and is appended before signing authority
is granted. Caller-authored timestamps and previously accepted skew objects
cannot authorize a request. Missing, expired, cross-product or disagreeing
time evidence fails before credential access or transport.

### 4.2 `binance_credential_capability`

A capability is constructed only from an explicit repository-external absolute
path and expected owner identity. The future production path is fixed by a
deployment contract, not by a user-supplied CLI argument. The capability:

- uses retained parent descriptors and no-follow opens;
- requires regular files, expected UID, `0600`, `st_nlink == 1` and bounded
  size;
- reads an exact schema containing only `api_key` and `hmac_secret`;
- never exposes either value through `repr`, equality, serialization, logs,
  exceptions or event payloads;
- provides one-use signing access and explicit close/zeroization attempts; and
- fails closed when platform capabilities or identity checks are unavailable.

The retained identity includes `st_mtime_ns` and `st_ctime_ns` as well as
device, inode, owner, mode, link count and size. Each use revalidates the held
descriptor before and after reading; an in-place mutation is rejected even when
device, inode and size are unchanged.

Python cannot guarantee that immutable `bytes` are physically zeroized. The
threat model states this limitation and minimizes lifetime/copies rather than
claiming stronger memory secrecy.

v0.77 creates only a secret-free example path/configuration and a
secret-absence test. It never creates the production credential file.

### 4.3 `binance_private_transport`

The transport accepts only a validated request from the protocol module and an
explicit credential capability. It has no generic URL function. Production
construction remains disabled unless a future exact activation artifact binds
the released build, configuration, account identity, capital/risk limits and
expiry.

Network rules:

- TLS port 443 only;
- exact hosts `api.binance.com` and `fapi.binance.com` only;
- no redirects, proxy-environment inheritance or caller-provided headers;
- bounded connect/read deadlines, response bytes and JSON depth;
- rate-limit headers retained as evidence;
- `418`/`429` obey `Retry-After` and never busy retry;
- `5xx`, timeout, disconnect after send, malformed success and `-1007` become
  execution status `UNKNOWN` for mutating requests; and
- no automatic resend of a mutating request.

Tests patch the lowest socket/HTTP boundary. They cannot pass an arbitrary URL,
callback, command or production path.

Raw-response carriers have an explicitly redacted `repr` and exception
surface. JSON parsing checks depth before any response field is consumed and
maps excessive nesting, recursion failure, duplicate keys and malformed
encoding to a fixed response-domain failure.

### 4.4 `binance_account_preflight`

The preflight is read-only. It verifies, from exact responses and a separate
account-approval receipt:

- API key reading enabled;
- withdrawals disabled;
- IP restriction enabled;
- Spot and Futures trading permissions are exactly those approved;
- account trading status is not locked;
- Spot contains no borrowed/margin exposure;
- current Spot ETH and Futures ETHUSDT positions/open orders are reconciled;
- Futures position mode is one-way;
- multi-assets mode is false;
- ETHUSDT margin type is isolated;
- configured leverage is at most 2×; and
- account is flat before ceremony or a new stage block.

The Binance permission endpoint proves only the returned permission flags and
`ipRestrict` boolean. It does not disclose the exact IP allowlist. Therefore an
account-approval receipt must separately bind the reviewed public egress IP,
the owner who checked it in Binance, collection time and the key fingerprint.
Code validates the binding but cannot claim to prove the human statement.

If margin type, position mode, multi-assets mode or leverage is wrong, preflight
fails. It does not silently change account configuration. Future configuration
POSTs require the separately approved configuration ceremony.

The production order runtime never accepts a preflight `Mapping`. It accepts
exact preflight receipt bytes through a retained owner-only artifact capability
and invokes the strict loader itself. The receipt binds the exact released
build, account-approval hash, credential fingerprint, configuration, account
identity, observed server-time evidence, collection time and expiry. Those
bindings must equal the activation artifact and currently retained credential
capability before any request, signing or event authorization. Loader success
proves structural and hash binding, not the truth of the separately approved
human account attestation.

### 4.5 `binance_order_adapter`

The adapter consumes only a frozen v0.72-compatible intent plus:

- current event projection token;
- approved block/stage identity;
- exact instrument metadata;
- current reconciled account snapshot; and
- immutable activation limits.

It emits normalized Binance venue events into the replacement-v3 event log. It
does not return a free-standing mutable position object.

The runtime reconstructs the intent unconditionally from the retained
replacement-v3 event root, the exact observed DecisionOpportunity, frozen
decision and accounting records, and current expected-last-event hash. A
caller-supplied intent is comparison input only and must be byte-equivalent to
that reconstruction. No schema variant or missing discriminator may bypass
reconstruction.

The v0.72 internal `replacement_client_` plus 64-lower-hex fixture identity exceeds the
current Binance 36-character `newClientOrderId` limit and is never sent. The
venue identifier is deterministically derived as:

```text
cq77 + first_32_lower_hex(
  sha256(plan_hash || block_id || full_intent_id || attempt_ordinal || product)
)
```

This produces exactly 36 allowed characters. The full internal intent identity
and mapping are retained in the event payload. Any collision or venue response
whose symbol/side/quantity/product does not match that mapping fails closed.

Before the first send the adapter queries by client ID. A retry after timeout,
disconnect, `5xx` or lost ACK queries by client ID and trade/fill endpoints. It
never submits a second economic order until the first attempt is proved absent
under the frozen resolution protocol. If absence cannot be proved, the order
remains `UNRESOLVED_ECONOMIC_ORDER_UNKNOWN` and new risk is rejected.

`UNKNOWN` is a durable hard-stop state, but not a terminal observation. Every
entry or fresh-process replay in that state first queries the exact client
order ID, replays matching trades, fills and fees, queries position and balance,
and continues reconciliation. It never resends the economic mutation. If
exposure is discovered, protective-stop management and the safest reconciled
flatten path remain authorized while all new risk stays blocked. The state can
be terminal only after the venue effect and position/protection outcome are
durably reconciled.

The event `BINANCE_ORDER_UNKNOWN` records the ambiguous transport observation
and sets `private_stage=UNKNOWN_QUERY_REQUIRED`; it is not a terminal event.
Only `BINANCE_UNKNOWN_QUERY_OBSERVED`, bound to the exact client-ID order query,
trade query and account-position response identities, may advance it into the
normal acknowledged/rejected/fill/reconciliation path. A query failure leaves
the stage unchanged. `BINANCE_RECONCILIATION_FAILED` is appended before a
runtime reconciliation failure is returned and preserves safe management
authority without granting new-risk authority.

### 4.6 `binance_reconciliation`

Before reconciliation, the runtime must publish exactly one canonical
`BINANCE_RECONCILIATION_INPUTS_CAPTURED` event for the intent.  This is the
durability boundary for all three inputs; an in-memory response hash is not a
publication identity.  Its strict payload contains only:

```text
intent_id
capture_version = "1.0.0"
event_input_bytes_base64 + event_input_sha256
ledger_input_bytes_base64 + ledger_input_sha256
venue_input_bytes_base64 + venue_input_sha256
```

Each decoded value is unique, bounded canonical JSON. `event_input` is the
ordered private-event transcript and authorized intent needed to derive the
internal projection. `ledger_input` is the ordered canonical fill, fee and
funding accounting transcript, exact previous reconciliation bytes or null,
and exact activation capital needed by a separate ledger reducer; it must not
contain or copy a caller-supplied final event projection. `venue_input` contains
the exact order, trade, account, balance, position, income and algo-order
response documents plus the durable authorized order and protective-stop
identities. The three reducers accept only their own decoded input.
Each decoded value is `1..1,048,576` bytes and the existing canonical event
limit remains `4,194,304` bytes; oversize input fails before any event staging
file is created. The transcript ends at the exact
`BINANCE_FILLS_FEES_REPLAYED` order stage and includes any already-reconciled
stop/replacement/cleanup substate. The only main-stage transition is:

```text
BINANCE_FILLS_FEES_REPLAYED
  -> BINANCE_RECONCILIATION_INPUTS_CAPTURED
  -> BINANCE_POSITION_BALANCE_RECONCILED
```

The capture event is published by the existing atomic event protocol.  The
reconciliation artifact carries `event_input`, `ledger_input` and `venue_input`
publication records.  Each record repeats the capture event's device, inode,
owner, mode, link count, final size and full-event SHA-256, and adds the fixed
payload selector, decoded size and decoded SHA-256. Sharing one immutable outer
event inode is intentional and does not merge the three parsing authorities.
The retained event-root capability reopens and verifies the exact canonical
event before any projection is trusted. Same decoded bytes in a replacement
inode are therefore rejected.

Each publication record has the exact keys
`capture_event_sequence`, `capture_event_hash`, `device`, `inode`, `uid`,
`mode_octal`, `link_count`, `event_size`, `event_sha256`, `payload_selector`,
`decoded_size` and `decoded_sha256`. Mode is exactly `0600`, link count exactly
one, and the three records must share all outer-event identity fields while
using the three different fixed selectors. A byte-only reconciliation parser
may validate canonical structure and hashes but is explicitly non-authorizing.
Every runtime, observer, controller or evaluator authority path uses the strict
loader with the retained event-root capability; it reopens the sequence file
with the existing no-follow/nonblocking verifier and compares every stored
identity field before returning a trusted projection.

Crash semantics are fixed: before capture commit, a retry may repeat read-only
venue queries but may not resend an economic mutation; after capture commit and
before reconciliation commit, fresh-process retry performs zero network calls
and replays the captured bytes; after reconciliation commit, the existing
reconciliation replay path applies. A second capture for the same intent is
allowed only as exact `ALREADY_COMMITTED`; any differing payload conflicts.
Staging files remain non-authoritative under the existing event protocol.

Reconciliation compares three independently parsed projections:

1. intended/internal event state;
2. Binance order, trade, balance, position and funding responses; and
3. the existing deterministic local ledger, independently replayed from its
   canonical published accounting artifacts rather than copied from item 1.

Exact Decimal arithmetic is used throughout. No float enters a financial
calculation. Fill IDs are unique and append-only. Replayed fills/fees/funding are
idempotent; conflicting duplicates fail closed. Same bytes on a different
untrusted publication identity are not silently adopted.

Success requires exact agreement on product, signed quantity, average entry,
realized/unrealized PnL inputs, cumulative fees, funding, open orders and
protective-stop identity. A mismatch never chooses the most favorable source.

Each input uses the retained read-only event-root capability and binds the exact
capture-event publication record described above. Venue trades
must bind the exact Binance order ID and deterministic client order ID. For
Futures, the reconciled stop trigger, side, quantity, reduce-only flag and
client-algo ID must equal the authorized protective intent. Same bytes under a
different publication identity are rejected, including on fresh-process replay.

### 4.7 `binance_protective_stop`

Current Binance USDⓈ-M documentation places conditional TP/SL orders on the
Algo Order API. v0.77 therefore uses:

```text
POST   /fapi/v1/algoOrder
GET    /fapi/v1/algoOrder
GET    /fapi/v1/openAlgoOrders
DELETE /fapi/v1/algoOrder
```

The stop is `CONDITIONAL` + `STOP_MARKET`, `BUY`, `positionSide=BOTH`,
`workingType=MARK_PRICE`, `quantity` equal to the exact absolute reconciled short,
`reduceOnly=true`, `closePosition=false`, and a deterministic 36-character
`clientAlgoId`. Close-all is not used in v0.77. Every partial entry fill must be
covered by an exact-quantity stop, and any increase or decrease in reconciled
short quantity requires a no-gap stop replacement protocol. It may not leave
any short quantity unprotected.

Perpetual exposure is not reported operationally healthy until the position and
the exact active protective order have both been queried and reconciled. A
partial entry fill must create or replace protection for the exact exposed
quantity before more risk is allowed. Loss, cancellation, rejection or
unverifiable status of the stop while exposed is an absolute hard stop.

The append-only stop substate has the exact durable order below. These three
query/send boundary events are required so a process crash can never turn an
unknown mutation into a second create request:

```text
BINANCE_STOP_INTENT_AUTHORIZED
BINANCE_STOP_ABSENCE_CHECKED
BINANCE_STOP_SIGNED_REQUEST_PREPARED
BINANCE_STOP_REQUEST_SEND_STARTED
BINANCE_STOP_ACKNOWLEDGED
BINANCE_STOP_RECONCILED
```

`STOP_ABSENCE_CHECKED` binds the exact client-algo query response hash and is
valid only for a proven `-2013` absence. `STOP_SIGNED_REQUEST_PREPARED` binds
the deterministic Algo-create request ID, encoded-parameter hash and timestamp.
`STOP_REQUEST_SEND_STARTED` is appended and durably replayed before transport.
Before this event, a fresh process may rebuild the exact prepared request; at
or after this event it may only query `FUTURES_ALGO_QUERY` by the same
`clientAlgoId` and must never send create again. An absent or unresolved query
after send-start is a hard stop, not mutation-retry authority. Stop replacement
uses the same candidate substate while the verified old stop remains active;
only a reconciled candidate may precede replacement success and old-stop
cancellation.

Any newly observed partial short fill creates exposed quantity and enters
protection handling before the runtime may return `ORDER_IN_PROGRESS` or
perform another risk-increasing action. Replacement is query-first and no-gap:
retain the verified old stop, create the deterministic candidate for the new
exact quantity, query and reconcile the candidate, then cancel the old stop and
query its terminal status. A crash at every boundary resumes from canonical
events without duplicate creation. Failure to establish verified protection
returns only the protective hard stop and continues safe query/flatten
management.

### 4.8 Ceremony and stage controllers

The ceremony controller implements the exact v0.75 sequence and label
`OPERATIONAL_CEREMONY_NOT_STRATEGY_EVIDENCE`. It consumes venue-confirmed minimum
notional/step sizes obtained during the separately approved real preflight. Its
events are structurally excluded from DecisionOpportunity cycles, 72-hour
performance, 90-day economics and stage cycle counts.

The stage controller implements E0/E1/E2 without automatic promotion:

| Stage | Capital | Gross exposure | Minimum time | Natural cycles |
|---|---:|---:|---:|---:|
| E0 | 100 USDT | 50 USDT / 0.5× | 7 days | 3 |
| E1 | 300 USDT | 1× | 14 days | 5 |
| E2 | 1000 USDT | 2× hard cap | 30 days | 10 |

Each stage also requires at least one natural complete Spot cycle and one
natural complete perpetual cycle. Promotion requires a new exact approval
artifact. Ceremony activity never counts.

Loss gates use conservative marked equity including realized and unrealized
PnL, fees and funding:

- E0/E1: 2 USDT UTC-day loss stops new risk until the next UTC day; 5 USDT
  high-water drawdown flattens and fails the block;
- E2: 2% of stage capital UTC-day loss stops new risk; 7.5% high-water drawdown
  flattens and fails the block.

Restart, product switch, a new process or a new calendar object cannot clear a
daily stop or reuse duration/cycles from a failed block.

The controller does not accept caller-authored ceremony, equity, hard-stop,
promotion or incident mappings as authority. It strictly replays the retained
replacement-v3 event root and loads every referenced activation, promotion,
reconciliation and incident/unlock artifact through its exact strict loader and
publication identity. Runtime reconciliation failures append their canonical
failure event before returning. An in-memory or fixture-only projection cannot
authorize a stage transition.

#### 4.8.1 Single-root authority and referenced-artifact identity

The `exact artifact root capability` in this section is the retained
replacement-v3 event-root capability itself. v0.77 must not introduce a second
mutable artifact directory, generic resolver or database. Exact approval and
reconciliation bytes are published first as
`CANARY_AUTHORITY_ARTIFACT_PUBLISHED` events; the canonical event file is the
only publication. A later transition refers to the publication by the exact
five-field record `sequence`, `event_hash`, `device`, `inode` and `size` plus
the artifact ID. The referenced event must precede the transition.

The event layer exposes one read-only verifier which reopens that exact
sequence under the retained directory descriptor with no-follow/nonblocking
flags, validates the five publication fields, and returns canonical event
bytes. Missing files, same bytes on a different inode, symlinks, hardlinks,
wrong ownership/mode/type/size, a changed root or a reference to a different
event all fail closed. This verifier never creates, writes, renames, chmods or
repairs an object.

`CANARY_AUTHORITY_ARTIFACT_PUBLISHED` has exactly these payload fields:

```text
event_type
block_id
occurred_at
artifact_kind       ACTIVATION | PROMOTION | RECONCILIATION | INCIDENT_UNLOCK
artifact_id
artifact_bytes_base64
artifact_sha256
```

The artifact event itself is not a stage transition. Duplicate publication of
the same artifact ID is invalid even when the bytes match; the first canonical
publication is the sole identity. `ACTIVATION` uses
`load_binance_private_activation_bytes`; `RECONCILIATION` uses
`load_binance_reconciliation_bytes_strict` against the same retained root.
`PROMOTION` and `INCIDENT_UNLOCK` use one closed canonical approval schema. Its
self-hashed ID, kind, plan/build identity, stage, new block, exact previous
block, approval/expiry times and zero-authority fields are all mandatory.
The exact approval keys are `$schema`, `schema_version`, `approval_id`,
`approval_kind`, `plan`, `build_identity`, `stage`, `block_id`,
`previous_block_id`, `approved_at`, `expires_at` and `authority`.
`approval_id` is `canary_promotion_` or `incident_unlock_` followed by the
lowercase SHA-256 of the canonical document with only `approval_id` removed.
`authority` is exactly `network_requests=0`, `orders=0`, `state_writes=0` and
`production_activation=false`. The approval must satisfy
`approved_at <= transition.occurred_at < expires_at`. Activation is likewise
loaded at the referenced transition time, not the later projection-observation
time, so expiry cannot rewrite valid historical state.

The public Canary projector replays the complete mixed event root, validates
plan/build identity on every event, indexes authority artifacts and derives
state only from canonical opportunity/private events plus strictly loaded
artifacts. The existing tuple reducer remains private and receives only the
derived normalized facts. In particular:

- stage start requires a strict activation publication; E1/E2 additionally
  require a `PROMOTION` approval, while recovery of a failed same-stage block
  requires an `INCIDENT_UNLOCK` approval;
- ceremony and equity facts require an exact strict reconciliation
  publication; equity is recomputed from the matched venue projection and
  `flat` is recomputed from signed quantity/open-order state;
- UNKNOWN, position mismatch and missing-stop hard stops must reference the
  exact canonical private failure event that supplies the reason code;
- a post-limit new-risk attempt must reference a later canonical
  `BINANCE_INTENT_AUTHORIZED` event for that block; and
- natural cycle counts come from completed canonical opportunity/private
  lifecycles, never a caller-supplied cycle mapping.

Any missing, duplicate, noncanonical, forward, stale, mismatched or
same-bytes/different-publication reference returns
`CHALLENGER_REPLACEMENT_CANARY_CANONICAL_AUTHORITY_INVALID`. No partial
projection is returned and no event or artifact is written by the projector.

## 5. Exact Binance REST inventory

The implementation uses only the following documented endpoints. Any method,
host or path not present here is rejected before signing or transport.

### 5.1 Public timing and metadata

```text
GET https://api.binance.com/api/v3/time
GET https://api.binance.com/api/v3/exchangeInfo?symbol=ETHUSDT
GET https://fapi.binance.com/fapi/v1/time
GET https://fapi.binance.com/fapi/v1/exchangeInfo
GET https://fapi.binance.com/fapi/v1/premiumIndex?symbol=ETHUSDT
```

### 5.2 Permission/account reads

```text
GET /sapi/v1/account/apiRestrictions
GET /sapi/v1/account/apiTradingStatus
GET /api/v3/account
GET /api/v3/openOrders?symbol=ETHUSDT
GET /api/v3/order
GET /api/v3/myTrades
GET /fapi/v1/positionSide/dual
GET /fapi/v1/multiAssetsMargin
GET /fapi/v1/symbolConfig?symbol=ETHUSDT
GET /fapi/v3/account
GET /fapi/v3/positionRisk?symbol=ETHUSDT
GET /fapi/v1/openOrders?symbol=ETHUSDT
GET /fapi/v1/order
GET /fapi/v1/userTrades?symbol=ETHUSDT
GET /fapi/v1/income
GET /fapi/v1/algoOrder
GET /fapi/v1/openAlgoOrders?symbol=ETHUSDT
```

### 5.3 Mutations compiled but disabled in v0.77

```text
POST   /api/v3/order
DELETE /api/v3/order
POST   /fapi/v1/order
DELETE /fapi/v1/order
POST   /fapi/v1/algoOrder
DELETE /fapi/v1/algoOrder
POST   /fapi/v1/leverage
POST   /fapi/v1/marginType
```

There is no withdrawal, deposit, universal transfer, internal transfer,
borrow/margin, convert, subaccount, position-mode mutation, multi-assets-mode
mutation or arbitrary asset endpoint. A static test proves those strings and
generic request entry points are absent from the executable boundary.

The following official documentation is the normative external reference as
observed on 2026-08-27:

- [Spot REST request security](https://developers.binance.com/en/docs/products/spot/rest-api)
- [Wallet API key permission](https://developers.binance.com/docs/wallet/account/api-key-permission)
- [USDⓈ-M Futures trade REST API](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade)
- [USDⓈ-M Futures account REST API](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/account)

Because Binance APIs can change, future real installation must rerun a
versioned endpoint/schema compatibility preflight. It may not silently accept a
changed field, endpoint or order semantic.

## 6. Request and response state machine

For a mutating intent:

```text
INTENT_AUTHORIZED
  -> VENUE_ABSENCE_CHECKED
  -> SIGNED_REQUEST_PREPARED
  -> REQUEST_SEND_STARTED
  -> ACKNOWLEDGED | REJECTED | UNKNOWN_QUERY_REQUIRED
  -> PARTIALLY_FILLED | FILLED | CANCELED | EXPIRED | UNKNOWN_QUERY_REQUIRED
  -> FILLS_AND_FEES_REPLAYED
  -> POSITION_BALANCE_RECONCILED
  -> PROTECTION_RECONCILED_IF_EXPOSED
  -> TERMINAL_RECONCILED
```

Only `TERMINAL_RECONCILED` permits the next economic transition. `REJECTED` is
terminal only when Binance proves no fill and no position effect. `CANCELED`
still requires fill replay because cancel/fill races are possible. A local
timeout does not mean rejection.

`UNKNOWN_QUERY_REQUIRED` blocks all new risk and is one of the four absolute
hard-stop classes. It retains read-only query, reconciliation,
protective-stop and safe-flatten authority for the already-started attempt. It
cannot become `TERMINAL_RECONCILED` merely because the original response was
lost; exact order, fill, position and protection observations are mandatory.

Crash recovery replays the canonical event log, queries the exact client ID,
replays fills/fees/funding and reconciles before deciding. It never reconstructs
a new timestamp/client ID for an already durable attempt and never resends
merely because the local process missed an ACK.

## 7. Failure taxonomy

The four absolute stage-block hard stops remain exact:

1. `UNRESOLVED_ECONOMIC_ORDER_UNKNOWN`;
2. `VENUE_LOCAL_POSITION_MISMATCH`;
3. `PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP`;
4. `RISK_INCREASE_ATTEMPT_AFTER_STAGE_LOSS_LIMIT`.

They reject new risk, initiate the safest reconciled flatten path where
possible, permanently fail the current block and require an immutable incident
record, verified flatness and a separately approved unlock before a new block.
They do not erase history or permanently abandon the project.

Recoverable only while flat and with no unresolved economic state:

- short network interruption;
- flat missed opportunity;
- rate-limit backoff;
- insufficient sample/product coverage; and
- negative short-window return.

An exposed disconnect is not categorized as harmless. The system must continue
read-only queries and protective management, reject new risk and flatten if it
cannot prove safe management.

## 8. Evidence, storage and UI

Private venue facts append to the existing replacement-v3 canonical event root
through retained capabilities and expected-last-hash optimistic concurrency.
No SQLite database, mutable order table or separate broker ledger is added.

Secret-bearing request bytes are never events. Evidence stores:

- endpoint ID, method and parameter-name set;
- hashed key fingerprint, never API key or secret;
- canonical unsigned intent hash;
- client order/algo ID and Binance order/fill IDs;
- response classification and selected normalized fields;
- raw-response SHA-256 plus an owner-only bounded raw evidence object whose
  secret headers/query signature are removed before publication; and
- reconciliation hashes and results.

The existing loopback-only v0.61 console gains read-only v3 projections for
qualification, ceremony, stage, unresolved order, protective stop, daily loss,
drawdown and reconciliation. It adds no write endpoint, activation control,
credential form, order button or external resource. Console availability is
not a prerequisite for safe order management and cannot grant authority.

## 9. Configuration and installation artifacts

v0.77 provides, without installing:

- fixed owner-only path contract;
- disabled LaunchAgent/config templates;
- credential-path template containing no secret;
- account-approval and activation-receipt schemas/loaders;
- preflight/observer CLI code whose default is no account access;
- secret-absence scanner;
- install, recovery, incident, flatten and rollback runbooks; and
- a `CODE_COMPLETE_NOT_ACTIVATED` dossier.

Every executable entry point requires a released-build identity and an exact
authority artifact. Merely importing a module, installing the package, loading
a plist, opening the UI or possessing a credential file cannot enable private
network or order authority.

## 10. TDD and fault matrix

Every behavior is developed RED → minimal GREEN → refactor. The implementation
plan must sequence at least:

1. endpoint/signing/timing known answers;
2. credential capability and secret-absence boundaries;
3. response schemas and error classification;
4. read-only account preflight;
5. Spot order/query/fill/cancel lifecycle;
6. Futures order/query/fill/cancel lifecycle;
7. Algo protective-stop lifecycle;
8. three-way reconciliation and fresh-process replay;
9. ceremony controller and evidence exclusions;
10. E0/E1/E2 loss/promotion/incident state machines;
11. alerts/UI/runbooks/templates; and
12. immutable fault receipt and completion dossier.

The fault matrix must include:

- official signing known answers and parameter-order/encoding mutations;
- clock ahead/behind, expired window and server-time disagreement;
- DNS/TLS/redirect/proxy/host/path rejection;
- timeout or disconnect before send, during send and after send;
- ACK loss, `-1007`, `5xx`, malformed `2xx`, `418` and `429`;
- duplicate client ID, query-before-retry and proven-absent rules;
- partial fill, cancel/fill race, late fill, overfill and conflicting fill;
- fee/funding duplication and correction attempts;
- same bytes/different identity and replay after process kill;
- Spot/perpetual mutual-exclusion violations;
- wrong position mode, multi-assets mode, margin type or leverage;
- partial perpetual exposure before stop confirmation;
- stop rejection/loss/cancel/replace/query mismatch;
- balance/position/order/ledger disagreement;
- daily stop, drawdown, restart and UTC rollover;
- ceremony evidence incorrectly entering economic projections;
- read-only UI loader failures; and
- any secret/API-key/signature occurrence in logs, exceptions or artifacts.

All tests use deterministic fixtures, mocks or fixed official examples. Their
authority counters must remain zero. No test result is a real account or market
qualification.

The matrix is an executable campaign, not a catalogue of test names. Every
listed condition has a unique atomic case ID and a dedicated probe that invokes
the relevant production boundary. A combined case is permitted only when the
receipt records and tests separately assert every named subcondition. Metadata
such as `fresh_process=true` or hard-coded zero authority counts is not evidence.

For every case the immutable receipt records exact fixture bytes and SHA-256;
observed return/failure code and stdout/stderr hashes; measured credential,
private-network, mutating-request, order, fund and production-state boundary
counts; subprocess executable, argv, exit status and output hashes where a
fresh interpreter is required; and exact canonical event/artifact identities
before and after the probe.

The campaign binds a sorted per-file inventory of every v0.77 executable
runtime module, schema and fixture plus an aggregate executable-core hash. It
may reuse a released v0.76 fault receipt only for a byte-identical requirement
whose exact foundation case, artifact hash and build identity are cited; all
private Binance semantics require direct v0.77 probes. Secret-absence probes
place a synthetic sentinel only at the controlled test boundary and scan all
captured logs, exceptions, events and artifacts, publishing only hashes and
zero occurrence counts. The strict loader recomputes all identities and rejects
open caller-provided build objects.

## 11. Review, release and code-size gates

The implementation stays in one semantic version with internal TDD commits.
It receives:

- one complete independent design/spec review;
- one complete independent implementation review;
- targeted re-review only after fixes;
- focused tests during development;
- one full local suite on the final unchanged candidate;
- compileall, manifest, package, schema, secret and release validation;
- Python 3.9, Python 3.12 and macOS arm64 PR CI;
- merged-main CI; and
- an annotated `v0.77.0` tag whose peeled commit equals origin/main.

No duplicate full test is run on an unchanged tree. GitHub CI inability blocks
release identity but does not authorize weakening or deleting the gate.

The implementation plan must set per-component and aggregate line budgets after
inventorying reusable v0.71/v0.72/v0.76 code. Any design that grows a generic
transport, broker or order platform is rejected even if under the numeric cap.

The amended 4,500-line aggregate cap remains a release gate. Remediation first
deletes the invalid Task 11 label runner and consolidates duplicated projection
and reconciliation logic. If the measured safe implementation still cannot
meet the cap, work stops for an explicit measured budget amendment; receipt
authority, UNKNOWN recovery, protection and reconciliation may not be weakened
to pass the numeric gate.

## 12. Completion dossier

The dossier maps every v0.75-v0.77 canonical requirement to exact code, tests,
fixtures, manifests, review findings and CI/tag evidence. It records:

- architecture and threat model;
- dependency/license and endpoint inventory;
- exact commits, tags, manifests and hashes;
- fault, restart, reconciliation and secret-absence evidence;
- read-only console acceptance;
- known limitations and residual risks;
- the v0.76 GitHub Actions quota delay if it affected sequencing; and
- every remaining external action and wall-clock gate.

The dossier must end with all of these true:

```text
CODE_COMPLETE_NOT_ACTIVATED
production_activation=false
no service installed or started
no production root or start receipt created
no credential created or read
no private Binance request made
no real order submitted
no funds moved
no 72-hour or 90-day timer started
no profitability or AI-advantage conclusion
```

## 13. Actions still requiring separate real-time approval

This code release does not execute or imply approval for:

1. installing the production-like simulation service or writing its root;
2. starting it and creating a start receipt;
3. creating or reading Binance credentials;
4. binding the exact IP allowlist/account identity;
5. changing Futures margin/leverage/account configuration;
6. funding or transferring ceremony/E0 capital;
7. submitting Spot ceremony orders;
8. submitting Futures ceremony/protective/close orders;
9. activating E0;
10. promoting E1 or E2;
11. unlocking a failed block; or
12. adding another venue, product, leverage or capital.

Those actions require exact released-build/configuration/account/limit/expiry
bindings at the moment of execution. A general project approval cannot be used
as a substitute for those irreversible approvals.

## 14. Acceptance criteria

The v0.77 design is satisfied only when:

- the exact two-product, Binance-only boundary is enforced statically and at
  runtime;
- signing, timing and endpoint behavior match frozen official examples;
- client IDs fit Binance's 36-character contract and remain mapped to full
  internal identities;
- mutating retries are query-first and unresolved UNKNOWN is a hard stop;
- UNKNOWN remains query/reconciliation/protection recoverable but never grants
  mutation-resend or new-risk authority;
- Spot and perpetual lifecycles cover ACK, partial fill, cancel, late fill,
  fees, funding, balances and positions;
- every partial perpetual exposure is protected before runtime return and stop
  replacement has no unprotected gap;
- three-way reconciliation is independently derived, publication-identity
  bound, deterministic and fresh-process replayable;
- ceremony and stage controllers strictly replay canonical authority and
  preserve v0.75 policies;
- preflight, activation, approval, credential and server-time inputs are
  strictly loaded and mutually bound before signing;
- bounded response parsing rejects excessive JSON depth with a fixed error;
- secrets cannot enter logs, exceptions, events, manifests or fixtures;
- the existing loopback UI remains read-only and non-authoritative;
- fault/recovery evidence is bound to the exact released build;
- Critical and Important findings are zero;
- predecessor/main/CI/tag identities are exact; and
- the only conclusion is `CODE_COMPLETE_NOT_ACTIVATED`.
