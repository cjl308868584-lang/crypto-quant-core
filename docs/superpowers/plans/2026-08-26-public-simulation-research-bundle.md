# v0.76 Public Simulation and Research Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Release a credential-free, deterministic public-market replacement
simulation, its four-hour event runtime candidate, 72-hour operational
qualifier, final v0.74 90-day evaluator and operations-projection-v3 without
installing or starting anything.

**Architecture:** Compose a strict `PublicMarketCaptureV2` over the released
v0.67 clock/Kline capture and six fixed public Binance endpoints, then feed a
public-only profile of the v0.71 Decimal kernel into the v0.70 append-only
DecisionOpportunity log. Pure operational/economic evaluators and a v3
projection read that one fact source; deployment, start-receipt and CLI code are
candidate-only and execute no production ceremony in this release.

**Tech Stack:** Python 3.9/3.12 standard library, `urllib`, `Decimal`, frozen
dataclasses, repository canonical JSON/hash/event capabilities, JSON Schema
Draft 2020-12, `unittest`, multiprocessing/subprocess, launchd plist rendering,
existing loopback HTML/CSS/JavaScript console and GitHub Actions.

**Spec:**
`docs/superpowers/specs/2026-08-26-public-simulation-research-bundle-design.md`

## Global Constraints

- Base is public v0.75.0 peeled commit
  `a51ed15d5a484e5bb9a54dc75a7fef4e8876e4d5`; this branch already carries only
  the approved v0.76 spec commits.
- Exact release claim is
  `PUBLIC_SIMULATION_AND_RESEARCH_CODE_RELEASED_NOT_ACTIVATED`.
- `production_activation=false`, `runtime_install_authorized=false`,
  `replacement_start_authorized=false`, `credentials_allowed=false`,
  `account_requests_allowed=false`, `broker_requests_allowed=false`,
  `real_orders_allowed=false`, `fund_movement_allowed=false`,
  `ceremony_authorized=false` and `e0_activation_authorized=false` throughout.
- Release work performs zero public/private market requests, zero credential or
  account reads, zero Broker/order/fund actions and zero production-root writes;
  all capture tests use exact response fixtures and patched transports.
- The append-only canonical DecisionOpportunity event log is the sole fact
  source. Results, projections, exports, receipts and the dashboard are
  derivatives and have no append authority.
- Released v0.67 and v0.71/v0.72 public APIs and committed fixture bytes retain
  exact behavior. Fixture labels never qualify as public-market evidence.
- Public APIs accept no URL, symbol, price, fee, funding, slippage, position,
  timestamp, seed, threshold, result status, path-selection or fault callback.
- New JSON rejects duplicate keys, binary float, noncanonical bytes, unknown
  keys, unsafe integers and over-size input; semantic loaders rebuild hashes,
  IDs, plan/build bindings and derived fields.
- Every feature/fix is exact RED, minimal GREEN, focused verification and one
  atomic commit. Do not run the unchanged full suite twice.
- Net new production Python across v0.76 modules is at most the revised 5,000
  physical-line hard cap, with 2,324 lines measured after Task 7 and remaining
  task allowances fixed by the approved design section 13;
  no generic exchange, Broker, scheduler, storage, evaluator or second UI
  framework is added.
- No install, bootstrap, kickstart, Runner start, production receipt, 72-hour
  timer, 90-day timer, credential, order or Canary action is permitted.

## File Structure

### Shared public capture

- `src/crypto_quant/challenger_replacement_public_http.py`: moved, narrow
  request/response/attempt primitives shared by v0.67 and v0.76; no business URL
  selection.
- `src/crypto_quant/challenger_replacement_public_market_capture.py`: fixed
  request identities, acquisition orchestration, exact-body ledger,
  normalization and strict `PublicMarketCaptureV2` loader.
- `src/crypto_quant/schemas/challenger-replacement-public-market-capture-v2.schema.json`:
  exact composite-capture document.

### Public simulation

- `src/crypto_quant/challenger_replacement_public_simulation_contract.py`:
  immutable public contract derived from exact v0.71/v0.74 constants.
- `src/crypto_quant/challenger_replacement_public_simulation.py`: strict public
  input/snapshot/result types and fixed public profile over the evidence-neutral
  Decimal kernel.
- `src/crypto_quant/schemas/challenger-replacement-public-simulation-{contract,input,snapshot,result}-v1.schema.json`:
  fixture-free exact documents.

### Runtime and trust chain

- `src/crypto_quant/challenger_replacement_v3_runtime.py`: one natural
  opportunity composition and recovery; no scheduler or callback seam.
- `src/crypto_quant/challenger_replacement_v3_deployment.py`: v0.76 inventory,
  plist and fixed owner-only candidate paths.
- `src/crypto_quant/challenger_replacement_v3_start.py`: pure dual-clock start
  receipt builder/loader; no publisher or launchctl mutation.
- `src/crypto_quant/schemas/challenger-replacement-v3-{deployment,start-receipt}-v1.schema.json`.

### Evaluation and operations

- `src/crypto_quant/challenger_replacement_fault_matrix.py`: exact offline case
  runner and strict receipt.
- `src/crypto_quant/challenger_replacement_operational_qualification.py`: pure
  continuous-72-hour segment evaluator.
- `src/crypto_quant/challenger_replacement_economic_evaluation.py`: tail-blind
  progress plus the final v0.74 Decimal/bootstrap evaluator and strict result.
- `src/crypto_quant/challenger_replacement_economic_evaluation_cli.py`: fixed
  future production paths, pre-tail refusal, no business arguments.
- `src/crypto_quant/challenger_replacement_v3_observer.py`: one-pass read-only
  typed fact reduction.
- `src/crypto_quant/operations_projection_v3.py`: strict read-only projection.
- Matching package Schemas and tests named after each module.
- `operations_alerts.py`, dashboard assets/tests: strict v3 dispatch only;
  existing HTTP routes and loopback binding remain unchanged.

---

### Task 1: Extract the shared bounded public HTTP boundary

**Files:**
- Create: `src/crypto_quant/challenger_replacement_public_http.py`
- Modify: `src/crypto_quant/challenger_replacement_live_input.py`
- Modify: `tests/test_challenger_replacement_live_input.py`
- Create: `tests/test_challenger_replacement_public_http.py`

**Interfaces:**
- Produces: internal `PublicHttpResponse`,
  `open_fixed_public_request(request: Request, *, max_body_bytes: int)`,
  `attempt_document(response, sequence)` and
  `transport_failure_attempt(sequence, started, received)`.
- Consumes: only an already constructed `urllib.request.Request`; it never
  constructs or selects a URL.
- Preserves: `acquire_challenger_replacement_live_capture` and
  `load_challenger_replacement_live_capture_bytes` output bytes and reason
  codes for every existing v0.67 fixture.

- [ ] **Step 1: Write characterization and capability RED tests**

Add a byte-for-byte fixture test around one success, two transient responses
then success, redirect, wrong content type, over-size body and transport error.
Add this AST/capability assertion:

```python
def test_shared_http_has_no_business_endpoint_or_credential_surface(self):
    source = PUBLIC_HTTP.read_text(encoding="utf-8")
    self.assertNotIn("binance.com", source)
    self.assertNotIn("APIKEY", source.upper())
    signature = inspect.signature(open_fixed_public_request)
    self.assertEqual(tuple(signature.parameters), ("request", "max_body_bytes"))
```

Patch `urlopen`, wall clock, monotonic clock and sleep; require HTTPS-only,
redirect rejection, fixed user-agent/accept headers, monotonic RTT, at most
`max_body_bytes + 1` read, status/final-URL/header capture and fixed exception
mapping. These tests are RED because the shared module does not exist.

- [ ] **Step 2: Run the focused RED**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_public_http \
  tests.test_challenger_replacement_live_input -v
```

Expected: import failure for `challenger_replacement_public_http`; all existing
v0.67 tests remain unchanged.

- [ ] **Step 3: Move only the reviewed transport primitives**

Implement the exact narrow shape:

```python
@dataclass(frozen=True)
class PublicHttpResponse:
    status: int
    final_url: str
    headers: Mapping[str, str]
    body: bytes
    monotonic_rtt_ms: int
    request_started_at: str
    response_received_at: str

def open_fixed_public_request(request, *, max_body_bytes):
    if not isinstance(max_body_bytes, int) or isinstance(max_body_bytes, bool):
        raise PublicHttpError("PUBLIC_HTTP_LIMIT_INVALID")
    # Reuse the released HTTPS, redirect, timeout, header, bounded-read,
    # monotonic and fixed-error behavior moved from live_input verbatim.
