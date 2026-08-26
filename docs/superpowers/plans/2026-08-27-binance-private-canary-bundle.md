# v0.77 Binance Private Boundary and Canary Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a fixture/mock-only Binance Spot-long and USDⓈ-M
perpetual-short private boundary, ceremony/stage controllers and auditable
`CODE_COMPLETE_NOT_ACTIVATED` dossier without contacting an account or granting
order authority.

**Architecture:** Extend the existing replacement-v3 append-only event authority
with a fixed set of Binance-private events. Keep signing, credential capability,
transport, parsing, reconciliation and stage policy in small product-specific
modules. Reuse v0.71/v0.72 lifecycle/accounting, v0.75 risk governance and v0.76
observer/UI; do not create generic exchange, broker, storage or UI frameworks.

**Tech Stack:** Python 3.9/3.12 stdlib, `jsonschema`, canonical JSON/Decimal
helpers already in `crypto_quant`, `unittest`, fixed official Binance examples,
Git/GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-27-binance-private-canary-bundle-design.md`

## Global Constraints

- Exactly `ETHUSDT` Spot long and `ETHUSDT` USDⓈ-M perpetual short.
- Spot/perpetual exposure is mutually exclusive.
- Futures is one-way, single-asset, isolated and at most 2×; E0 gross exposure
  is at most 50 USDT.
- Existing append-only replacement-v3 event log is the sole runtime fact source.
- Endpoint/method/host allowlist is closed; no generic URL/request API.
- HMAC-SHA256 is the only key type in v0.77; `recvWindow` is exactly 5000 ms.
- Venue client/algo IDs are exactly `cq77` plus 32 lower-hex characters.
- No mutation retry before exact client-ID query and fill reconciliation.
- The four v0.75 hard-stop classes remain exact; no fifth hard stop.
- Ceremony events never count as strategy, 72-hour or 90-day evidence.
- No third-party runtime dependency and no new SQLite/mutable position store.
- Release-time authority counters remain zero; no secret/account/order/fund call.
- v0.76 final tag/CI identity is a hard prerequisite for v0.77 release freeze,
  but local v0.77 TDD may continue against reviewed tree
  `4d8e9acf8e68c037c8ad274d970bfe67c71d4766`.
- New production code budget: protocol+transport ≤600 lines, credential ≤220,
  preflight ≤380, order/reconciliation ≤850, controllers ≤650,
  projection/delivery ≤300; aggregate ≤3,000 physical lines.
- One final local full suite per final code state; no repeated unchanged full run.

## File Map

Create:

- `src/crypto_quant/challenger_replacement_binance_private_contract.py` —
  closed endpoint inventory and private-event projection grammar.
- `src/crypto_quant/challenger_replacement_binance_private_protocol.py` — fixed
  request identity, encoding, signing and response classification.
- `src/crypto_quant/challenger_replacement_binance_credential.py` — retained,
  owner-only secret capability.
- `src/crypto_quant/challenger_replacement_binance_private_transport.py` —
  disabled-by-default fixed-host HTTP transport.
- `src/crypto_quant/challenger_replacement_binance_preflight.py` — strict
  permission/account/mode/flatness evaluation.
- `src/crypto_quant/challenger_replacement_binance_private_lifecycle.py` — venue
  client identity, Spot/Futures/Algo request and normalization state machine.
- `src/crypto_quant/challenger_replacement_binance_reconciliation.py` — exact
  venue/event/ledger comparison and replay.
- `src/crypto_quant/challenger_replacement_canary_controller.py` — ceremony and
  E0/E1/E2 block projections.
- `src/crypto_quant/challenger_replacement_private_fault_matrix.py` — fixed
  offline fault runner and strict receipt loader.
- schemas for credential reference, permission/account snapshot, private event,
  ceremony/stage projection, fault receipt and completion dossier.
- deterministic official-example and private lifecycle fixtures under
  `src/crypto_quant/fixtures/challenger-replacement-v077/`.
- exact tests named after each module plus `tests/test_challenger_replacement_v077_release.py`.
- disabled config/plist examples and v0.77 runbooks/ADR/status/dossier.

Modify:

- `src/crypto_quant/challenger_replacement_opportunities.py` — delegate the
  exact private event family after `OPPORTUNITY_OBSERVED` without changing public
  opportunity semantics.
- `src/crypto_quant/challenger_replacement_economic_evaluation.py` — ignore only
  schema-valid private operational events when deriving economic facts.
- `src/crypto_quant/operations_projection_v3.py`, `operations_alerts.py` and the
  existing dashboard assets — read-only private health projection.
- build/version/manifest files only after final reviewed code is frozen.

---

### Task 1: Freeze private event and endpoint contracts

**Files:**
- Create: `src/crypto_quant/challenger_replacement_binance_private_contract.py`
- Create: `src/crypto_quant/schemas/challenger-replacement-binance-private-event-v1.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-binance-private-request-v1.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-binance-account-approval-v1.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-binance-private-activation-v1.schema.json`
- Create: `tests/test_challenger_replacement_binance_private_contract.py`
- Modify: `src/crypto_quant/challenger_replacement_opportunities.py`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class BinanceAccountApproval:
    account_identity_sha256: str
    key_fingerprint: str
    reviewed_egress_ip: str
    reviewer_uid: int
    reviewed_at: str
    expires_at: str
    spot_trading_approved: bool
    futures_trading_approved: bool

@dataclass(frozen=True)
class BinancePrivateActivation:
    activation_id: str
    build_identity: Mapping[str, str]
    configuration_sha256: str
    account_approval_sha256: str
    block_id: str
    stage: str
    capital_usdt: str
    max_gross_exposure_usdt: str
    max_leverage: str
    expires_at: str
    production_activation: bool
```