```

Keep retry selection and business URL construction in the domain modules.
Replace v0.67 private implementations with imports; do not change its Schema,
constants, output construction or retry policy.

- [ ] **Step 4: Run GREEN and exact v0.67 adjacency**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_public_http \
  tests.test_challenger_replacement_live_input \
  tests.test_challenger_replacement_live_runtime \
  tests.test_challenger_replacement_v067_safety -v
python3 -m compileall -q \
  src/crypto_quant/challenger_replacement_public_http.py \
  src/crypto_quant/challenger_replacement_live_input.py
git diff --check
```

Expected: all pass; captured canonical bytes and reason codes are unchanged.

- [ ] **Step 5: Commit**

```bash
git add src/crypto_quant/challenger_replacement_public_http.py \
  src/crypto_quant/challenger_replacement_live_input.py \
  tests/test_challenger_replacement_public_http.py \
  tests/test_challenger_replacement_live_input.py
git commit -m "refactor: share bounded public market transport"
```

### Task 2: Freeze and load PublicMarketCaptureV2

**Files:**
- Create: `src/crypto_quant/challenger_replacement_public_market_capture.py`
- Create: `src/crypto_quant/schemas/challenger-replacement-public-market-capture-v2.schema.json`
- Create: `tests/test_challenger_replacement_public_market_capture.py`
- Create: `tests/fixtures/challenger_replacement_v076/public-market-capture.json`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class ChallengerReplacementPublicMarketCapture:
    document: Mapping[str, Any]
    canonical_bytes: bytes

def load_challenger_replacement_public_market_capture_bytes(
    data: bytes,
    *,
    plan: Mapping[str, Any],
    build_identity: Mapping[str, Any],
    previous_source_bundle: Optional[Mapping[str, Any]],
) -> ChallengerReplacementPublicMarketCapture: ...
```

- Consumes: strict nested v0.67 canonical bytes plus six exact top-level
  response ledgers in the frozen request order.
- Produces normalized `bars`, Spot/perpetual `bid`/`ask`, perpetual current
  `mark`, ordered `funding_records` and narrow `simulation_rules`.

- [ ] **Step 1: Write exact Schema and loader RED tests**

Freeze exact top-level keys and reject unknown nested leaves. Build deterministic
fixtures for Spot/Futures exchangeInfo, book tickers, premium index and zero,
one and four funding records. Require the fixed URLs and count range `10..24`.
The core assertion is:

```python
loaded = load_challenger_replacement_public_market_capture_bytes(
    fixture_bytes,
    plan=plan,
    build_identity=build_identity,
    previous_source_bundle=previous_bundle,
)
self.assertEqual(loaded.document["normalized"]["funding_records"], [
    {"funding_time": "2026-08-26T04:00:00.000Z",
     "rate": "-0.0001", "mark": "3310.25"},
])
self.assertNotIn("last", loaded.document["normalized"]["quotes"]["spot"])
```

Mutation tests cover duplicate JSON keys, float/NaN, noncanonical decimals,
wrong URL/query order, response hash/body mismatch, response outside the
trusted window, count mismatch, symbol/status mismatch, bid above ask,
nonpositive mark, all filter-selection branches, conflicting applicable
minimum notionals, funding outside `(scheduled-4h, scheduled]`, duplicate or
unordered funding, `Special` rate, more than 16 records, 1/4 MiB limits, forged
authority and overlap failure.

- [ ] **Step 2: Run the focused RED**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_public_market_capture -v
```

Expected: import/Schema failure.

- [ ] **Step 3: Implement strict normalization and capability grant**

Implement fixed constants for the six URLs, a private capability token, strict
Schema loader and deterministic rules:

```python
def _market_quantity_filter(filters):
    market = _one_filter(filters, "MARKET_LOT_SIZE", allow_absent=True)
    if market is not None and _positive_lot_tuple(market):
        return _lot_tuple(market)
    return _lot_tuple(_one_filter(filters, "LOT_SIZE"))

def _spot_min_notional(filters):
    values = _applicable_spot_min_notionals(filters)
    if not values:
        _invalid("PUBLIC_MARKET_CAPTURE_RULES_INVALID")
    return max(values)
```

Use `load_challenger_replacement_live_capture_bytes` for the nested bytes,
recompute every response and normalized field, and grant the frozen capture
only after canonical byte equality. Never parse an orphan/partial response as
business evidence.

- [ ] **Step 4: Run GREEN and mutation adjacency**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_public_market_capture \
  tests.test_challenger_replacement_live_input \
  tests.test_challenger_replacement_plan_v3 -v
python3 -m compileall -q \
  src/crypto_quant/challenger_replacement_public_market_capture.py
git diff --check
```

- [ ] **Step 5: Commit**

```bash
git add src/crypto_quant/challenger_replacement_public_market_capture.py \
  src/crypto_quant/schemas/challenger-replacement-public-market-capture-v2.schema.json \
  tests/test_challenger_replacement_public_market_capture.py \
  tests/fixtures/challenger_replacement_v076/public-market-capture.json
git commit -m "feat: validate v0.76 public market capture"
```

### Task 3: Acquire the fixed composite capture without a second client

**Files:**
- Modify: `src/crypto_quant/challenger_replacement_public_market_capture.py`
- Modify: `tests/test_challenger_replacement_public_market_capture.py`

**Interfaces:**
- Produces:

```python
def acquire_challenger_replacement_public_market_capture(
    *, state: ChallengerReplacementOpportunityState
) -> ChallengerReplacementPublicMarketCapture: ...
```

- Consumes: `acquire_challenger_replacement_live_capture(state=state)` followed
  by the six fixed endpoints in spec order; no transport/callback parameter.

- [ ] **Step 1: Write acquisition-order and failure RED tests**

Patch only the module-private imported acquisition/open/sleep symbols. Require
the exact call sequence, retry delays, independent maximum of three attempts,
body limits, request count, all attempt bytes and final canonical replay. Prove
that release-time tests execute no real `urlopen`:

```python
with patch("urllib.request.OpenerDirector.open",
           side_effect=AssertionError("network forbidden")):
    capture = acquire_with_fixture_queue(state, exact_responses)
self.assertEqual(capture.document["authority"]["network_request_count"], 10)
```

Require a fixed acquisition error for permanent HTTP status, three transient
failures, transport exhaustion, wrong final URL, clock/window expiry and
invalid success body. No event or production file write occurs.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_public_market_capture.PublicMarketAcquisitionTests -v
```

Expected: missing acquisition function.

- [ ] **Step 3: Implement the six-request orchestrator**

Use a frozen request tuple and the shared Task 1 primitive:

```python
SPOT_EXCHANGE_INFO_URL = (
    "https://data-api.binance.vision/api/v3/exchangeInfo?symbol=ETHUSDT"
)
SPOT_BOOK_TICKER_URL = (
    "https://data-api.binance.vision/api/v3/ticker/bookTicker?symbol=ETHUSDT"
)
FUTURES_EXCHANGE_INFO_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"
FUTURES_BOOK_TICKER_URL = (
    "https://fapi.binance.com/fapi/v1/ticker/bookTicker?symbol=ETHUSDT"
)
FUTURES_PREMIUM_INDEX_URL = (
    "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=ETHUSDT"
)

def funding_url_for(scheduled_ms):
    return (
        "https://fapi.binance.com/fapi/v1/fundingRate?"
        f"endTime={scheduled_ms}&limit=16&"
        f"startTime={scheduled_ms - 14399999}&symbol=ETHUSDT"
    )

_PUBLIC_REQUESTS = (
    ("spot_exchange_info", SPOT_EXCHANGE_INFO_URL, 1024 * 1024),
    ("spot_book_ticker", SPOT_BOOK_TICKER_URL, 1024 * 1024),
    ("perpetual_exchange_info", FUTURES_EXCHANGE_INFO_URL, 4 * 1024 * 1024),
    ("perpetual_book_ticker", FUTURES_BOOK_TICKER_URL, 1024 * 1024),
    ("perpetual_mark", FUTURES_PREMIUM_INDEX_URL, 1024 * 1024),
    ("funding_history", funding_url_for(state.scheduled_for), 1024 * 1024),
)
```

Build attempts, normalize through the same strict loader and return its
capability. Do not add threads, async I/O, WebSocket, cache, fallback host or
historical request mode.

- [ ] **Step 4: Run GREEN and static authority scan**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_public_http \
  tests.test_challenger_replacement_public_market_capture \
  tests.test_challenger_replacement_live_input -v
python3 - <<'PY'
from pathlib import Path
s = Path('src/crypto_quant/challenger_replacement_public_market_capture.py').read_text()
for forbidden in ('X-MBX-APIKEY', 'apiKey', 'secretKey',
                  '/api/v3/order', '/fapi/v1/order'):
    assert forbidden not in s
print('public-capture-authority-scan: PASS')
PY
git diff --check
```

- [ ] **Step 5: Commit**

```bash
git add src/crypto_quant/challenger_replacement_public_market_capture.py \
  tests/test_challenger_replacement_public_market_capture.py