Also produces: `PRIVATE_EVENT_TYPES: frozenset[str]`,
  `BINANCE_PRIVATE_ENDPOINTS: Mapping[str, tuple[str, str, str, bool]]`,
  `require_binance_private_endpoint(endpoint_id: str) -> tuple[str, str, str, bool]`,
  `load_binance_account_approval_bytes(data: bytes, *, now: str) -> BinanceAccountApproval`,
  `load_binance_private_activation_bytes(data: bytes, *, build_identity: Mapping[str, str], now: str) -> BinancePrivateActivation`,
  `apply_challenger_replacement_private_event(projection, event) -> None`, and
  the closed endpoint inventory consumed by Tasks 2-7. Each endpoint tuple is
  `(host, method, path, mutating)`.
- Consumes: `ChallengerReplacementCanonicalEvent`, v0.75 plan and v0.76 build
  identity.

- [ ] **Step 1: Write contract RED tests**

```python
def test_private_event_requires_observed_opportunity_and_exact_payload():
    state = observed_opportunity_state()
    append_private(state, "BINANCE_INTENT_AUTHORIZED", {"product": "spot"})
    self.assertEqual(state.replay()["opportunities"][OID]["private_stage"],
                     "INTENT_AUTHORIZED")

def test_private_event_before_observed_is_rejected():
    with self.assertRaisesRegex(ValueError, "PRIVATE_EVENT_INVALID"):
        append_private(prepared_opportunity_state(), "BINANCE_INTENT_AUTHORIZED", VALID)

def test_unknown_endpoint_and_private_event_are_rejected_before_signing():
    with self.assertRaisesRegex(ValueError, "BINANCE_ENDPOINT_FORBIDDEN"):
        require_binance_private_endpoint("WITHDRAW")

def test_activation_binds_build_account_limits_and_expiry():
    altered = dict(valid_activation_document())
    altered["max_gross_exposure_usdt"] = "51"
    with self.assertRaisesRegex(ValueError, "BINANCE_ACTIVATION_INVALID"):
        load_binance_private_activation_bytes(canonical(altered),
                                              build_identity=BUILD,
                                              now=NOW)
```

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src:tests python3 -m unittest tests.test_challenger_replacement_binance_private_contract -v
```

Expected: import/schema/event delegation failures; no file or network side effect.

- [ ] **Step 3: Implement the minimum event grammar**

Define the exact event order:

```text
BINANCE_INTENT_AUTHORIZED
BINANCE_ABSENCE_CHECKED
BINANCE_SIGNED_REQUEST_PREPARED
BINANCE_REQUEST_SEND_STARTED
BINANCE_ORDER_ACKNOWLEDGED | BINANCE_ORDER_REJECTED | BINANCE_ORDER_UNKNOWN
BINANCE_ORDER_PARTIALLY_FILLED | BINANCE_ORDER_FILLED |
  BINANCE_ORDER_CANCELED | BINANCE_ORDER_EXPIRED | BINANCE_ORDER_UNKNOWN
BINANCE_FILL_OBSERVED (zero or more, unique venue fill identity)
BINANCE_FILLS_FEES_REPLAYED
BINANCE_POSITION_BALANCE_RECONCILED
BINANCE_PROTECTION_RECONCILED_IF_EXPOSED
BINANCE_RECONCILIATION_SUCCEEDED | BINANCE_RECONCILIATION_FAILED
```

Algo-stop and ceremony/stage events are separate exact branches introduced by
Tasks 7 and 9. Unknown private event names, wrong opportunity ID, post-terminal
append and altered plan/build identity fail before publication.

The account-approval schema binds exact hashed account identity, key
fingerprint, reviewed public egress IP, reviewer UID, review/expiry times and
approved Spot/Futures permissions. The activation schema binds released build,
configuration hash, account-approval hash, stage/block identity, capital,
gross-exposure/leverage limits, expiry and the explicit activation boolean.
Both loaders reject missing/extra keys and return immutable typed values rather
than caller-authored dictionaries.

- [ ] **Step 4: Run contract and public-event regression tests**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_binance_private_contract \
  tests.test_challenger_replacement_opportunities \
  tests.test_challenger_replacement_v3_runtime -v
```