git commit -m "feat: acquire fixed public simulation evidence"
```

### Task 4: Freeze the public contract, input and snapshot boundary

**Files:**
- Create: `src/crypto_quant/challenger_replacement_public_simulation_contract.py`
- Create: `src/crypto_quant/challenger_replacement_public_simulation.py`
- Create: `src/crypto_quant/schemas/challenger-replacement-public-simulation-contract-v1.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-public-simulation-input-v1.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-public-simulation-snapshot-v1.schema.json`
- Create: `tests/test_challenger_replacement_public_simulation_contract.py`
- Create: `tests/test_challenger_replacement_public_simulation.py`

**Interfaces:**
- Produces:

```python
def build_challenger_replacement_public_simulation_contract(
    *, plan: Mapping[str, Any], economic_plan: Mapping[str, Any],
    predecessor_contract: Mapping[str, Any]
) -> Dict[str, Any]: ...

def load_challenger_replacement_public_simulation_contract_bytes(
    data: bytes, *, plan, economic_plan, predecessor_contract
) -> Dict[str, Any]: ...

def build_challenger_replacement_public_simulation_input(
    capture: ChallengerReplacementPublicMarketCapture,
    *, plan, economic_plan, predecessor_contract, public_contract,
    build_identity
) -> Dict[str, Any]: ...

def load_challenger_replacement_public_simulation_input_bytes(
    data: bytes, *, plan, economic_plan, predecessor_contract,
    public_contract, build_identity, opportunity_id
) -> Dict[str, Any]: ...
```

- Consumes: strict Task 2 capture, exact v0.69/v0.74 plans and exact v0.71
  contract bytes/identity.
- Produces: no `last`, fixture label, account/venue fee observation or caller
  override.

- [ ] **Step 1: Write contract/input/snapshot Schema RED tests**

Require exact public labels, predecessor ID/hash/file SHA, v0.74 accounting
policy hash, model multiplier `1`, fee `0.0015`, adverse slippage `0.001`,
50-USDT exposure cap, model cost warnings and all authority false/zero. Require
contract self-hash/stable ID and rebuilt semantic equality.

For public input, require capture hash, normalized bars/quotes/rules/funding,
plan/contract/build/opportunity bindings and exact authority. Prove fixture
contamination fails:

```python
for forbidden in (
    "FIXTURE_ONLY_DETERMINISTIC_BINANCE_SIMULATION",
    "DETERMINISTIC_IMMEDIATE_FULL_MARKET_FIXTURE",
    "CONFIRMED_FIXTURE",
):
    mutated = deepcopy(valid_public_input)
    mutated["public_profile"]["protective_stop_status"] = forbidden
    with self.assertRaises(PublicSimulationError):
        load_public(mutated)
```

Snapshot Schema permits `FLAT`, `SPOT_LONG`, `PERP_SHORT`, verified certainty,
fixed risk states and only `CONFIRMED_SIMULATED` protection while exposed.
Mutation tests change every contract/input/snapshot identity, economic constant,
rule response hash, Decimal, Funding record, authority and label leaf.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_public_simulation_contract \
  tests.test_challenger_replacement_public_simulation -v
```

Expected: imports/Schemas absent.

- [ ] **Step 3: Implement pure builders and strict loaders**

Use parameter-required builders so identities cannot be read from disk. Freeze
the public contract document internally:

```python
PUBLIC_PROFILE = {
    "mode": "PUBLIC_MARKET_DETERMINISTIC_BINANCE_SIMULATION",
    "fill_model": "DETERMINISTIC_IMMEDIATE_FULL_MARKET_MODEL",
    "funding_source": "EXACT_PUBLIC_FUNDING_RECORDS_IN_OPPORTUNITY_INTERVAL",
    "protective_stop_status": "CONFIRMED_SIMULATED",
}
```

Build the narrow simulation rules only from strict capture values plus frozen
model constants. Validate package Schema, canonical bytes, self-hash, stable ID
and equality with a fresh rebuild. Use deep copies at public boundaries; no
path, clock, network or mutable global cache enters these APIs.

- [ ] **Step 4: Run GREEN and predecessor immutability**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_public_simulation_contract \
  tests.test_challenger_replacement_public_simulation \
  tests.test_challenger_replacement_simulation_contract \
  tests.test_challenger_replacement_binance_simulation_input \
  tests.test_challenger_replacement_v072_artifacts -v
python3 -m compileall -q \
  src/crypto_quant/challenger_replacement_public_simulation_contract.py
git diff --check
```

- [ ] **Step 5: Commit**

```bash
git add src/crypto_quant/challenger_replacement_public_simulation_contract.py \
  src/crypto_quant/schemas/challenger-replacement-public-simulation-contract-v1.schema.json \
  src/crypto_quant/schemas/challenger-replacement-public-simulation-input-v1.schema.json \
  src/crypto_quant/schemas/challenger-replacement-public-simulation-snapshot-v1.schema.json \
  tests/test_challenger_replacement_public_simulation_contract.py \
  tests/test_challenger_replacement_public_simulation.py
git commit -m "feat: freeze public simulation contract"
```

### Task 5: Add the evidence-neutral Decimal kernel and public result

**Files:**
- Modify: `src/crypto_quant/challenger_replacement_simulation.py`
- Modify: `tests/test_challenger_replacement_simulation.py`
- Modify: `src/crypto_quant/challenger_replacement_public_simulation.py`
- Modify: `tests/test_challenger_replacement_public_simulation.py`
- Create: `src/crypto_quant/schemas/challenger-replacement-public-simulation-result-v1.schema.json`
- Create: `tests/fixtures/challenger_replacement_v076/public-simulation-golden.json`

**Interfaces:**
- Preserves: `build_challenger_replacement_genesis_snapshot`,
  `compute_challenger_replacement_simulation_decision`,
  `simulate_challenger_replacement_opportunity` and private v0.72 transition
  exact fixture bytes.
- Produces:

```python
def build_challenger_replacement_public_genesis_snapshot(
    *, plan, public_contract
) -> Dict[str, Any]: ...

def simulate_challenger_replacement_public_opportunity(
    *, source, previous_projection, plan, public_contract, build_identity
) -> Dict[str, Any]: ...

def build_challenger_replacement_public_simulation_result(
    *, source, previous_projection, transition, plan, economic_plan,
    public_contract, build_identity, sequence, parent_event_hash
) -> Dict[str, Any]: ...

def load_challenger_replacement_public_simulation_result_bytes(
    data: bytes, *, source, previous_projection, plan, economic_plan,
    public_contract, build_identity, sequence, parent_event_hash
) -> Dict[str, Any]: ...
```

- [ ] **Step 1: Write exact predecessor-byte and public-profile RED tests**

Record every existing v0.71/v0.72 golden input/result hash before refactor and
require unchanged outputs. Add public Spot open/hold/close, perpetual
open/hold/close, reversal flatten-first, stop trigger, min-notional, daily loss,
drawdown, fee, slippage, Funding and fresh-replay tests.

For multiple Funding records, assert exact ordered cashflow:

```python
result = simulate_public(source_with_funding([
    ("2026-08-26T01:00:00.000Z", "0.0001", "3300"),
    ("2026-08-26T03:00:00.000Z", "-0.0002", "3320"),
]), previous_signed_quantity="-0.015", contract_multiplier="1")
self.assertEqual(result["accounting"]["funding_cashflows"], [
    {"amount": "0.00495", "funding_time": "2026-08-26T01:00:00.000Z"},
    {"amount": "-0.00996", "funding_time": "2026-08-26T03:00:00.000Z"},
])
```

These are fixed known answers from
`-signed_quantity * contract_multiplier * mark * rate`: `0.00495` and
`-0.00996`. The fixture freezes signed quantity `-0.015`, multiplier `1`, both
marks and both rates; repository Decimal encoding is applied once to each
cashflow.

Result loader tests recompute decision, risk, simulated intent/fill, fees,
Funding, next snapshot, lifecycle/reconciliation, self-hash and stable ID.
Require `SIMULATED_ORDER_ACCEPTED` and `SIMULATED_FILL_APPLIED`; reject any
event ending in `_FIXTURE`, venue ACK/fill claims, `UNKNOWN`, absent simulated
protection while exposed and any changed source/previous snapshot/event parent.
Require every public result to carry exactly:

```text
PUBLIC_MARKET_DETERMINISTIC_SIMULATION_NO_ACCOUNT_NO_BROKER_NO_REAL_ORDER
```

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_public_simulation -v
```

Expected: public transition/result functions absent.

- [ ] **Step 3: Extract a fixed internal profile boundary**

Refactor only the pure computation internals:

```python
@dataclass(frozen=True)
class _SimulationProfile:
    protective_stop_status: str
    funding_shape: str

_FIXTURE_PROFILE = _SimulationProfile("CONFIRMED_FIXTURE", "SINGLE_BOUNDARY")
_PUBLIC_PROFILE = _SimulationProfile("CONFIRMED_SIMULATED", "ORDERED_INTERVAL")
```

The profile objects are private constants and are never accepted from callers.
Fixture wrappers pass `_FIXTURE_PROFILE`; the new public wrapper passes
`_PUBLIC_PROFILE`. Apply each public Funding record once before decision using
its own mark. Build the public result from recomputed typed values and validate
against the strict Schema.

- [ ] **Step 4: Run GREEN, golden replay and line budget**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_simulation \
  tests.test_challenger_replacement_binance_simulation_input \
  tests.test_challenger_replacement_fixture_simulation \
  tests.test_challenger_replacement_binance_lifecycle \
  tests.test_challenger_replacement_public_simulation \
  tests.test_challenger_replacement_v072_artifacts -v
python3 -m compileall -q \
  src/crypto_quant/challenger_replacement_simulation.py \
  src/crypto_quant/challenger_replacement_public_simulation.py
wc -l src/crypto_quant/challenger_replacement_{public_market_capture,public_simulation_contract,public_simulation}.py
git diff --check
```

- [ ] **Step 5: Commit**

```bash
git add src/crypto_quant/challenger_replacement_simulation.py \
  src/crypto_quant/challenger_replacement_public_simulation.py \
  src/crypto_quant/schemas/challenger-replacement-public-simulation-result-v1.schema.json \
  tests/test_challenger_replacement_simulation.py \
  tests/test_challenger_replacement_public_simulation.py \
  tests/fixtures/challenger_replacement_v076/public-simulation-golden.json
git commit -m "feat: simulate public decision opportunities"
```

### Task 6: Compose one recoverable v3 DecisionOpportunity runtime

**Files:**
- Create: `src/crypto_quant/challenger_replacement_v3_runtime.py`
- Create: `tests/test_challenger_replacement_v3_runtime.py`
- Modify: `src/crypto_quant/challenger_replacement_opportunity_projection.py`
- Modify: `tests/test_challenger_replacement_opportunities.py`
- Modify: `tests/test_challenger_replacement_opportunity_evidence.py`

**Interfaces:**
- Consumes: retained `ChallengerReplacementEventRoot`, strict plans/contracts,
  fixed build identity and `ChallengerReplacementOpportunityState`.
- Produces:

```python
def run_challenger_replacement_v3_opportunity(
    *, state: ChallengerReplacementOpportunityState,
    event_root: ChallengerReplacementEventRoot,
    plan, economic_plan, predecessor_contract, public_contract,
    build_identity
) -> Mapping[str, Any]: ...
```

- No capture, clock, worker, fault, retry, URL or output-path callback is public.
  Tests patch private imported boundaries only.

- [ ] **Step 1: Write stage/recovery/concurrency RED tests**

Require replay-first behavior and the exact terminal path:

```text
INPUT_PREPARED -> RESULT_PREPARED -> OPPORTUNITY_OBSERVED
INPUT_PREPARED -> OPPORTUNITY_MISSED
```

Test natural current opportunity, schedule-ordered historical `MISSED` facts,
no historical market request, already terminal zero-network/zero-write return,
resume after each durable boundary, result exact replay, parent snapshot chain,
single active opportunity, optimistic token conflict and source/build/plan
mutation. Crash tests patch the private append wrapper before/after each append
and retry in a new interpreter.

Use two real processes at the append boundary. Same candidate yields one event
chain and `{OBSERVED, ALREADY_TERMINAL}`; conflicting result yields one winner
and fixed conflict. No duplicate simulated economic order/fill is possible.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_v3_runtime -v
```

Expected: module absent.

- [ ] **Step 3: Implement minimal replay/advance logic**

Use the v0.70 projection to decide exactly one next action. Before every append,
pass the caller-observed last event hash; on conflict, return no rebased result.
The private capture call is direct:

```python
def _acquire(state):
    return acquire_challenger_replacement_public_market_capture(state=state)
```

Map acquisition/input failures to canonical flat/exposed `MISSED` or fixed
failure semantics from v0.69/v0.75. Never append a failure to an already
advanced opportunity. Store exact canonical capture/result bytes through the
released event payload encoding; no parallel artifact copy becomes authority.

- [ ] **Step 4: Run GREEN and fresh-process adjacency**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_events \
  tests.test_challenger_replacement_opportunities \
  tests.test_challenger_replacement_opportunity_evidence \
  tests.test_challenger_replacement_v3_runtime -v
python3 -m compileall -q \
  src/crypto_quant/challenger_replacement_v3_runtime.py
git diff --check
```

- [ ] **Step 5: Commit**

```bash
git add src/crypto_quant/challenger_replacement_v3_runtime.py \
  src/crypto_quant/challenger_replacement_opportunity_projection.py \
  tests/test_challenger_replacement_v3_runtime.py \
  tests/test_challenger_replacement_opportunities.py \
  tests/test_challenger_replacement_opportunity_evidence.py
git commit -m "feat: compose replacement v3 public runtime"
```

### Task 7: Bind the v3 deployment and dual-clock start receipt

**Files:**
- Create: `src/crypto_quant/challenger_replacement_v3_deployment.py`
- Create: `src/crypto_quant/challenger_replacement_v3_start.py`
- Create: `src/crypto_quant/schemas/challenger-replacement-v3-deployment-v1.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-v3-start-receipt-v1.schema.json`
- Create: `tests/test_challenger_replacement_v3_deployment.py`
- Create: `tests/test_challenger_replacement_v3_start.py`

**Interfaces:**
- Produces:

```python
def build_challenger_replacement_v3_deployment(
    *, predecessor_release, plan, economic_plan, accelerated_plan,
    predecessor_contract, public_contract, build_identity,
    strategy_inventory
) -> Dict[str, Any]: ...

def render_challenger_replacement_v3_plist(deployment) -> bytes: ...

def load_challenger_replacement_v3_deployment_bytes(
    data: bytes, *, predecessor_release, plan, economic_plan,
    accelerated_plan, predecessor_contract, public_contract,
    build_identity, strategy_inventory
) -> Dict[str, Any]: ...

def build_challenger_replacement_v3_start_receipt(
    *, deployment, event_projection, event_root_identity
) -> Dict[str, Any]: ...

def load_challenger_replacement_v3_start_receipt_bytes(
    data: bytes, *, deployment, event_projection, event_root_identity
) -> Dict[str, Any]: ...
```

- Consumes: candidate-only exact build/plan/contract inventory and the strict
  canonical event projection containing the first natural
  `OPPORTUNITY_OBSERVED` event.
- Produces no install/publisher/launchctl API. The v0.68 540-slot receipt remains
  historical and is never accepted by the v3 loader.

- [ ] **Step 1: Write deployment/plist/start RED tests**

Require the exact six local-hour values `00,04,08,12,16,20`, minute `02`,
`RunAtLoad=false`, `KeepAlive=false`, fixed service label and owner-only paths.
Require package executable and exact inventory hashes. Assert every authority
false and absence of API-key/account/order environment entries.

For start receipt, require one event to bind both clocks:

```python
self.assertEqual(receipt["operational_start"]["observed_at"],
                 observed["observed_at"])
self.assertEqual(receipt["economic_start"]["scheduled_for"],
                 observed["scheduled_for"])
self.assertEqual(receipt["shared_event_hash"], observed.event_hash)
```

Reject fixture result qualification, `MISSED`, manually supplied time,
nonfirst observed candidate, plan/build/root mismatch, old receipt Schema,
`required_slot_count`, 540-slot fields and any post-build mutation.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_v3_deployment \
  tests.test_challenger_replacement_v3_start -v
```

Expected: modules/Schemas absent.

- [ ] **Step 3: Implement pure trust documents**

Reuse canonical/hash helpers and released plist rendering patterns, but do not
import install/start mutation functions. The fixed candidate paths remain under
the v0.68 owner-only root and use the v3 event directory. The candidate build
identity has exact keys `reviewed_code_checkpoint/package_version/`
`predecessor_manifest_identity/executable_core_hash`: the checkpoint is a real
commit containing every core byte, the predecessor object is the complete
v0.75 manifest/release identity, and the aggregate covers the exact path-to-SHA
inventory. The final v0.76 manifest later binds that inventory and deployment.
No candidate document claims a future release tag, merge commit, v0.76 manifest
hash/file SHA or any self-referential identity.
Committed deterministic vectors may use only the explicit seven-key
`v0.76.0-fixture` identity. It is not a deployment authority; production
boundaries reject the unqualified seven-key `v0.76.0` form.

Start receipt construction scans the strict projection in canonical sequence,
derives the first eligible natural `OPPORTUNITY_OBSERVED`, and derives all
time/ID fields from that event. All plan/deployment/root fields come from typed
inputs. It has no caller-selected event, `now` parameter, production path or
publisher function.