- [ ] **Step 5: Commit**

```bash
git add src/crypto_quant/schemas/challenger-replacement-binance-private-*.json \
  src/crypto_quant/challenger_replacement_binance_private_contract.py \
  src/crypto_quant/challenger_replacement_opportunities.py \
  tests/test_challenger_replacement_binance_private_contract.py
git commit -m "feat: freeze v0.77 private event contract"
```

### Task 2: Implement canonical request encoding and HMAC signing

**Files:**
- Create: `src/crypto_quant/challenger_replacement_binance_private_protocol.py`
- Create: `tests/test_challenger_replacement_binance_private_protocol.py`
- Create: `src/crypto_quant/fixtures/challenger-replacement-v077/spot-hmac-known-answer.json`
- Create: `src/crypto_quant/fixtures/challenger-replacement-v077/futures-request-known-answers.json`

**Interfaces:**
- Consumes:
  `require_binance_private_endpoint(endpoint_id: str) -> tuple[str, str, str, bool]`
  from Task 1; callers cannot supply host, method or path directly.
- Produces:

```python
@dataclass(frozen=True)
class BinancePrivateRequest:
    request_id: str
    endpoint_id: str
    host: str
    method: str
    path: str
    encoded_parameters: bytes
    parameter_names: tuple[str, ...]
    mutating: bool

def build_binance_private_request(endpoint_id: str, parameters: Mapping[str, str],
                                  *, timestamp_ms: int) -> BinancePrivateRequest
def compute_binance_hmac_sha256(payload: bytes, hmac_key: bytes) -> str
def sign_binance_private_request(request: BinancePrivateRequest,
                                 hmac_secret: bytes) -> str
def validate_binance_request_time(*, timestamp_ms: int,
                                  server_time_ms: int) -> int
def classify_binance_private_response(request: BinancePrivateRequest, *,
                                      status: int, body: bytes,
                                      headers: Mapping[str, str]) -> Mapping[str, object]
```

- [ ] **Step 1: Write signing, timing and allowlist RED tests**

Cover the official Spot HMAC known answer, percent encoding, duplicate keys,
non-string values, sorted deterministic order, exact `recvWindow=5000`, ±server
skew, 36-character client IDs, size bounds and every forbidden host/path/method.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src:tests python3 -m unittest tests.test_challenger_replacement_binance_private_protocol -v
```

- [ ] **Step 3: Implement pure protocol code**

Use `urllib.parse.urlencode(..., quote_via=quote)` and
`hmac.new(secret, encoded_parameters, hashlib.sha256).hexdigest()`. Never retain
the secret/signature in the dataclass or diagnostic mapping. Classify a mutating
`-1007`, timeout, disconnect, malformed `2xx` or `5xx` as `UNKNOWN`.

- [ ] **Step 4: Run focused tests and static secret scan**

```bash
PYTHONPATH=src:tests python3 -m unittest tests.test_challenger_replacement_binance_private_protocol -v
! rg -n 'api_secret|secretKey|X-MBX-APIKEY.*=' src/crypto_quant/challenger_replacement_binance_private_protocol.py
```

- [ ] **Step 5: Commit**

```bash
git add src/crypto_quant/challenger_replacement_binance_private_protocol.py \
  src/crypto_quant/fixtures/challenger-replacement-v077 \
  tests/test_challenger_replacement_binance_private_protocol.py
git commit -m "feat: sign fixed Binance private requests"
```

### Task 3: Implement owner-only credential capability

**Files:**
- Create: `src/crypto_quant/challenger_replacement_binance_credential.py`
- Create: `src/crypto_quant/schemas/challenger-replacement-binance-credential-reference-v1.schema.json`
- Create: `tests/test_challenger_replacement_binance_credential.py`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class BinanceCredentialIdentity:
    device: int
    inode: int
    owner_uid: int
    file_sha256: str
    key_fingerprint: str

class BinanceCredentialCapability:
    identity: BinanceCredentialIdentity
    def authorize(self, request: BinancePrivateRequest) -> "BinanceAuthorization"
    def close(self) -> None

class BinanceAuthorization:
    def close(self) -> None

def open_binance_credential_capability(*,
    reference: Mapping[str, object], expected_owner_uid: int
) -> BinanceCredentialCapability
```

- [ ] **Step 1: Write filesystem and disclosure RED tests**

Test symlink/hardlink/FIFO/socket/directory, wrong owner/mode/nlink, parent
rename, file replacement before/after read, over-size JSON, duplicate keys,
close failure, `repr`, exception and serialization. External sentinel bytes,
mode, size, inode, nlink, mtime_ns and ctime_ns must not change.

- [ ] **Step 2: Run RED in owner-only temporary directories**

```bash
PYTHONPATH=src:tests python3 -m unittest tests.test_challenger_replacement_binance_credential -v
```

- [ ] **Step 3: Implement retained-descriptor capability**

Require `O_NOFOLLOW`, `O_DIRECTORY`, `O_NONBLOCK`, regular file, UID, mode
`0600`, nlink 1 and 1..8192 bytes before bounded read. Missing platform flags
return `BINANCE_CREDENTIAL_PLATFORM_UNSUPPORTED`; no zero-flag fallback.
`authorize()` returns a one-use context-managed `BinanceAuthorization` with a
redacted `repr`; only the fixed Task 4 transport may consume its API-key header
and signed parameter bytearrays. Closing attempts to overwrite those mutable
bytearrays before releasing references. Tests must prove the public capability
does not expose key or signature strings through attributes, return values,
serialization, diagnostics or exceptions. The documentation must remain
honest that CPython cannot guarantee erasure of every immutable/interpreter
copy, so this is exposure minimization rather than a memory-secrecy claim.

- [ ] **Step 4: Run credential/protocol tests and descriptor audit**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_binance_credential \
  tests.test_challenger_replacement_binance_private_protocol -v
```

- [ ] **Step 5: Commit**

```bash
git add src/crypto_quant/challenger_replacement_binance_credential.py \
  src/crypto_quant/schemas/challenger-replacement-binance-credential-reference-v1.schema.json \
  tests/test_challenger_replacement_binance_credential.py
git commit -m "feat: retain Binance credential capability"
```

### Task 4: Implement disabled fixed-host transport

**Files:**
- Create: `src/crypto_quant/challenger_replacement_binance_private_transport.py`
- Create: `tests/test_challenger_replacement_binance_private_transport.py`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class BinancePrivateTransportResult:
    response_class: str
    status_or_null: Optional[int]
    body: bytes
    response_sha256: str
    rate_limit_headers: tuple[tuple[str, str], ...]

def execute_binance_private_request(request: BinancePrivateRequest, *,
    credential: BinanceCredentialCapability,
    activation: BinancePrivateActivation,
    expected_build_identity: Mapping[str, str],
    now: str) -> BinancePrivateTransportResult
```

`expected_build_identity` and `now` are mandatory authority inputs: without
them the transport could not independently reject a wrong-build or expired
activation before credential authorization and socket construction.

- [ ] **Step 1: Write no-authority and HTTP boundary RED tests**

Prove missing/fixture/expired/wrong-build activation rejects before credential
sign or socket open. Patch `http.client.HTTPSConnection` for fixed responses and
test redirect, proxy env, TLS failure, oversized body, bad JSON, `418`, `429`,
`5xx`, timeout before/after send and close failure.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src:tests python3 -m unittest tests.test_challenger_replacement_binance_private_transport -v
```

- [ ] **Step 3: Implement fixed-host transport**

Build connections only from the endpoint enum. Ignore proxy environment by not
using URL opener APIs. Use a strict SSL default context, no redirects, bounded
timeouts and ≤1 MiB response. Never automatically repeat a mutating call.

- [ ] **Step 4: Run protocol/credential/transport tests**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_binance_private_protocol \
  tests.test_challenger_replacement_binance_credential \
  tests.test_challenger_replacement_binance_private_transport -v
```

- [ ] **Step 5: Commit**

```bash
git add src/crypto_quant/challenger_replacement_binance_private_transport.py \
  tests/test_challenger_replacement_binance_private_transport.py
git commit -m "feat: execute fixed Binance private requests"
```

### Task 5: Implement strict read-only account preflight

**Files:**
- Create: `src/crypto_quant/challenger_replacement_binance_preflight.py`
- Create: `src/crypto_quant/schemas/challenger-replacement-binance-account-preflight-v1.schema.json`
- Create: `tests/test_challenger_replacement_binance_preflight.py`
- Create: `src/crypto_quant/fixtures/challenger-replacement-v077/account-preflight-flat.json`

**Interfaces:**
- Produces:

```python
def evaluate_binance_account_preflight(*,
    responses: Mapping[str, bytes], account_approval: BinanceAccountApproval,
    credential_identity: BinanceCredentialIdentity,
    build_identity: Mapping[str, str], now: str) -> bytes
def load_binance_account_preflight_bytes(data: bytes, *,
    build_identity: Mapping[str, str]) -> Mapping[str, object]
```

The secret-free credential identity is mandatory so the evaluator can compare
the actually opened key fingerprint to the accountable owner approval. Binance
only exposes the `ipRestrict` boolean; the exact reviewed egress IP remains an
explicit governance attestation and is not misrepresented as a machine-proven
allowlist entry.

- [ ] **Step 1: Write strict preflight RED tests**