- [ ] **Step 4: Prove deterministic candidate bytes and run adjacency**

Generate deployment bytes twice with a frozen test-only executable-core
identity, byte-compare in memory and assert loader replay. Do not commit the
formal artifact here: Tasks 8-11 still change executable code. Task 12 freezes
the final executable-core identity and creates the formal deployment.

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_v3_deployment \
  tests.test_challenger_replacement_v3_start \
  tests.test_challenger_replacement_deployment \
  tests.test_challenger_replacement_start \
  tests.test_challenger_replacement_install_trust -v
python3 -m compileall -q \
  src/crypto_quant/challenger_replacement_v3_deployment.py \
  src/crypto_quant/challenger_replacement_v3_start.py
git diff --check
```

- [ ] **Step 5: Commit**

```bash
git add src/crypto_quant/challenger_replacement_v3_deployment.py \
  src/crypto_quant/challenger_replacement_v3_start.py \
  src/crypto_quant/schemas/challenger-replacement-v3-deployment-v1.schema.json \
  src/crypto_quant/schemas/challenger-replacement-v3-start-receipt-v1.schema.json \
  tests/test_challenger_replacement_v3_deployment.py \
  tests/test_challenger_replacement_v3_start.py
git commit -m "feat: bind replacement v3 deployment candidate"
```

### Task 8: Implement the exact-build fault receipt and 72-hour qualifier

**Files:**
- Create: `src/crypto_quant/challenger_replacement_fault_matrix.py`
- Create: `src/crypto_quant/challenger_replacement_operational_qualification.py`
- Create: `src/crypto_quant/schemas/challenger-replacement-fault-matrix-receipt-v1.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-operational-qualification-v1.schema.json`
- Create: `tests/test_challenger_replacement_fault_matrix.py`
- Create: `tests/test_challenger_replacement_operational_qualification.py`

**Interfaces:**
- Produces:

```python
def run_challenger_replacement_fault_matrix(
    *, build_identity: Mapping[str, Any]
) -> Dict[str, Any]: ...

def load_challenger_replacement_fault_matrix_bytes(
    data: bytes, *, build_identity
) -> Dict[str, Any]: ...

@dataclass(frozen=True)
class OperationalQualificationFacts:
    start_receipt: Mapping[str, Any]
    terminal_opportunities: Tuple[Mapping[str, Any], ...]
    observed_at: str
    position_state: str
    reconciliation_status: str
    hard_stop_reason_codes: Tuple[str, ...]

def evaluate_challenger_replacement_operational_qualification(
    facts: OperationalQualificationFacts,
    *, accelerated_plan: Mapping[str, Any], fault_receipt: Mapping[str, Any]
) -> Dict[str, Any]: ...

def load_challenger_replacement_operational_qualification_bytes(
    data: bytes, *, facts, accelerated_plan, fault_receipt
) -> Dict[str, Any]: ...
```

- Evaluator is pure and imports no filesystem/network/subprocess/launchd/UI
  module. Production policy is never caller supplied.

- [ ] **Step 1: Write the exhaustive fault-case RED**

Freeze this exact ordered tuple; each result has exact `case_id`, expected
boundary, observed boundary, passed boolean and fixture/result hashes:

```python
EXPECTED_CASE_IDS = (
    "PROCESS_TERMINATION_BEFORE_INPUT_APPEND",
    "PROCESS_TERMINATION_AFTER_INPUT_APPEND",
    "PROCESS_TERMINATION_BEFORE_RESULT_APPEND",
    "PROCESS_TERMINATION_AFTER_RESULT_APPEND",
    "PROCESS_TERMINATION_BEFORE_TERMINAL_APPEND",
    "PROCESS_TERMINATION_AFTER_TERMINAL_APPEND",
    "FRESH_PROCESS_REPLAY_IDEMPOTENT_RETRY",
    "NETWORK_LOSS_BEFORE_REQUEST",
    "NETWORK_LOSS_AFTER_REQUEST_BEFORE_RESPONSE",
    "NETWORK_LOSS_AFTER_RESPONSE_RECEIPT",
    "CLOCK_OFFSET",
    "CLOCK_SPREAD",
    "WALL_CLOCK_BACKWARD",
    "MONOTONIC_INCONSISTENCY",
    "DUPLICATE_INVOCATION",
    "STALE_OPTIMISTIC_TOKEN",
    "MALFORMED_MARKET_INPUT",
    "PARTIAL_MARKET_INPUT",
    "REVISED_MARKET_INPUT",
    "UNAVAILABLE_MARKET_INPUT",
    "PARTIAL_SIMULATED_FILL",
    "LATE_SIMULATED_FILL",
    "SIMULATED_CANCEL_RACE",
    "UNRESOLVED_UNKNOWN_CLASSIFICATION",
    "PROTECTIVE_STOP_MODEL_FAILURE",
    "PROTECTIVE_STOP_REPLACE_MODEL_FAILURE",
    "ENGINE_VENUE_MODEL_LEDGER_DISAGREEMENT",
    "FEE_REPLAY",
    "FUNDING_REPLAY",
    "DAILY_LOSS_LOCK",
    "DRAWDOWN_LOCK",
    "DISK_WRITE_FAILURE",
    "FILE_FSYNC_FAILURE",
    "DIRECTORY_FSYNC_FAILURE",
    "PROJECTION_SOURCE_UNAVAILABLE",
    "PROJECTION_SOURCE_INVALID",
)
```

No skipped/xfail/unknown value is allowed. The runner must exercise actual
public kernel/runtime functions with mocks at existing private boundaries; it
cannot accept caller case results.

```python
receipt = run_challenger_replacement_fault_matrix(
    build_identity=fixture_build_identity()
)
self.assertEqual(tuple(item["case_id"] for item in receipt["cases"]),
                 EXPECTED_CASE_IDS)
self.assertTrue(all(item["passed"] is True for item in receipt["cases"]))
```

RED tests also require exact-build mismatch, missing/extra/duplicate case,
changed expected status and one failed case to reject qualification.

- [ ] **Step 2: Write 72-hour state-machine RED tests**

Cover `NOT_STARTED`, `ACTIVE`, `INTERRUPTED_RECOVERABLE`, `BLOCK_FAILED` and
`QUALIFIED`; exact equality at 259200 seconds; 259199 seconds; disconnected
segments that must not sum; flat miss; safe disconnection; later natural
restart; exposed miss; unresolved position/order; reconciliation failure;
missing simulated stop; fixture time; untrusted clock; incomplete terminal
coverage and fault receipt failure.

```python
result = evaluate_challenger_replacement_operational_qualification(
    facts_for_segments((100000, 159200), (0, 259200)),
    accelerated_plan=plan,
    fault_receipt=passed_fault_receipt,
)
self.assertEqual(result["status"], "QUALIFIED")
self.assertEqual(result["eligible_continuous_seconds"], 259200)
```

- [ ] **Step 3: Run combined RED**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_fault_matrix \
  tests.test_challenger_replacement_operational_qualification -v
```

Expected: modules absent.

- [ ] **Step 4: Implement fixed runner and pure qualifier**

The fault runner owns the case registry and invokes no network. The qualifier
validates typed facts, replays the accelerated plan's exact policy hash, finds
the final uninterrupted segment and gives hard-stop precedence over elapsed
time. Result self-hash and stable ID cover facts, plan, fault receipt and build.
The loader rebuilds the complete result; caller status is never trusted.

- [ ] **Step 5: Run GREEN and commit the runner/qualifier**

Use a frozen test-only build identity to prove deterministic receipt bytes. Do
not publish the formal release receipt here: Tasks 9-11 still change runtime
code. Task 12 freezes the final runtime-core inventory and generates the formal
receipt against that exact identity.

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_fault_matrix \
  tests.test_challenger_replacement_operational_qualification \
  tests.test_challenger_replacement_v3_runtime \
  tests.test_challenger_replacement_accelerated_canary_plan -v
python3 -m compileall -q \
  src/crypto_quant/challenger_replacement_fault_matrix.py \
  src/crypto_quant/challenger_replacement_operational_qualification.py
git diff --check
git add src/crypto_quant/challenger_replacement_fault_matrix.py \
  src/crypto_quant/challenger_replacement_operational_qualification.py \
  src/crypto_quant/schemas/challenger-replacement-fault-matrix-receipt-v1.schema.json \
  src/crypto_quant/schemas/challenger-replacement-operational-qualification-v1.schema.json \
  tests/test_challenger_replacement_fault_matrix.py \
  tests/test_challenger_replacement_operational_qualification.py
git commit -m "feat: qualify continuous public simulation"
```

### Task 9: Build tail-blind economic facts and boundary series

**Files:**
- Create: `src/crypto_quant/challenger_replacement_economic_evaluation.py`
- Create: `tests/test_challenger_replacement_economic_evaluation.py`
- Create: `src/crypto_quant/schemas/challenger-replacement-economic-evaluation-v1.schema.json`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class EconomicProgressFacts:
    start_receipt: Mapping[str, Any]
    terminal_headers: Tuple[Mapping[str, Any], ...]
    observed_at: str

@dataclass(frozen=True)
class EconomicOpportunityFact:
    opportunity_id: str
    scheduled_for: str
    outcome: str
    result_or_null: Optional[Mapping[str, Any]]
    missed_position_state_or_null: Optional[str]
    missed_reason_or_null: Optional[str]

@dataclass(frozen=True)
class EconomicEvaluationFacts:
    start_receipt: Mapping[str, Any]
    opportunities: Tuple[EconomicOpportunityFact, ...]
    observed_at: str
    tail_mark_or_null: Optional[Mapping[str, Any]]

def observe_challenger_replacement_economic_progress(
    facts: EconomicProgressFacts, *, economic_plan: Mapping[str, Any]
) -> Mapping[str, Any]: ...

def _build_economic_boundary_series(
    facts: EconomicEvaluationFacts, *, economic_plan
) -> Mapping[str, Any]: ...
```

`result_or_null`, when present, has exactly `source`, `previous_projection`,
`result`, `sequence` and `parent_event_hash`. `tail_mark_or_null`, when present,
has exactly `source`, `previous_projection` and `marked_equity`. Production
code must strict-load the source/result and recompute the tail mark; tests may
patch only the private strict-replay boundary when constructing 540-item
known-answer populations. No production callback or trusted-result flag is
added.

- `EconomicProgressFacts` contains only schedule/outcome headers and never
  carries result payloads, prices or accounting. `_build_economic_boundary_series`
  remains private, derives
  `tail_scheduled_for = start_scheduled_for + 7776000 seconds`, and checks
  `observed_at >= tail_scheduled_for` before reading any result or tail-mark
  field. It raises `ECONOMIC_TAIL_NOT_REACHED` first. The public observer never
  calls it and never returns economic amounts or statistics.

- [ ] **Step 1: Write strict-fact and pre-tail non-disclosure RED tests**

Cover exact half-open start/tail, 4h cadence, one terminal per due opportunity,
strict result loader binding, unique IDs, order, missing tail, malformed event,
duplicate authority and all confirmed safety failures. Before tail, recursively
scan output/logs for forbidden keys/substrings:

```python
FORBIDDEN = {
    "pnl", "profit", "return", "drawdown", "fee", "funding",
    "confidence", "bootstrap", "power", "rank", "pass",
}
self.assertTrue(FORBIDDEN.isdisjoint(flattened_keys(progress)))
```

The allowed progress result contains only due/terminal/observed/missed counts,
elapsed complete days, next opportunity, evidence health and `TAIL_BLIND`.

- [ ] **Step 2: Write 91-boundary and missingness RED tests**

At tail, require exactly 91 pre-action equities, 90 fixed-capital returns, six
nonoverlapping 15-day blocks, continuous high-water drawdown, cycle counts and
base/stress plus optimistic/pessimistic flat-miss series. Test one Spot cycle,
one perpetual cycle, multiple Funding records, exact one-time fees, tail mark,
nonpositive equity, a flat miss charged exactly once and exposed miss with no
imputation.

- [ ] **Step 3: Run RED**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_economic_evaluation -v
```

Expected: module absent.

- [ ] **Step 4: Implement validation, progress and Decimal reconstruction**

Parse no paths. Recompute each public result through its strict loader before
using it. Apply outcomes in schedule order, snapshot pre-action equity exactly
at `start_scheduled_for + k * 86400` for `k=0..90`, and prevent post-tail input
from changing population. Use
repository Decimal encoders with no intermediate rounding except frozen
cashflow/fee rules. Build stress replay from quantities/event order while
scaling only the v0.74 cost components.

- [ ] **Step 5: Run GREEN and commit**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_economic_evaluation \
  tests.test_challenger_replacement_economic_plan \
  tests.test_challenger_replacement_public_simulation -v
python3 -m compileall -q \
  src/crypto_quant/challenger_replacement_economic_evaluation.py
git diff --check
git add src/crypto_quant/challenger_replacement_economic_evaluation.py \
  src/crypto_quant/schemas/challenger-replacement-economic-evaluation-v1.schema.json \
  tests/test_challenger_replacement_economic_evaluation.py
git commit -m "feat: reconstruct v0.74 economic population"
```

### Task 10: Implement the final v0.74 bootstrap, gates and strict result

**Files:**
- Modify: `src/crypto_quant/challenger_replacement_economic_evaluation.py`
- Modify: `src/crypto_quant/schemas/challenger-replacement-economic-evaluation-v1.schema.json`
- Create: `src/crypto_quant/challenger_replacement_economic_evaluation_cli.py`
- Modify: `tests/test_challenger_replacement_economic_evaluation.py`
- Create: `tests/test_challenger_replacement_economic_evaluation_cli.py`
- Create: `tests/fixtures/challenger_replacement_v076/economic-evaluation-known-answers.json`

**Interfaces:**
- Consumes: Task 9 strict facts/boundary series, exact v0.74 economic plan and
  the exact v0.76 runtime-core build identity.
- Produces:

```python
def evaluate_challenger_replacement_economic_result(
    facts: EconomicEvaluationFacts,
    *, economic_plan: Mapping[str, Any], build_identity: Mapping[str, Any]
) -> Dict[str, Any]: ...

def load_challenger_replacement_economic_evaluation_bytes(
    data: bytes,
    *, facts: EconomicEvaluationFacts, economic_plan: Mapping[str, Any],
    build_identity: Mapping[str, Any]
) -> Dict[str, Any]: ...

def main(argv: Optional[Sequence[str]] = None) -> int: ...
```

- The CLI accepts only no arguments or `--help`. It resolves the future fixed
  owner-only roots from the strict committed v3 deployment; it is never called
  during v0.76 release and cannot accept a date, path, price, return, seed,
  threshold, status, result ID or filename.

- [ ] **Step 1: Write SHA-256 draw and nearest-rank RED vectors**

Commit these literal first-attempt vectors:

```python
DRAW_VECTORS = (
    (2026082574, 0, 0, 84, 32,
     "005ef479a250f41a49dd0717ea738f9979847e07b44ea39c9b322526388edbf8"),
    (2026082574, 0, 1, 84, 65,
     "8ca3b4c3bc8ed7cbb09736de1f197052158e81be999c70b230a8ca58cbbdef29"),
    (2026082574, 9999, 12, 84, 78,
     "3f4f7ea1df3036efdd288a800ef5b7eda452549f1c736e49d58519e632cc4636"),
    (2026082574, 0, 0, 1, 0,
     "98ac38b561532aaab998dfe0cb92ab74e9205fde4d37df1c78c90c4dcf82f5e8"),
)
```

For the otherwise astronomically rare rejection branch at production block
counts, patch private `hashlib.sha256` in the test to return `2^256-1` then `5`
for `start_count=3`; assert attempt strings end in `:0`, `:1` and the accepted
result is `2`. No injectable hash or random source is added to production.
Also cover seven-day blocks and the final short truncation. The private
algorithm under test is exactly:

```python
def _draw_start(seed, replicate, draw, start_count):
    limit = (1 << 256) - ((1 << 256) % start_count)
    attempt = 0
    while True:
        message = (
            f"MBB_V1:{seed}:{replicate}:{draw}:{start_count}:{attempt}"
        ).encode("ascii")
        candidate = int.from_bytes(hashlib.sha256(message).digest(), "big")
        if candidate < limit:
            return candidate % start_count
        attempt += 1
```

Require 10,000 overlapping non-circular seven-day-block replicates, each
truncated to 90 values. For a sorted 10,000-value vector, fifth percentile is
one-based rank `ceil(0.05 * 10000) = 500`; centered-error 95th percentile is
one-based rank `9500`. Any Python `random`, NumPy, float or caller seed fails.

- [ ] **Step 2: Write result/gate/immutability RED tests**

Freeze known answers for base, stress, optimistic-flat-miss and
pessimistic-flat-miss series. Cover all conjunctive gates:

```python
EXPECTED_GATES = {
    "calendar_days": 90,
    "daily_return_count": 90,
    "terminal_coverage": "1",
    "minimum_observed_coverage": "0.95",
    "minimum_completed_cycle_count": 12,
    "minimum_spot_completed_cycle_count": 3,
    "minimum_perpetual_completed_cycle_count": 3,
    "nonempty_15_day_block_count": 6,
    "minimum_moving_block_count": 12,
    "minimum_achieved_power_at_mere": "0.80",
}
```