Require withdrawal false, IP restriction true, approved trade permissions,
unlocked account, one-way, single-asset, isolated ETHUSDT, leverage 1 or 2,
zero ETH Spot borrow, zero positions/open orders/algo orders and exact account
approval key fingerprint/egress-IP attestation. Missing/extra fields fail.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src:tests python3 -m unittest tests.test_challenger_replacement_binance_preflight -v
```

- [ ] **Step 3: Implement a pure evaluator and strict loader**

Do not add network calls here. Map every rejected invariant to a fixed reason
code. Output canonical JSON with request/order/fund/state counters all zero.

- [ ] **Step 4: Run focused and v0.75 governance regressions**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_binance_preflight \
  tests.test_challenger_replacement_accelerated_canary_plan -v
```

- [ ] **Step 5: Commit**

```bash
git add src/crypto_quant/challenger_replacement_binance_preflight.py \
  src/crypto_quant/schemas/challenger-replacement-binance-account-preflight-v1.schema.json \
  src/crypto_quant/fixtures/challenger-replacement-v077/account-preflight-flat.json \
  tests/test_challenger_replacement_binance_preflight.py
git commit -m "feat: evaluate Binance account preflight"
```

### Task 6: Implement Spot and Futures order lifecycles

**Files:**
- Create: `src/crypto_quant/challenger_replacement_binance_private_lifecycle.py`
- Create: `tests/test_challenger_replacement_binance_private_lifecycle.py`
- Modify: `src/crypto_quant/schemas/challenger-replacement-binance-private-event-v1.schema.json`
- Create: fixed ACK/partial/fill/cancel/UNKNOWN fixtures under the v0.77 fixture root.

**Interfaces:**
- Produces:

```python
def derive_binance_client_order_id(*, plan_hash: str, block_id: str,
    intent_id: str, attempt_ordinal: int, product: str) -> str
def prepare_binance_order_attempt(*, intent: Mapping[str, object],
    projection: Mapping[str, object], preflight: Mapping[str, object],
    activation: BinancePrivateActivation) -> Mapping[str, object]
def apply_binance_order_observation(*, attempt: Mapping[str, object],
    order: bytes, trades: tuple[bytes, ...], account: bytes) -> tuple[Mapping[str, object], ...]
```

- [ ] **Step 1: Write lifecycle RED tests**

Cover Spot BUY/SELL and Futures SELL/BUY-reduce-only; exact 36-character ID;
query-before-send; ACK, reject, partial, cancel/fill race, late fill, duplicate
fill, overfill, `UNKNOWN`; mutual exclusion; no blind resend; and v0.72 internal
identity mapping.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src:tests python3 -m unittest tests.test_challenger_replacement_binance_private_lifecycle -v
```

- [ ] **Step 3: Implement minimum product-specific lifecycle**

Reuse v0.72 Decimal/accounting helpers; do not import or wrap its fixture event
names as venue facts. Preserve full intent ID in the event while transmitting
only the short venue ID.

- [ ] **Step 4: Run v0.71/v0.72 and private lifecycle tests**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_binance_simulation_input \
  tests.test_challenger_replacement_binance_lifecycle \
  tests.test_challenger_replacement_binance_private_lifecycle -v
```

- [ ] **Step 5: Commit**

```bash
git add src/crypto_quant/challenger_replacement_binance_private_lifecycle.py \
  src/crypto_quant/fixtures/challenger-replacement-v077 \
  tests/test_challenger_replacement_binance_private_lifecycle.py
git commit -m "feat: normalize Binance private order lifecycle"
```

### Task 7: Implement Algo protective-stop lifecycle

**Files:**
- Modify: `src/crypto_quant/challenger_replacement_binance_private_lifecycle.py`
- Modify: `src/crypto_quant/schemas/challenger-replacement-binance-private-event-v1.schema.json`
- Create: `tests/test_challenger_replacement_binance_protective_stop.py`

**Interfaces:**
- Produces:

```python
def prepare_binance_protective_stop(*, short_quantity: str,
    trigger_price: str, intent_identity: Mapping[str, str]) -> Mapping[str, str]
def reconcile_binance_protective_stop(*, position: bytes,
    algo_order: bytes, expected: Mapping[str, str]) -> Mapping[str, object]
```

- [ ] **Step 1: Write stop RED tests**