Include a bootstrap identity vector with 90 copies of `0.001`: observed mean
and every resampled mean/LCB are `0.001`, every centered error and its 95th
critical value are `0`, and achieved power at MERE `0.0005` is `1`. Include 90
copies of `-0.001` to prove the LCB/economic gate is negative while the power
calculation remains a distinct reporting/sample gate.

Require PASS only when both optimistic and pessimistic series pass every
economic gate and every sample/power gate passes. A confirmed safety boundary,
exposed miss, economic gap lock, nonpositive equity or trusted sufficient
evidence failing an economic gate returns
`RESEARCH_CONTINUATION_GATE_DID_NOT_PASS`. Missing/untrusted/unreconstructable
evidence, any sample/power shortfall, or disagreement between optimistic and
pessimistic bounds returns `INCONCLUSIVE_INSUFFICIENT_EVIDENCE`. Test absent
tail mark, observed coverage `0.949999`, completed-cycle/product shortfalls,
block shortfall, achieved power `0.7999`, favorable-series selection, changed
seed, changed first result, post-tail data and a second result filename.
The only successful status literal is
`RESEARCH_CONTINUATION_GATE_PASS`; no alias or boolean pass field is accepted.

The strict loader must rebuild series, bootstrap means, LCB, centered critical
value, achieved power, all gates, result status, stable ID and self-hash before
byte comparison.

- [ ] **Step 3: Run RED**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_economic_evaluation \
  tests.test_challenger_replacement_economic_evaluation_cli -v
```

Expected: final evaluator/CLI symbols absent.

- [ ] **Step 4: Implement the fixed Decimal evaluator and CLI refusal**

Use `Decimal` throughout. The 10,000 bootstrap means are sorted once; use
integer nearest-rank arithmetic and strict comparison to zero. Center every
bootstrap mean by subtracting the observed sample mean, compute the 95th
nearest-rank critical value and count all 10,000 values satisfying:

```python
minimum_effect + centered_error > critical_value
```

Encode the count-derived power as canonical Decimal. The pure evaluator derives
the unique first-result ID from exact inputs. The fixed-path CLI checks the tail
before loading economic payloads, then publishes with the existing secure
no-overwrite protocol: an existing exact result is replay-only and a different
existing result fails closed. Before tail it returns a fixed nonzero exit code
without creating or reading a result.

- [ ] **Step 5: Run GREEN and commit**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_economic_evaluation \
  tests.test_challenger_replacement_economic_evaluation_cli \
  tests.test_challenger_replacement_economic_plan \
  tests.test_challenger_cohort_cumulative_evaluation -v
python3 -m compileall -q \
  src/crypto_quant/challenger_replacement_economic_evaluation.py \
  src/crypto_quant/challenger_replacement_economic_evaluation_cli.py
git diff --check
git add src/crypto_quant/challenger_replacement_economic_evaluation.py \
  src/crypto_quant/challenger_replacement_economic_evaluation_cli.py \
  tests/test_challenger_replacement_economic_evaluation.py \
  tests/test_challenger_replacement_economic_evaluation_cli.py \
  tests/fixtures/challenger_replacement_v076/economic-evaluation-known-answers.json
git commit -m "feat: evaluate replacement v3 economics"
```

### Task 11: Add the v3 observer and reuse the read-only operations console

**Files:**
- Create: `src/crypto_quant/challenger_replacement_v3_observer.py`
- Create: `src/crypto_quant/operations_projection_v3.py`
- Create: `src/crypto_quant/schemas/operations-projection-v3.schema.json`
- Create: `config/operations-projection-v3.schema.json`
- Create: `tests/test_challenger_replacement_v3_observer.py`
- Create: `tests/test_operations_projection_v3.py`
- Modify: `src/crypto_quant/operations_alerts.py`
- Modify: `src/crypto_quant/operations_dashboard.py`
- Modify: `src/crypto_quant/dashboard/app.js`
- Modify: `tests/test_operations_alerts.py`
- Modify: `tests/test_operations_dashboard.py`

**Interfaces:**
- Consumes: strict v3 deployment/start/event replay, strict fault receipt,
  strict operational result and Task 9 tail-blind progress. It never consumes
  raw JSON or trusts a status string without its domain loader.
- Produces:

```python
@dataclass(frozen=True)
class ChallengerReplacementV3Observation:
    deployment: Mapping[str, Any]
    start_receipt_or_null: Optional[Mapping[str, Any]]
    event_projection: Mapping[str, Any]
    operational_qualification: Mapping[str, Any]
    economic_progress: Mapping[str, Any]
    evidence_health: str

def observe_challenger_replacement_v3() -> ChallengerReplacementV3Observation: ...

def build_operations_projection_v3(
    observation: ChallengerReplacementV3Observation,
    *, build_identity: Mapping[str, Any]
) -> Dict[str, Any]: ...

def load_operations_projection_v3_bytes(
    data: bytes, *, observation, build_identity
) -> Dict[str, Any]: ...
```

- The public observer accepts no path selection. It resolves only fixed v3
  deployment paths internally, then validates descriptor identity. Tests patch
  private fixed-path loader boundaries; the pure projection accepts no paths.
  Neither surface appends events or repairs files.

- [ ] **Step 1: Write observer/projection RED tests**

Cover not-installed, installed-not-started candidate facts, active,
recoverable interruption, blocked and qualified operational states; due,
observed and missed counts; next opportunity; current simulated product,
reconciliation, risk lock; exact provenance and every authority false.

Before tail, recursively reject these projection keys and rendered strings:

```python
ECONOMIC_DISCLOSURE_FORBIDDEN = (
    "pnl", "profit", "return", "drawdown", "fee", "funding",
    "confidence", "bootstrap", "power", "rank", "pass",
)
```

Test symlink/hardlink/FIFO/directory/socket/wrong-owner/wrong-mode/oversize,
path replacement, event-chain corruption and strict-loader failure. Every
failure returns a fixed health reason without appending an event.

- [ ] **Step 2: Write console compatibility and read-only RED tests**

Require byte-equivalent v1/v2 projection handling and add exact v3 dispatch:

```python
identity = ("./operations-projection-v3.schema.json", "3.0.0")
self.assertEqual(classify_projection(v3_projection), identity)
```

Render safe text only; exercise hostile strings and verify escaping. Assert
loopback `127.0.0.1`, GET/HEAD-only routes, no POST/PUT/PATCH/DELETE, no action
button, credential input, external script/style/font/image, WebSocket, fetch to
non-loopback host or UI-to-runtime dependency. UI health must not alter any
authority field.

- [ ] **Step 3: Run RED**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_v3_observer \
  tests.test_operations_projection_v3 \
  tests.test_operations_alerts \
  tests.test_operations_dashboard -v
```

Expected: v3 observer/projection imports and dispatch are absent.

- [ ] **Step 4: Implement strict read-only composition and v3 dispatch**

Open each fixed source through the existing owner-only no-follow descriptor
boundary, bound size before read, replay through its production loader, then
close exactly once. Build only this narrow projection:

```python
projection = {
    "service_and_evidence_health": health,
    "operational_qualification": operational_summary,
    "opportunities": opportunity_counts,
    "next_required_opportunity": next_required,
    "fault_matrix": fault_summary,
    "economic_progress": tail_blind_progress,
    "simulation_state": simulation_state,
    "provenance": provenance,
    "authority": ALL_FALSE_AUTHORITY,
}
```

Copy the package Schema byte-for-byte to `config/`; strict tests compare the
two files. Extend existing alert and dashboard dispatch tables rather than
creating a server or frontend.

- [ ] **Step 5: Run GREEN, v1/v2 adjacency and commit**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_v3_observer \
  tests.test_operations_projection \
  tests.test_operations_projection_v2 \
  tests.test_operations_projection_v3 \
  tests.test_operations_alerts \
  tests.test_operations_dashboard -v
cmp config/operations-projection-v3.schema.json \
  src/crypto_quant/schemas/operations-projection-v3.schema.json
python3 -m compileall -q \
  src/crypto_quant/challenger_replacement_v3_observer.py \
  src/crypto_quant/operations_projection_v3.py
git diff --check
git add src/crypto_quant/challenger_replacement_v3_observer.py \
  src/crypto_quant/operations_projection_v3.py \
  src/crypto_quant/schemas/operations-projection-v3.schema.json \
  config/operations-projection-v3.schema.json \
  src/crypto_quant/operations_alerts.py \
  src/crypto_quant/operations_dashboard.py \
  src/crypto_quant/dashboard/app.js \
  tests/test_challenger_replacement_v3_observer.py \
  tests/test_operations_projection_v3.py \
  tests/test_operations_alerts.py \
  tests/test_operations_dashboard.py
git commit -m "feat: observe replacement v3 read only"
```

### Task 12: Freeze exact release evidence and publish v0.76.0