Require `CONDITIONAL`, `STOP_MARKET`, BUY, BOTH, MARK_PRICE, exact quantity,
`reduceOnly=true`, `closePosition=false`, clientAlgoId length 36. Test partial
entry, create-new/query-new/cancel-old no-gap replacement, rejection, lost ACK,
wrong quantity/side/trigger, canceled/missing stop while exposed and flat cleanup.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src:tests python3 -m unittest tests.test_challenger_replacement_binance_protective_stop -v
```

- [ ] **Step 3: Implement stop event branch**

Append `BINANCE_STOP_INTENT_AUTHORIZED`, `BINANCE_STOP_ABSENCE_CHECKED`,
`BINANCE_STOP_SIGNED_REQUEST_PREPARED`,
`BINANCE_STOP_REQUEST_SEND_STARTED`, `BINANCE_STOP_ACKNOWLEDGED`,
`BINANCE_STOP_RECONCILED`, `BINANCE_STOP_REPLACEMENT_STARTED` and terminal
replacement events. Crash tests cover every boundary: before send-start an
exact prepared request may resume; at or after send-start only clientAlgoId
query is allowed and create is never resent. Never mark exposure healthy
between fill and confirmed stop.

- [ ] **Step 4: Run lifecycle/stop tests**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_binance_private_lifecycle \
  tests.test_challenger_replacement_binance_protective_stop -v
```

- [ ] **Step 5: Commit**

```bash
git add src/crypto_quant/challenger_replacement_binance_private_lifecycle.py \
  src/crypto_quant/schemas/challenger-replacement-binance-private-event-v1.schema.json \
  tests/test_challenger_replacement_binance_protective_stop.py
git commit -m "feat: reconcile Binance protective stops"
```

### Task 8: Implement three-way reconciliation and replay

**Files:**
- Create: `src/crypto_quant/challenger_replacement_binance_reconciliation.py`
- Create: `tests/test_challenger_replacement_binance_reconciliation.py`
- Modify: `src/crypto_quant/challenger_replacement_economic_evaluation.py`
- Modify: `src/crypto_quant/schemas/challenger-replacement-binance-private-event-v1.schema.json`

**Interfaces:**
- Produces:

```python
def reconcile_binance_private_state(*, event_projection: Mapping[str, object],
    order_documents: tuple[bytes, ...], trade_documents: tuple[bytes, ...],
    account_document: bytes, position_document: bytes,
    income_documents: tuple[bytes, ...], algo_documents: tuple[bytes, ...]) -> bytes
def load_binance_reconciliation_bytes(data: bytes) -> Mapping[str, object]
def run_challenger_replacement_binance_private_intent(*,
    state: ChallengerReplacementOpportunityState,
    event_root: ChallengerReplacementEventRoot,
    intent: Mapping[str, object],
    preflight: Mapping[str, object],
    activation: BinancePrivateActivation,
    credential: BinanceCredentialCapability,
    build_identity: Mapping[str, str],
) -> Mapping[str, object]
```

- [ ] **Step 1: Write reconciliation/replay RED tests**

Test exact agreement, same fill replay, conflicting fill, fee/funding
duplication, position/balance/open-order mismatch, same bytes/different artifact
identity, process kill after send/ACK/fill/stop/reconciliation and fresh-process
replay. Economic results must remain byte-identical when valid private events are
added and must reject malformed private events.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src:tests python3 -m unittest tests.test_challenger_replacement_binance_reconciliation -v
```

- [ ] **Step 3: Implement pure Decimal reducers and economic filtering**

Use three distinct reducer return types for event, venue and ledger projections.
Require exact equality after normalization. The economic evaluator may skip
only private events that pass the v0.77 private-event schema and parent chain.
The orchestration entry point performs fresh replay before every transition and
appends with that projection's expected-last-event hash. It uses only the fixed
Task 4 transport and returns only after terminal reconciliation. Sequence
conflict is surfaced unchanged to the caller: the runtime never silently
rebases, retries a mutation or sends again.

- [ ] **Step 4: Run reconciliation/economic tests**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_binance_reconciliation \
  tests.test_challenger_replacement_economic_evaluation \
  tests.test_challenger_replacement_economic_evaluation_cli -v
```

- [ ] **Step 5: Commit**

```bash
git add src/crypto_quant/challenger_replacement_binance_reconciliation.py \
  src/crypto_quant/challenger_replacement_economic_evaluation.py \
  tests/test_challenger_replacement_binance_reconciliation.py
git commit -m "feat: reconcile Binance venue and local evidence"
```

### Task 9: Implement ceremony and Canary stage controllers

**Files:**
- Create: `src/crypto_quant/challenger_replacement_canary_controller.py`
- Create: `src/crypto_quant/schemas/challenger-replacement-canary-projection-v1.schema.json`
- Create: `tests/test_challenger_replacement_canary_controller.py`
- Modify: `src/crypto_quant/schemas/challenger-replacement-binance-private-event-v1.schema.json`

**Interfaces:**
- Produces:

```python
def project_challenger_replacement_canary(*, events: tuple[object, ...],
    plan: Mapping[str, object], now: str) -> bytes
def load_challenger_replacement_canary_projection_bytes(data: bytes,
    *, plan: Mapping[str, object]) -> Mapping[str, object]
```

- [ ] **Step 1: Write ceremony/stage RED tests**

Cover all ten ceremony states, minimum venue amount, final flatness, evidence
exclusion, immutable failed block/new approved block, E0/E1/E2 limits, UTC daily
loss, high-water drawdown, restart, product switch, cycle/duration counts,
Spot/perpetual cycle requirements and no automatic promotion.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src:tests python3 -m unittest tests.test_challenger_replacement_canary_controller -v
```

- [ ] **Step 3: Implement pure projection**

Return one of the exact v0.75 states and one of the four hard-stop classes.
Recoverable flat conditions extend/restart the proper block without erasing
events. Refuse any promotion without an exact next-stage approval identity.

- [ ] **Step 4: Run controller/governance/qualification tests**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_canary_controller \
  tests.test_challenger_replacement_accelerated_canary_plan \
  tests.test_challenger_replacement_operational_qualification -v
```

- [ ] **Step 5: Commit**

```bash
git add src/crypto_quant/challenger_replacement_canary_controller.py \
  src/crypto_quant/schemas/challenger-replacement-canary-projection-v1.schema.json \
  tests/test_challenger_replacement_canary_controller.py
git commit -m "feat: project ceremony and Canary stages"
```

### Task 10: Integrate read-only operations, alerts and disabled delivery

**Files:**
- Modify: `src/crypto_quant/operations_projection_v3.py`
- Modify: `src/crypto_quant/operations_alerts.py`
- Modify: `src/crypto_quant/dashboard/app.js`
- Create: `config/challenger-replacement-binance-v1.example.json`
- Create: `config/local.crypto-quant.challenger-replacement-binance-v1.plist.example`
- Create: `docs/runbooks/binance-private-preflight-v0.77.md`
- Create: `docs/runbooks/binance-order-unknown-v0.77.md`
- Create: `docs/runbooks/binance-safe-flatten-v0.77.md`
- Create: `docs/runbooks/binance-secret-incident-v0.77.md`
- Create: `tests/test_challenger_replacement_binance_delivery.py`

**Interfaces:**
- Consumes: strict reconciliation and Canary projections.
- Produces: no new write API; read-only projection fields and deterministic
  alerts.

- [ ] **Step 1: Write UI/alert/template RED tests**

Assert unresolved UNKNOWN, position mismatch, missing stop, daily stop and
drawdown alerts. Assert loopback-only/no write route/no control button/no secret
field/no remote asset. Assert examples contain `production_activation=false`
and no real path/key/account value.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src:tests python3 -m unittest tests.test_challenger_replacement_binance_delivery -v
```

- [ ] **Step 3: Implement minimum projection and runbooks**

Extend existing v3 projection rather than create a new server. Runbooks use
fixed decision trees and never tell operators to guess state, delete evidence,
resend UNKNOWN orders or disable protection.

- [ ] **Step 4: Run operations adjacency**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_binance_delivery \
  tests.test_operations_projection_v3 \
  tests.test_operations_alerts \
  tests.test_operations_dashboard -v
```

- [ ] **Step 5: Commit**

```bash
git add src/crypto_quant/operations_projection_v3.py \
  src/crypto_quant/operations_alerts.py src/crypto_quant/dashboard/app.js \
  config/challenger-replacement-binance-v1.example.json \
  config/local.crypto-quant.challenger-replacement-binance-v1.plist.example \
  docs/runbooks/binance-*-v0.77.md \
  tests/test_challenger_replacement_binance_delivery.py
git commit -m "feat: expose read-only Binance canary health"
```

### Task 11: Execute the fixed offline fault matrix once

**Files:**
- Create: `src/crypto_quant/challenger_replacement_private_fault_matrix.py`
- Create: `src/crypto_quant/schemas/challenger-replacement-private-fault-receipt-v1.schema.json`
- Create: `tests/test_challenger_replacement_private_fault_matrix.py`
- Create at freeze: `artifacts/challenger-replacement/challenger-replacement-private-fault-matrix-v0.77.0.json`

**Interfaces:**
- Produces:

```python
def run_challenger_replacement_private_fault_matrix(*,
    build_identity: Mapping[str, str]) -> Mapping[str, object]
def load_challenger_replacement_private_fault_matrix_bytes(data: bytes, *,
    build_identity: Mapping[str, str]) -> Mapping[str, object]
```

- [ ] **Step 1: Freeze exact case IDs and write RED tests**

Encode every case from spec section 10. Require unique ordered IDs, fixture and
result hashes, fresh-process cases, all pass booleans and zero authority
counters. Altered/reordered/missing cases fail strict loading.

- [ ] **Step 2: Run RED then implement pure fixed runner**

```bash
PYTHONPATH=src:tests python3 -m unittest tests.test_challenger_replacement_private_fault_matrix -v
```

Patch only private low-level boundaries in tests/runner. Do not expose a
production fault callback, enum, command, environment flag or arbitrary path.

- [ ] **Step 3: Obtain one complete independent code/spec review**

Review exact v0.76 base, v0.77 spec/plan and Tasks 1-10 diff. Critical and
Important must be zero. Fix each valid finding with targeted RED/GREEN and ask
only for targeted re-review.