**Files:**
- Create: `artifacts/challenger-replacement/challenger-replacement-v3-deployment-v0.76.0.json`
- Create: `artifacts/challenger-replacement/challenger-replacement-fault-matrix-v0.76.0.json`
- Create: `docs/adr/0076-public-simulation-research-bundle.md`
- Create: `docs/implementation-status-v0.76.0.md`
- Create: `tests/test_challenger_replacement_v076_release.py`
- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `setup.py`
- Modify: `src/crypto_quant/__init__.py`
- Modify: `src/crypto_quant/build.py`
- Modify: `scripts/refresh_evaluator_build_manifest.py`
- Modify: `config/evaluator-build-manifest-v1.json`

**Interfaces:**
- Produces package `0.76.0`, manifest `1.70.0`, an exact offline fault receipt,
  release status `PUBLIC_SIMULATION_AND_RESEARCH_CODE_RELEASED_NOT_ACTIVATED`
  and an annotated `v0.76.0` tag peeled to merged `origin/main`.
- Defines `executable_core_identity` as the sorted exact path-to-SHA map of all
  v0.76 production Python, package Schemas and fixed fixtures from Tasks 1-11.
  The formal deployment binds this map/hash. Defines `runtime_core_identity` as
  that same map plus the exact deployment artifact; the formal fault receipt
  binds the runtime-core map/hash. Both identities exclude the fault receipt,
  release test, ADR, status, README and build manifest to avoid a hash cycle.
  The final build manifest binds every map member, deployment and receipt.

- [ ] **Step 1: Write release/status/static RED tests**

Require all new modules, mirrored Schemas and committed artifacts in the build
manifest; package/manifest versions `0.76.0`/`1.70.0`; exact status claims;
v0.69/v0.74/v0.75 artifact replay; deployment and fault receipt loader replay;
runtime-core inventory equality; and zero release authority.

Add an AST/static gate over v0.76 public modules:

```python
FORBIDDEN_IMPORT_ROOTS = {
    "requests", "aiohttp", "websockets", "ccxt", "binance",
}
FORBIDDEN_CAPABILITIES = {
    "X-MBX-APIKEY", "api_key", "secret_key", "withdraw",
    "/api/v3/order", "/fapi/v1/order", "launchctl bootstrap",
}
```

Allow `urllib` only in the shared public HTTP/capture boundary, filesystem only
in observer/fixed CLI/deployment-document utilities, and no subprocess in pure
simulation/qualification/evaluation/projection modules. Enforce net-new v0.76
production Python at or below the revised 5,000 physical-line hard cap, each
remaining task within its section-13 allowance, and the no-generic-framework
gate.

- [ ] **Step 2: Run release RED**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_v076_release -v
```

Expected: release files, versions, formal receipt and manifest entries absent.

- [ ] **Step 3: Obtain one independent complete code/spec review**

Give the reviewer exact base `a51ed15d5a484e5bb9a54dc75a7fef4e8876e4d5`,
spec, plan and Tasks 1-11 diff. Require severity-ranked findings with file and
line evidence. Critical/Important must be zero. For each valid finding, write a
targeted failing test, make the minimum fix, run the affected suite and request
only a targeted rereview; do not repeat the unchanged whole-branch review.

- [ ] **Step 4: Freeze deployment, runtime-core identity and fault receipt**

After review fixes are final, commit a code checkpoint containing every core
path and record its real commit ID. Then enumerate executable-core paths, compute every
SHA-256 and the canonical aggregate hash, and build the deployment twice in
memory to byte-compare before adding one canonical JSON plus LF with
`apply_patch`. Then extend the identity with the exact deployment artifact,
compute `runtime_core_hash` and invoke the fixed Task 8 runner once. Serialize
the returned object a second time only to byte-compare; do not execute a second
fault campaign. Add the one receipt JSON plus LF with `apply_patch`, then prove:

```python
receipt = load_challenger_replacement_fault_matrix_bytes(
    receipt_bytes, build_identity=runtime_core_identity
)
assert len(receipt["cases"]) == 36
assert all(item["passed"] is True for item in receipt["cases"])
assert receipt["runtime_core_hash"] == runtime_core_hash
```

Any code/Schema/fixture/deployment change after this point invalidates the
receipt and returns to this step. Release-document-only changes do not alter
the defined runtime core.

- [ ] **Step 5: Write exact ADR/status/version/manifest GREEN**

Record the explicit distinction between offline conformance and real time:

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

Bump package files to `0.76.0`, manifest to `1.70.0`, add the exact new
inventory paths to `build.py`, refresh once, and make the release loader prove
the refreshed manifest and runtime-core/receipt bindings.

- [ ] **Step 6: Run focused/adjacent verification**

```bash
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_public_http \
  tests.test_challenger_replacement_public_market_capture \
  tests.test_challenger_replacement_public_simulation_contract \
  tests.test_challenger_replacement_public_simulation \
  tests.test_challenger_replacement_v3_runtime \
  tests.test_challenger_replacement_v3_deployment \
  tests.test_challenger_replacement_v3_start \
  tests.test_challenger_replacement_fault_matrix \
  tests.test_challenger_replacement_operational_qualification \
  tests.test_challenger_replacement_economic_evaluation \
  tests.test_challenger_replacement_economic_evaluation_cli \
  tests.test_challenger_replacement_v3_observer \
  tests.test_operations_projection_v3 \
  tests.test_challenger_replacement_v076_release -v
PYTHONPATH=src:tests python3 -m unittest \
  tests.test_challenger_replacement_v069_release \
  tests.test_challenger_replacement_v074_release \
  tests.test_challenger_replacement_v075_release \
  tests.test_operations_projection \
  tests.test_operations_projection_v2 \
  tests.test_operations_alerts \
  tests.test_operations_dashboard -v
```

- [ ] **Step 7: Run the one final local release gate**

Run once on the final unchanged candidate:

```bash
PYTHONPATH=src:tests python3 -m unittest discover -s tests
python3 -m compileall -q src tests
make validate
git diff --check
git status --short
```

Expected: full suite, compileall and validation pass; diff check passes; status
contains only the exact release files to be committed. Do not repeat this full
suite on the unchanged state.

- [ ] **Step 8: Commit the release candidate**

```bash
git add artifacts/challenger-replacement/challenger-replacement-v3-deployment-v0.76.0.json \
  artifacts/challenger-replacement/challenger-replacement-fault-matrix-v0.76.0.json \
  docs/adr/0076-public-simulation-research-bundle.md \
  docs/implementation-status-v0.76.0.md \
  tests/test_challenger_replacement_v076_release.py \
  README.md pyproject.toml setup.py src/crypto_quant/__init__.py \
  src/crypto_quant/build.py scripts/refresh_evaluator_build_manifest.py \
  config/evaluator-build-manifest-v1.json
git commit -m "release: prepare v0.76.0 public simulation bundle"
git status --short
```

Expected: clean worktree.

- [ ] **Step 9: Publish through the public repository release gates**

Read-only verify `origin`, public repository identity, write permission and
remote main. Push the feature branch, create a Draft PR, wait for Python 3.9,
Python 3.12 and macOS arm64 PR CI, merge only that exact reviewed head, wait for
merged-main CI, then create and push an annotated `v0.76.0` tag. Verify:

```bash
test "$(git rev-parse origin/main)" = "$(git rev-parse v0.76.0^{})"
git cat-file -t v0.76.0 | grep '^tag$'
git status --short
```

If billing, CI, permission, loader, identity or test status is not green, keep
the candidate unpublished and report the exact gate; never bypass required CI
or retag another commit.

---

## Final verification checklist

- [ ] Every spec section 1-15 maps to Tasks 1-12; no requirement is implemented
  only by prose.
- [ ] Exact v0.67 and v0.71/v0.72 fixture behavior remains unchanged.
- [ ] Public capture uses only fixed credential-free GETs and no release-time
  network request occurs.
- [ ] Event log is the sole fact source; all results/projections are replayed
  derivatives.
- [ ] Fault receipt covers all 36 exact case IDs against the final runtime-core
  identity.
- [ ] Operational qualification cannot synthesize 72 hours; economic evaluator
  cannot inspect or disclose pre-tail outcomes.
- [ ] v1/v2 operations projections remain exact; v3 is loopback-only/read-only.
- [ ] New production Python is at most 5,000 physical lines; Task 8 adds 575
  measured lines, Tasks 9-10 together add at most 800, and Task 11 adds at most
  350. The 75-line Task 8 overage is deducted from the section-13 contingency.
  The final 800 lines are reserved exclusively for independent-review
  remediation; unused allowance is not available for feature expansion.
- [ ] No install, start, credential, account, Broker, real order, fund movement,
  production state write, 72-hour timer or 90-day timer occurred.
- [ ] Critical/Important review findings are zero and final local/remote release
  gates are backed by exact command/run identities.