- [ ] **Step 4: Freeze executable identity and run campaign once**

Commit the final executable code checkpoint. Enumerate exact runtime paths,
compute per-file hashes and aggregate hash, build the campaign twice in memory
for byte equality, execute it once, serialize canonical JSON with no trailing
LF and strict-load/replay it. Any runtime/schema/fixture change invalidates the
receipt and returns to this step.

- [ ] **Step 5: Commit immutable receipt**

```bash
git add src/crypto_quant/challenger_replacement_private_fault_matrix.py \
  src/crypto_quant/schemas/challenger-replacement-private-fault-receipt-v1.schema.json \
  tests/test_challenger_replacement_private_fault_matrix.py \
  artifacts/challenger-replacement/challenger-replacement-private-fault-matrix-v0.77.0.json
git commit -m "test: freeze v0.77 private fault evidence"
```

### Task 12: Produce dossier, verify and publish v0.77

**Files:**
- Create: `docs/adr/0077-binance-private-canary-bundle.md`
- Create: `docs/implementation-status-v0.77.0.md`
- Create: `docs/v1-code-complete-not-activated-dossier.md`
- Create: `tests/test_challenger_replacement_v077_release.py`
- Modify: `README.md`, version files, `src/crypto_quant/build.py`, manifest
  refresher and `config/evaluator-build-manifest-v1.json`.

- [ ] **Step 1: Write release/dossier RED tests**

Require every v0.75-v0.77 requirement to map to exact code/test/artifact; exact
v0.76 released identity; package/manifest versions; fault receipt binding;
≤3,000 new production lines; secret/endpoint/static authority scans; and the
exact non-activation conclusion.

- [ ] **Step 2: Write ADR/status/dossier and refresh manifest once**

The dossier must explicitly list installation, start, credential, IP/account
binding, configuration, funding, Spot ceremony, Futures ceremony, E0, E1, E2
and incident unlock as still external. It must say no 72-hour/90-day clock and
no profitability/AI conclusion.

- [ ] **Step 3: Run focused and adjacent verification**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_binance_private_contract \
  tests.test_challenger_replacement_binance_private_protocol \
  tests.test_challenger_replacement_binance_credential \
  tests.test_challenger_replacement_binance_private_transport \
  tests.test_challenger_replacement_binance_preflight \
  tests.test_challenger_replacement_binance_private_lifecycle \
  tests.test_challenger_replacement_binance_protective_stop \
  tests.test_challenger_replacement_binance_reconciliation \
  tests.test_challenger_replacement_canary_controller \
  tests.test_challenger_replacement_binance_delivery \
  tests.test_challenger_replacement_private_fault_matrix \
  tests.test_challenger_replacement_v077_release -v
```

- [ ] **Step 4: Run the one final local release gate**

```bash
PYTHONPATH=src:tests python3 -m unittest discover -s tests
python3 -m compileall -q src tests
make validate
git diff --check
git status --short
```

Expected: all suites green; release validation retains production-disabled
policy; only exact release files remain before commit.

- [ ] **Step 5: Final independent review and release commit**

Request one final read-only release review if release-only files add claims not
covered by the Task 11 review. Fix Critical/Important with targeted tests; do not
repeat the unchanged full suite. Commit the clean candidate as
`release: freeze v0.77 code-complete evidence`.

- [ ] **Step 6: Publish only after v0.76 and Actions gates are green**

Read-only verify public repository, ADMIN permission, origin/main and exact
annotated `v0.76.0`. Push branch, create Draft PR, wait for Python 3.9, Python
3.12 and macOS arm64 PR CI, merge exact reviewed head, wait for main CI, create
annotated `v0.77.0`, push and verify:

```bash
test "$(git rev-parse origin/main)" = "$(git rev-parse v0.77.0^{})"
test "$(git cat-file -t v0.77.0)" = tag
git status --short
```

If CI quota, permission, loader, manifest or identity is not green, keep the
candidate unpublished. Never replace remote CI with a local claim.

---

## Completion Checklist

- [ ] Every design section 1-14 maps to a task and an executable test.
- [ ] No generic exchange/broker/storage/UI surface or third-party runtime was added.
- [ ] Exact endpoint inventory and 36-character ID contract are enforced.
- [ ] Credential/signed data never appears in durable evidence or diagnostics.
- [ ] UNKNOWN, position mismatch, missing stop and post-limit risk are hard stops.
- [ ] Ceremony and stage state machines exactly preserve v0.75.
- [ ] v0.74 90-day economics is unchanged by private operational events.
- [ ] Fault matrix and dossier bind the exact released runtime.
- [ ] v0.76 and v0.77 PR/main/tag identities are all green and exact.
- [ ] No installation, credential/account request, order, funds or timers occurred.
- [ ] Final claim is only `CODE_COMPLETE_NOT_ACTIVATED`.
