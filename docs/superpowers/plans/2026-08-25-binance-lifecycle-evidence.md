# v0.72 Binance Lifecycle Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a fixture-only Binance Spot-long/perpetual-short lifecycle,
strict result evidence v2 and canonical DecisionOpportunity integration without
adding any trading, account, credential, installation or production authority.

**Architecture:** Keep the released v0.71 accounting/risk core as the only
economic calculator.  Add a product-specific pure lifecycle reducer, a strict
v2 evidence codec and a thin fixture runner over the existing retained event
root.  The append-only opportunity log remains the only authority; goldens and
snapshots are projections.

**Tech Stack:** Python 3.9/3.12, stdlib dataclasses/Decimal/unittest,
jsonschema Draft 2020-12, existing canonical JSON/event-root primitives, GitHub
Actions Python 3.9/3.12 and macOS arm64.

**Spec:** `docs/superpowers/specs/2026-08-25-binance-lifecycle-evidence-design.md`

## Global Constraints

- Start from annotated `v0.71.0^{}` commit
  `ba81e48a572e75806bba8b859471f0a7345572dd`.
- Preserve exact bytes of v0.69 plan, v0.70 event fixtures and v0.71 contract.
- Fixture-only: no network, account, credential, Broker, SDK, testnet/real order,
  filesystem path authority, production root, install, start, scheduler or UI.
- Exact authority: all counts zero; every authority/activation boolean false.
- No public fault/scenario/path/time/price/PnL/outcome callback or override.
- Canonical event log is the sole authority; exports/snapshots/goldens are
  projections.
- Every production module is at most 700 physical lines.
- Net-new production logic across the spec's exact modules is at most 1,500
  physical lines relative to `v0.71.0^{}`; unrelated deletions do not count.
- If a size gate cannot hold, stop before artifacts/release and preregister a
  new semantic split.  Do not introduce a generic framework to evade it.
- Use exact RED → minimal GREEN → refactor for every task.  Record the exact RED
  output in the task checkpoint before GREEN; commit the reviewed task only
  after GREEN.  A separate RED commit is not required.
- Run one complete local suite only on the final code state; focused tests are
  used during tasks.  Do not repeat a full suite on unchanged code.
- v0.72 status is exactly
  `FIXTURE_LIFECYCLE_EVIDENCE_VERIFIED_NOT_OPERATIONAL`.
- v0.72 does not start the seven-day or 90-day clocks and does not claim
  profitability, AI advantage, Paper completion, Canary or live eligibility.

## File map

- `src/crypto_quant/challenger_replacement_binance_lifecycle.py`: immutable
  lifecycle event/observation/result types, stable IDs, order/stop reducers and
  three independent reconciliation projections.
- `src/crypto_quant/challenger_replacement_simulation.py`: released accounting
  core; add only a private v0.72 stop-before-strategy transition while keeping
  the public v0.71 result shape and bytes exact.
- `src/crypto_quant/challenger_replacement_opportunity_evidence.py`: keep v1
  replay and add strict v2 builder/loader dispatch.
- `src/crypto_quant/challenger_replacement_opportunity_projection.py`: sole
  event state machine; project v2 snapshot and forbid v2 RESULT→MISSED.
- `src/crypto_quant/challenger_replacement_opportunities.py`: facade/state; no
  second state machine.
- `src/crypto_quant/challenger_replacement_fixture_simulation.py`: thin
  canonical-input fixture runner and recovery orchestration.
- `src/crypto_quant/challenger_replacement_binance_simulation_input.py`: strict
  input-v1 build-identity dispatch; accept only the exact released v0.71 fixture
  tuple or the exact v0.72 fixture tuple, without changing v0.71 bytes.
- `config/challenger-replacement-opportunity-result-evidence-v2.schema.json`
  and package mirror: exact v2 schema.
- `tests/test_challenger_replacement_binance_lifecycle.py`: pure lifecycle,
  stop, fault and reconciliation tests.
- `tests/test_challenger_replacement_fixture_simulation.py`: runner, crash and
  concurrency tests.
- `tests/test_challenger_replacement_opportunity_evidence.py`: v1/v2 strict
  evidence tests.
- `tests/test_challenger_replacement_opportunities.py`: projection/catch-up
  compatibility and v2 terminal tests.
- `tests/challenger_replacement_v3_fixtures.py`: deterministic v0.72 fixture
  builders with non-authoritative build identity.
- `tests/fixtures/challenger_replacement_v072/`: portable Spot/Perp cycles.
- `artifacts/challenger-replacement/challenger-replacement-binance-golden-fixture-manifest-v0.72.0.json`:
  ordered exact fixture inventory.
- `tests/test_challenger_replacement_v072_artifacts.py`: pre-artifact and exact
  artifact replay.
- `tests/test_challenger_replacement_v072_release.py`: final status, manifest,
  size, authority and predecessor gates.

---

### Task 1: Freeze canonical lifecycle identities and no-intent flow

**Files:**
- Create: `src/crypto_quant/challenger_replacement_binance_lifecycle.py`
- Create: `tests/test_challenger_replacement_binance_lifecycle.py`
- Modify: `src/crypto_quant/challenger_replacement_binance_simulation_input.py`
- Modify: `tests/test_challenger_replacement_binance_simulation_input.py`
- Modify: `tests/challenger_replacement_v3_fixtures.py`

**Interfaces:**
- Consumes: `stable_id`, `canonical_json`, `artifact_self_hash`, the exact v0.71
  decision/accounting/next-snapshot mapping returned internally by
  `simulate_challenger_replacement_opportunity`.
- Produces:

```python
class ChallengerReplacementLifecycleError(ValueError):
    reason_code: str

@dataclass(frozen=True)
class LifecycleEvent:
    ordinal: int
    event_type: str
    event_hash: str
    parent_event_hash_or_null: Optional[str]
    intent_id_or_null: Optional[str]
    attempt_id_or_null: Optional[str]
    payload_bytes: bytes

@dataclass(frozen=True)
class ChallengerReplacementLifecycleResult:
    source_bytes: bytes
    previous_snapshot_bytes: bytes
    plan_identity_bytes: bytes
    contract_identity_bytes: bytes
    build_identity_bytes: bytes
    decision_bytes: bytes
    accounting_bytes: bytes
    next_snapshot_bytes: bytes
    lifecycle_events: Tuple[LifecycleEvent, ...]
    status: str
    operationally_complete: bool
    reason_code_or_null: Optional[str]

def simulate_challenger_replacement_binance_lifecycle(
    *, source, previous_projection, plan, contract, build_identity
) -> ChallengerReplacementLifecycleResult
```

The strict simulation-input v1 loader uses version dispatch over exactly two
accepted fixture identities:

```text
v0.71: release_tag=v0.71.0-fixture, package_version=0.71.0,
       manifest_version=1.65.0
v0.72: release_tag=v0.72.0-fixture, package_version=0.72.0,
       manifest_version=1.66.0
```

The v0.72 fixture helper is named `fixture_v072_build_identity()`.  Lifecycle
execution requires the source-bound build identity to equal the explicitly
passed v0.72 identity.  Projection and v2 result evidence bind that same exact
identity.  Any v0.71/v0.72 cross-version mix is rejected; exact v0.71 fixture
loading and replay remain accepted byte-for-byte.

- [ ] **Step 1: Write identity/envelope RED tests**

Create tests that require exact input build-identity dispatch, exact v0.71
replay, rejection of every cross-version mix, common event keys,
ordinal/parent/self-hash,
stable intent/attempt/client IDs, canonical Decimal payloads, and rejection of
caller mappings or caller IDs.  Require HOLD/NO_TRADE to emit exactly
`NO_INTENT_RECONCILED` then `LIFECYCLE_RECONCILED_FIXTURE` with null IDs.

```python
def test_no_intent_has_exact_canonical_lifecycle(self):
    result = lifecycle.simulate_challenger_replacement_binance_lifecycle(
        source=self.flat_source,
        previous_projection=self.genesis,
        plan=self.plan,
        contract=self.contract,
        build_identity=self.build,
    )
    self.assertEqual(
        [event.event_type for event in result.lifecycle_events],
        ["NO_INTENT_RECONCILED", "LIFECYCLE_RECONCILED_FIXTURE"],
    )
    self.assertEqual(result.status, "RECONCILED_FIXTURE")
    self.assertTrue(result.operationally_complete)
```

- [ ] **Step 2: Run Task 1 tests and record RED**

Run:

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_binance_lifecycle \
  tests.test_challenger_replacement_binance_simulation_input -v
```

Expected: import/API failures because the lifecycle module does not exist.
Save the exact failing test names/output in the task checkpoint.

- [ ] **Step 3: Implement immutable types and exact event builder**

First add the two-value strict input-v1 identity dispatch and the v0.72 fixture
builder.  Then implement only the listed dataclasses, fixed error mapping, the
15 event-type payload key table, canonical event self-hash/parent validation
and stable IDs.
Use one private `_append_event(...)` that receives typed values, not a public
payload mapping.  Add the no-intent reducer by consuming the existing v0.71
simulation result.

The module must not import `orders.py`, filesystem/network/time modules, or
expose observation/fault configuration in this task.

- [ ] **Step 4: Run Task 1 GREEN and adjacent accounting tests**

Run:

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_binance_lifecycle \
  tests.test_challenger_replacement_binance_simulation_input \
  tests.test_challenger_replacement_simulation \
  tests.test_challenger_replacement_simulation_contract -v
PYTHONPATH=src python3 -m compileall -q src/crypto_quant
git diff --check
```

Expected: all selected tests pass; v0.71 accounting results are unchanged.

- [ ] **Step 5: Commit Task 1**

```bash
git add \
  src/crypto_quant/challenger_replacement_binance_lifecycle.py \
  src/crypto_quant/challenger_replacement_binance_simulation_input.py \
  tests/test_challenger_replacement_binance_lifecycle.py \
  tests/test_challenger_replacement_binance_simulation_input.py \
  tests/challenger_replacement_v3_fixtures.py
git commit -m "feat: define replacement lifecycle evidence"
```

### Task 2: Implement normal Spot/Perp and protective-stop lifecycle

**Files:**
- Modify: `src/crypto_quant/challenger_replacement_binance_lifecycle.py`
- Modify: `src/crypto_quant/challenger_replacement_simulation.py`
- Modify: `tests/test_challenger_replacement_binance_lifecycle.py`
- Modify: `tests/test_challenger_replacement_simulation.py`
- Modify: `tests/challenger_replacement_v3_fixtures.py`

**Interfaces:**
- Consumes: Task 1 lifecycle result/event types and v0.71 pure accounting.
- Produces the spec's exact normal sequences for Spot open/hold/close,
  perpetual short open/hold/funding/close and stop-trigger close.  Non-null
  `protective_stop_or_null` has exact identities/product/side/quantity/trigger
  and `status=CONFIRMED_FIXTURE`.

- [ ] **Step 1: Write normal complete-cycle and old-byte RED tests**

Require exact event type order and payloads for both products.  Assert stop
trigger is evaluated before strategy exit and produces:

```python
decision = json.loads(result.decision_bytes)
self.assertEqual(decision["action"], "STOP_CLOSE_SPOT_LONG")
self.assertEqual(decision["reason_code"], "PROTECTIVE_STOP_TRIGGERED")
self.assertEqual(decision["risk_approval"], "REDUCE_ONLY")
```

Require Spot stop round-down, Perp stop round-up, stop cancel ACK before normal
close, reduce-only perpetual close, exact fee/funding/PnL and verified-flat
before reversal.  Add equality-boundary bars and gap-open fills.  Freeze the
exact canonical public v0.71 simulation outputs and require them to remain:

```text
FLAT:  length=2124, sha256=2a43ff164c0729808ef5b3f73da8415856d7d366cc7173407da091805d9bfd6d
LONG:  length=2388, sha256=f8e738ac45b4c99c8b574360b3545764d21b175a392a1c7ff0213fbb3fb23d98
SHORT: length=2377, sha256=ef5a5a0a2bdaf15980c72784863489f26591606c4f4e2cd4a1b8febf22580e7b
```

- [ ] **Step 2: Run Task 2 tests and record RED**

Run:

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_binance_lifecycle \
  tests.test_challenger_replacement_simulation -v
```

Expected: missing order/stop events, private v0.72 enriched stop identity and
stop-trigger action assertions fail against Task 1.

- [ ] **Step 3: Add a private v0.72 stop-before-strategy transition**

Keep public `simulate_challenger_replacement_opportunity(...)` and all v0.71
output bytes unchanged.  Add one private typed v0.72 transition, for example
`_simulate_challenger_replacement_v072_transition(...)`, used only by the
lifecycle reducer.  It derives the two exact stop actions from a validated
previous confirmed stop and completed bar.  The caller receives no override
parameter.  Share private `_fill_price`, quantity, fee and signed-accounting
formulas; do not duplicate them in the lifecycle module and do not route the
released public function through the enriched result shape.

- [ ] **Step 4: Implement normal product-specific lifecycle**

The private normal observation boundary returns deterministic typed
observations for one immediate full fill.  Reduce them into exact intent,
submit, ACK, fill, order-reconcile, stop and lifecycle-reconcile events.
Derive every ID from frozen content.  For close, consume the stored stop
identity and require cancel ACK before the reduce close.

- [ ] **Step 5: Run Task 2 GREEN and product-adjacent tests**

Run:

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_binance_lifecycle \
  tests.test_challenger_replacement_simulation \
  tests.test_instruments tests.test_orders tests.test_ledger \
  tests.test_system_paper_broker -v
PYTHONPATH=src python3 -m compileall -q src/crypto_quant
git diff --check
```

Expected: normal lifecycle and existing generic primitives all pass without
changing System Paper behavior, and the three frozen v0.71 public byte
length/SHA pairs remain exact.

- [ ] **Step 6: Commit Task 2**

```bash
git add \
  src/crypto_quant/challenger_replacement_binance_lifecycle.py \
  src/crypto_quant/challenger_replacement_simulation.py \
  tests/test_challenger_replacement_binance_lifecycle.py \
  tests/test_challenger_replacement_simulation.py \
  tests/challenger_replacement_v3_fixtures.py
git commit -m "feat: simulate replacement order lifecycle"
```

### Task 3: Prove fault aggregation and independent reconciliation

**Files:**
- Modify: `src/crypto_quant/challenger_replacement_binance_lifecycle.py`
- Modify: `tests/test_challenger_replacement_binance_lifecycle.py`

**Interfaces:**
- Consumes: Task 2 private normal observation boundary.
- Produces private immutable `LifecycleObservation`, `EngineProjection`,
  `VenueProjection`, `LedgerProjection`; reducers `_reduce_engine(events)`,
  `_reduce_venue(observations, previous_position)`,
  `_reduce_ledger(previous_snapshot, accounting_transition)`; terminal
  `FAILED_CLOSED` and exact reason mapping.

- [ ] **Step 1: Write fixed fault RED tests**

Patch only the private normal observation boundary.  Cover fill-before-ACK,
exact/conflicting duplicate, partial fill, overfill, UNKNOWN timeout,
disconnect, late close/stop fill, wrong product/side, missing stop, failed
flatten and ledger mismatch.  Assert no public fault/scenario signature exists.

For later partial fill require exact:

```text
FILL(new cumulative)
→ STOP_CANCEL_REQUESTED(old)
→ STOP_CANCEL_ACKNOWLEDGED(old)
→ STOP_INTENT_PREPARED(new)
→ STOP_ACKNOWLEDGED(new)
```

Add RED tests for missing cancel ACK, missing new ACK, second fill before new
ACK, old-stop late fill, and exactly one final stop.  Require verified remaining
position only after quantity-exact stop rebuild; otherwise verified-flat or
UNRESOLVED with no protection claim.

- [ ] **Step 2: Write independent-projection RED tests**

Patch each completed reducer output separately and require
`LEDGER_POSITION_MISMATCH`.  Use identity assertions to prove no reducer accepts
or returns another reducer's type.  Re-run a new venue reducer instance on the
same observation tuple and require exact output; do not claim fresh-process
fault recovery.

```python
with patch.object(lifecycle, "_reduce_venue", return_value=tampered_venue):
    result = self.simulate_open()
self.assertEqual(result.status, "FAILED_CLOSED")
self.assertEqual(result.reason_code_or_null, "LEDGER_POSITION_MISMATCH")
```

- [ ] **Step 3: Run Task 3 tests and record RED**

Run:

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_binance_lifecycle -v
```

Expected: private observation and independent reducer behavior is absent.

- [ ] **Step 4: Implement minimal observation/reducer/failure logic**

Keep raw observations, normalized engine events and accounting transition as
three distinct inputs.  Normalize exact duplicate observations once.  Reject
conflict/decrease/overfill.  Implement the stop-replacement sequence and
terminal failure rules exactly.  The single reason is selected from
`UNRESOLVED_UNKNOWN`, `DUPLICATE_ECONOMIC_ORDER`,
`UNRECORDED_OR_CONFLICTING_FILL`, `LEDGER_POSITION_MISMATCH`,
`DISASTER_STOP_MISSING_OR_UNCONFIRMED`, or
`EVIDENCE_DURABILITY_OR_IDENTITY_FAILURE`; no generic exception text enters
evidence.  Do not import or extend a generic Broker.

- [ ] **Step 5: Verify Task 3 and enforce the first size gate**

Run:

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_binance_lifecycle \
  tests.test_challenger_replacement_simulation \
  tests.test_orders tests.test_ledger tests.test_risk -v
wc -l \
  src/crypto_quant/challenger_replacement_binance_lifecycle.py \
  src/crypto_quant/challenger_replacement_binance_simulation_input.py \
  src/crypto_quant/challenger_replacement_simulation.py
git diff --numstat v0.71.0^{}..HEAD -- src/crypto_quant
python3 - <<'PY'
from pathlib import Path
baseline = {
    "challenger_replacement_binance_lifecycle.py": 0,
    "challenger_replacement_fixture_simulation.py": 0,
    "challenger_replacement_binance_simulation_input.py": 385,
    "challenger_replacement_simulation.py": 517,
    "challenger_replacement_opportunity_evidence.py": 147,
    "challenger_replacement_opportunity_projection.py": 447,
    "challenger_replacement_opportunities.py": 296,
}
root = Path("src/crypto_quant")
current = {name: len((root / name).read_text().splitlines()) for name in baseline}
assert all(lines <= 700 for lines in current.values()), current
delta = sum(max(0, current[name] - baseline[name]) for name in baseline)
print({"baseline_total": 1792, "current": current, "conservative_net_new": delta})
assert delta <= 1500, delta
PY
PYTHONPATH=src python3 -m compileall -q src/crypto_quant
git diff --check
```

Expected: tests pass and both modules are at most 700 lines.  Calculate actual
net-new production lines.  If the projected 1,500-line total cannot contain
Tasks 4-6, stop and design a semantic split before continuing.

- [ ] **Step 6: Commit Task 3**

```bash
git add \
  src/crypto_quant/challenger_replacement_binance_lifecycle.py \
  tests/test_challenger_replacement_binance_lifecycle.py
git commit -m "feat: fail closed on lifecycle ambiguity"
```

### Task 4: Add strict result evidence v2 without changing v1 bytes

**Files:**
- Create: `config/challenger-replacement-opportunity-result-evidence-v2.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-opportunity-result-evidence-v2.schema.json`
- Modify: `src/crypto_quant/challenger_replacement_opportunity_evidence.py`
- Modify: `tests/test_challenger_replacement_opportunity_evidence.py`

**Interfaces:**
- Consumes: `ChallengerReplacementLifecycleResult` only.
- Produces:

```python
def build_challenger_replacement_simulation_result_evidence(
    *, lifecycle_result: ChallengerReplacementLifecycleResult
) -> dict

def load_challenger_replacement_simulation_result_evidence_bytes(
    data: bytes, *, plan, contract, build_identity
) -> dict
```

The builder derives plan/contract/build/opportunity/source/observed time,
action, PnL, outcome, lifecycle status and next snapshot from the typed result;
it accepts no corresponding caller arguments.  The loader receives expected
plan/contract/build values only to verify the canonical document against the
caller's trust context; they cannot change its bytes.

- [ ] **Step 1: Write v2 schema/codec RED tests**

Require mirrored schema bytes, exact top-level key set, constants, full
plan/contract/build/source/decision/previous snapshot/lifecycle/accounting/next
snapshot bindings and self-hash.  Check 0-byte and >1-MiB rejection before
parse, duplicate keys, float, unsafe integer, malformed Decimal, unknown field,
wrong derived ID/hash, wrong event parent and exact authority mutations.

Keep every existing v1 fixture byte and loader test unchanged.  Add a static
signature test that caller PnL/action/status/outcome parameters do not exist.

- [ ] **Step 2: Run Task 4 tests and record RED**

Run:

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_opportunity_evidence -v
```

Expected: missing v2 schema and public codec APIs.

- [ ] **Step 3: Implement strict v1/v2 dispatch**

Preserve the v1 functions byte-for-byte in behavior.  Add a distinct cached v2
validator, typed builder and bounded canonical loader.  Construct the document
field-by-field from the lifecycle result; never serialize caller mappings.
Use the existing canonical duplicate-key/float rejection and self-hash helpers.

- [ ] **Step 4: Run Task 4 GREEN**

Run:

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_opportunity_evidence \
  tests.test_challenger_replacement_binance_lifecycle \
  tests.test_challenger_replacement_opportunities -v
cmp \
  config/challenger-replacement-opportunity-result-evidence-v2.schema.json \
  src/crypto_quant/schemas/challenger-replacement-opportunity-result-evidence-v2.schema.json
PYTHONPATH=src python3 -m compileall -q src/crypto_quant
git diff --check
```

- [ ] **Step 5: Commit Task 4**

```bash
git add \
  config/challenger-replacement-opportunity-result-evidence-v2.schema.json \
  src/crypto_quant/schemas/challenger-replacement-opportunity-result-evidence-v2.schema.json \
  src/crypto_quant/challenger_replacement_opportunity_evidence.py \
  tests/test_challenger_replacement_opportunity_evidence.py
git commit -m "feat: validate replacement lifecycle evidence"
```

### Task 5: Bind v2 results to the sole opportunity projection and runner

**Files:**
- Create: `src/crypto_quant/challenger_replacement_fixture_simulation.py`
- Create: `tests/test_challenger_replacement_fixture_simulation.py`
- Modify: `src/crypto_quant/challenger_replacement_opportunity_projection.py`
- Modify: `src/crypto_quant/challenger_replacement_opportunities.py`
- Modify: `tests/test_challenger_replacement_opportunities.py`

**Interfaces:**
- Consumes: strict input bytes loader, Task 3 lifecycle, Task 4 v2 evidence,
  `ChallengerReplacementOpportunityState.append(...)` with optimistic token.
- Produces:

```python
def run_challenger_replacement_fixture_simulation_opportunity(
    *, state: ChallengerReplacementOpportunityState,
    input_bytes: bytes,
    worker_id: str,
) -> dict
```

Return value is the public terminal projection/result loaded from canonical
event bytes.  It has no path/time/price/fault/scenario callback.

- [ ] **Step 1: Write projection and terminal RED tests**

Cover v2 genesis, second opportunity snapshot parent, failed lifecycle OBSERVED,
flat MISSED, non-flat MISSED economic-gap lock, v1/v2 root/build mixing and exact
v1 replay.  Add the blocking regression: v2 `RESULT_PREPARED` followed by
expired catch-up must raise
`CHALLENGER_REPLACEMENT_OPPORTUNITY_ACTIVE_CONFLICT`, then resume only to
OBSERVED.  INPUT-only catch-up keeps its existing permitted MISSED behavior.

- [ ] **Step 2: Write runner RED tests**

Require malformed/unbound bytes to fail before INPUT with zero events.  For a
valid input require exact INPUT→RESULT→OBSERVED, prior v2 snapshot selection,
zero authority and no caller overrides.  Re-running an already-terminal exact
input returns stored bytes with zero append/build/compute.

- [ ] **Step 3: Run Task 5 tests and record RED**

Run:

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_fixture_simulation \
  tests.test_challenger_replacement_opportunities \
  tests.test_challenger_replacement_opportunity_evidence -v
```

Expected: missing runner, v2 projection and RESULT→MISSED guard.

- [ ] **Step 4: Implement minimal v2 projection dispatch**

Dispatch only on exact schema/version.  Store latest v2 next snapshot as a
private projection value and expose only its strict public copy.  Reject v2
RESULT catch-up without changing committed v1 replay.  Do not duplicate the
event state machine in the facade or runner.

- [ ] **Step 5: Implement the thin fixture runner**

Validate input before append.  Replay before every stage and pass the exact
last-event hash.  Derive recorded time/opportunity from canonical input.  After
INPUT, reuse embedded source bytes.  After RESULT, load embedded decision/result
without recompute.  After terminal, return stored projection.  Propagate stale
sequence conflict; do not catch/rebase it.

- [ ] **Step 6: Verify Task 5 and enforce the final implementation size gate**

Run:

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_fixture_simulation \
  tests.test_challenger_replacement_opportunities \
  tests.test_challenger_replacement_opportunity_evidence \
  tests.test_challenger_replacement_binance_lifecycle \
  tests.test_challenger_replacement_events \
  tests.test_challenger_replacement_plan_v3 -v
wc -l \
  src/crypto_quant/challenger_replacement_binance_lifecycle.py \
  src/crypto_quant/challenger_replacement_fixture_simulation.py \
  src/crypto_quant/challenger_replacement_binance_simulation_input.py \
  src/crypto_quant/challenger_replacement_simulation.py \
  src/crypto_quant/challenger_replacement_opportunity_evidence.py \
  src/crypto_quant/challenger_replacement_opportunity_projection.py \
  src/crypto_quant/challenger_replacement_opportunities.py
git diff --numstat v0.71.0^{}..HEAD -- \
  src/crypto_quant/challenger_replacement_binance_lifecycle.py \
  src/crypto_quant/challenger_replacement_fixture_simulation.py \
  src/crypto_quant/challenger_replacement_binance_simulation_input.py \
  src/crypto_quant/challenger_replacement_simulation.py \
  src/crypto_quant/challenger_replacement_opportunity_evidence.py \
  src/crypto_quant/challenger_replacement_opportunity_projection.py \
  src/crypto_quant/challenger_replacement_opportunities.py
python3 - <<'PY'
from pathlib import Path
baseline = {
    "challenger_replacement_binance_lifecycle.py": 0,
    "challenger_replacement_fixture_simulation.py": 0,
    "challenger_replacement_binance_simulation_input.py": 385,
    "challenger_replacement_simulation.py": 517,
    "challenger_replacement_opportunity_evidence.py": 147,
    "challenger_replacement_opportunity_projection.py": 447,
    "challenger_replacement_opportunities.py": 296,
}
root = Path("src/crypto_quant")
current = {name: len((root / name).read_text().splitlines()) for name in baseline}
assert all(lines <= 700 for lines in current.values()), current
delta = sum(max(0, current[name] - baseline[name]) for name in baseline)
print({"baseline_total": 1792, "current": current, "conservative_net_new": delta})
assert delta <= 1500, delta
PY
PYTHONPATH=src python3 -m compileall -q src/crypto_quant
git diff --check
```

Expected: selected tests pass, every module ≤700 lines and the conservative
net-new production count is ≤1,500.  The exact frozen baseline map totals 1,792
physical lines.  The formula is
`sum(max(0, current[path] - baseline[path]) for path in exact_seven_modules)`;
therefore unrelated deletion or moving code between modules cannot create
budget credit.  `git diff --numstat` is diagnostic only.  If the gate fails,
stop before Task 6/artifacts.

- [ ] **Step 7: Commit Task 5**

```bash
git add \
  src/crypto_quant/challenger_replacement_fixture_simulation.py \
  src/crypto_quant/challenger_replacement_opportunity_projection.py \
  src/crypto_quant/challenger_replacement_opportunities.py \
  tests/test_challenger_replacement_fixture_simulation.py \
  tests/test_challenger_replacement_opportunities.py
git commit -m "feat: bind lifecycle results to opportunities"
```

### Task 6: Prove crash, exact retry and true-process concurrency

**Files:**
- Modify: `tests/test_challenger_replacement_fixture_simulation.py`
- Modify only if RED proves necessary:
  `src/crypto_quant/challenger_replacement_fixture_simulation.py`
- Modify only if RED proves necessary:
  `src/crypto_quant/challenger_replacement_opportunity_projection.py`

**Interfaces:**
- Consumes: Task 5 runner and existing event durability protocol.
- Produces no new public API.

- [ ] **Step 1: Write fresh-interpreter crash RED tests**

Use subprocesses and owner-only temporary event roots.  Patch existing private
append/build/compute boundaries in child processes only.  Cover crash after
INPUT, after RESULT and after OBSERVED.  Require:

```text
after INPUT: source recapture count 0
after RESULT: decision/lifecycle/accounting recompute count 0
after OBSERVED: append/build/recompute count 0
```

Add RESULT-visible-before-OBSERVED then expired catch-up: catch-up conflicts and
fresh resume terminalizes OBSERVED with exact result.

- [ ] **Step 2: Write true two-process race RED tests**

Use a cross-process barrier by patching the existing private append boundary.
For one exact event require `{COMMITTED, ALREADY_COMMITTED}`.  For two complete
runners require one terminal success and one
`CHALLENGER_REPLACEMENT_OPPORTUNITY_SEQUENCE_CONFLICT`; a separate later exact
invocation returns stored terminal result.  Replay has one intent/fill set.

- [ ] **Step 3: Run Task 6 tests and record RED**

Run:

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_fixture_simulation -v
```

- [ ] **Step 4: Apply only minimal recovery corrections proven by RED**

Do not add production fault callbacks, retry loops or orchestration enums.  Use
existing replay, event bytes and optimistic conflict.  Preserve the exact
single-event/whole-runner distinction.

- [ ] **Step 5: Run Task 6 GREEN and event-adjacent suite**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_fixture_simulation \
  tests.test_challenger_replacement_opportunities \
  tests.test_challenger_replacement_events -v
PYTHONPATH=src python3 -m compileall -q src/crypto_quant
git diff --check
```

- [ ] **Step 6: Commit Task 6**

```bash
git add \
  tests/test_challenger_replacement_fixture_simulation.py \
  src/crypto_quant/challenger_replacement_fixture_simulation.py \
  src/crypto_quant/challenger_replacement_opportunity_projection.py
git commit -m "test: prove lifecycle crash recovery"
```

### Task 7: Publish deterministic complete-cycle goldens

**Files:**
- Create: `config/challenger-replacement-binance-golden-fixture-manifest-v1.schema.json`
- Create:
  `artifacts/challenger-replacement/challenger-replacement-binance-golden-fixture-manifest-v0.72.0.json`
- Create: `tests/fixtures/challenger_replacement_v072/spot-cycle/*.json`
- Create: `tests/fixtures/challenger_replacement_v072/perp-cycle/*.json`
- Create: `tests/test_challenger_replacement_v072_artifacts.py`
- Modify: `tests/challenger_replacement_v3_fixtures.py`
- Modify: `src/crypto_quant/build.py`

**Interfaces:**
- Consumes: Tasks 1-6 strict loaders and fixture runner.
- Produces one formal ordered fixture manifest and two portable canonical streams.

- [ ] **Step 1: Add pre-artifact RED tests**

Freeze exact paths and ordered inventory:

```text
spot-cycle/01-input.json
spot-cycle/02-result.json
spot-cycle/03-input.json
spot-cycle/04-result.json
spot-cycle/05-input.json
spot-cycle/06-result.json
perp-cycle/01-input.json
perp-cycle/02-result.json
perp-cycle/03-input.json
perp-cycle/04-result.json
perp-cycle/05-input.json
perp-cycle/06-result.json
perp-cycle/07-input.json
perp-cycle/08-result.json
```

Require missing formal manifest/result paths to fail.  Freeze schema, ordered
path/SHA/size, contract hash, fixture-only build identity and manifest self-hash.

- [ ] **Step 2: Run pre-artifact tests and record RED**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_v072_artifacts -v
```

Expected: exact files are missing.

- [ ] **Step 3: Generate and independently reproduce canonical fixtures**

Use only the committed fixture builders and owner-only temp event roots.  First
generate the fixed canonical input files and strict-load them with the input-v1
loader.  Run each complete stream independently in two fresh owner-only event
roots and fresh interpreter processes.  Require candidate result bytes from
the two runs to be byte-identical, then strict-load and replay both candidates.
Only after this independent equality gate may the exact candidate bytes be
added, using `apply_patch`/repository no-overwrite publication, to the fixed
result paths.  Run a third fresh root/process and require its results to equal
the now-committed result bytes.  No step compares against a result file before
that file exists, and no JSON is edited manually.

- [ ] **Step 4: Build and publish the exact manifest**

Construct sorted fixed inventory, lengths and SHA-256, contract identity and
self-hash.  Publish with repository no-overwrite semantics.  Add the schema,
formal manifest and fixture paths to the build manifest expected paths without
embedding future commit/tag/CI identity.  Introduce exact
`_V072_RELEASE_PATHS` in `src/crypto_quant/build.py` containing:

```text
config/challenger-replacement-opportunity-result-evidence-v2.schema.json
config/challenger-replacement-binance-golden-fixture-manifest-v1.schema.json
artifacts/challenger-replacement/challenger-replacement-binance-golden-fixture-manifest-v0.72.0.json
tests/fixtures/challenger_replacement_v072/spot-cycle/01-input.json
tests/fixtures/challenger_replacement_v072/spot-cycle/02-result.json
tests/fixtures/challenger_replacement_v072/spot-cycle/03-input.json
tests/fixtures/challenger_replacement_v072/spot-cycle/04-result.json
tests/fixtures/challenger_replacement_v072/spot-cycle/05-input.json
tests/fixtures/challenger_replacement_v072/spot-cycle/06-result.json
tests/fixtures/challenger_replacement_v072/perp-cycle/01-input.json
tests/fixtures/challenger_replacement_v072/perp-cycle/02-result.json
tests/fixtures/challenger_replacement_v072/perp-cycle/03-input.json
tests/fixtures/challenger_replacement_v072/perp-cycle/04-result.json
tests/fixtures/challenger_replacement_v072/perp-cycle/05-input.json
tests/fixtures/challenger_replacement_v072/perp-cycle/06-result.json
tests/fixtures/challenger_replacement_v072/perp-cycle/07-input.json
tests/fixtures/challenger_replacement_v072/perp-cycle/08-result.json
tests/test_challenger_replacement_binance_lifecycle.py
tests/test_challenger_replacement_fixture_simulation.py
tests/test_challenger_replacement_v072_artifacts.py
tests/test_challenger_replacement_v072_release.py
docs/superpowers/specs/2026-08-25-binance-lifecycle-evidence-design.md
docs/superpowers/plans/2026-08-25-binance-lifecycle-evidence.md
docs/adr/0072-binance-lifecycle-evidence.md
docs/implementation-status-v0.72.0.md
```

Files already present in earlier release-path sets remain there and are not
duplicated.  The v0.72 release regression asserts every exact path above is in
the manifest with matching bytes/hash; package Python files and mirrored
package schemas continue to enter through the existing automatic inventory.

- [ ] **Step 5: Run artifact replay and tamper tests**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_v072_artifacts \
  tests.test_challenger_replacement_fixture_simulation \
  tests.test_challenger_replacement_opportunity_evidence -v
git diff --check
```

Require wrong byte/path/order/hash/schema/contract and extra file to fail.

- [ ] **Step 6: Commit Task 7**

```bash
git add \
  config/challenger-replacement-binance-golden-fixture-manifest-v1.schema.json \
  artifacts/challenger-replacement/challenger-replacement-binance-golden-fixture-manifest-v0.72.0.json \
  tests/fixtures/challenger_replacement_v072 \
  tests/test_challenger_replacement_v072_artifacts.py \
  tests/challenger_replacement_v3_fixtures.py \
  src/crypto_quant/build.py
git commit -m "test: freeze lifecycle golden cycles"
```

### Task 8: Finalize v0.72 candidate and release evidence

**Files:**
- Create: `docs/adr/0072-binance-lifecycle-evidence.md`
- Create: `docs/implementation-status-v0.72.0.md`
- Create: `tests/test_challenger_replacement_v072_release.py`
- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `setup.py`
- Modify: `src/crypto_quant/__init__.py`
- Modify: `src/crypto_quant/build.py`
- Modify: `src/crypto_quant/challenger_replacement_deployment.py`
- Modify: `config/evaluator-build-manifest-v1.json`
- Modify: `scripts/refresh_evaluator_build_manifest.py`
- Modify current-manifest expectations only in:
  `tests/test_estimators.py`,
  `tests/test_challenger_replacement_v066_release.py`,
  `tests/test_challenger_replacement_v067_release.py`,
  `tests/test_challenger_replacement_v068_release.py`,
  `tests/test_challenger_replacement_v069_release.py`,
  `tests/test_challenger_replacement_v070_release.py`,
  `tests/test_challenger_replacement_v071_release.py`,
  `tests/test_nautilus_v065_release.py`,
  `tests/test_nautilus_v0651_hardening.py`, and
  `tests/test_v064_public_ci_bundle.py`.

**Interfaces:**
- Consumes: final Tasks 1-7 code/artifacts and released predecessor identities.
- Produces package `0.72.0`, manifest `1.66.0`, exact candidate/final status and
  release evidence.  No installation/start artifact is produced.

- [ ] **Step 1: Write candidate release RED tests**

Require package/manifest versions, expected file set, exact predecessor hashes,
formal artifact replay, each module ≤700, net-new production ≤1,500, no forbidden
imports/signatures, exact status and no seven-day/90-day clock claim.  Initially
require candidate verification fields `PENDING_VERIFICATION`.  Hard-code the
exact seven-module baseline map `{lifecycle: 0, fixture_runner: 0,
simulation_input: 385, simulation: 517, evidence: 147, projection: 447,
opportunities: 296}` and the conservative
per-module positive-delta formula used in Tasks 3 and 5; `numstat` alone is not
an acceptance gate.

- [ ] **Step 2: Run release tests and record RED**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_v072_release -v
```

- [ ] **Step 3: Add candidate metadata and documentation**

ADR records selected thin lifecycle and rejected generic/monolith alternatives.
Status separates local tests, review, PR CI, main CI and tag identity.  README
states fixture lifecycle verified only after evidence exists and explicitly
states no install/start/account/credential/order/funds/Paper/profitability claim.
Update versions and regenerate the manifest only with the reviewed builder.

- [ ] **Step 4: Run focused and adjacent final tests**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_v072_release \
  tests.test_challenger_replacement_v072_artifacts \
  tests.test_challenger_replacement_fixture_simulation \
  tests.test_challenger_replacement_binance_lifecycle \
  tests.test_challenger_replacement_opportunity_evidence \
  tests.test_challenger_replacement_opportunities \
  tests.test_challenger_replacement_events \
  tests.test_challenger_replacement_simulation \
  tests.test_challenger_replacement_plan_v3 -v
```

- [ ] **Step 5: Run the one final local verification state**

Run once, without repeating on unchanged code:

```bash
python3 -m unittest discover -s tests
PYTHONPATH=src python3 -m compileall -q src/crypto_quant
make validate
git diff --check
git status --short
```

Record exact test count/skips/time/exit codes.  `make validate` must exit zero;
its internal production-activation report must remain fail-closed/disabled.

- [ ] **Step 6: Run one independent complete review**

Reviewer compares `v0.71.0^{}..HEAD` against the spec and this plan.  It reports
Critical/Important/Minor with file/line evidence and explicitly checks stop
replacement, UNKNOWN, three independent projections, RESULT→MISSED,
whole-runner concurrency, v1 replay, size budget and zero authority.  Fix every
Critical/Important through focused RED/GREEN tests; use only targeted re-review.

- [ ] **Step 7: Convert candidate status to exact final local evidence**

After local verification/review actually pass, replace only the corresponding
`PENDING_VERIFICATION` fields with their exact evidence, regenerate the build
manifest, rerun release/status/manifest tests, compileall and diff-check.  Do not
rerun the unchanged full suite.

- [ ] **Step 8: Commit the final candidate**

```bash
git add \
  docs/adr/0072-binance-lifecycle-evidence.md \
  docs/implementation-status-v0.72.0.md \
  tests/test_challenger_replacement_v072_release.py \
  README.md pyproject.toml setup.py \
  src/crypto_quant/__init__.py src/crypto_quant/build.py \
  src/crypto_quant/challenger_replacement_deployment.py \
  config/evaluator-build-manifest-v1.json \
  scripts/refresh_evaluator_build_manifest.py \
  tests/test_estimators.py \
  tests/test_challenger_replacement_v066_release.py \
  tests/test_challenger_replacement_v067_release.py \
  tests/test_challenger_replacement_v068_release.py \
  tests/test_challenger_replacement_v069_release.py \
  tests/test_challenger_replacement_v070_release.py \
  tests/test_challenger_replacement_v071_release.py \
  tests/test_nautilus_v065_release.py \
  tests/test_nautilus_v0651_hardening.py \
  tests/test_v064_public_ci_bundle.py
git commit -m "chore: prepare v0.72.0 release"
```

- [ ] **Step 9: Complete the already-authorized public release ceremony**

Before each remote write verify public repo identity, `origin`, `ADMIN`, clean
worktree, branch head and that `origin/main` still equals the expected base.
Push branch, create Draft PR, require Python 3.9/3.12 and macOS arm64 PR CI.
Mark ready and merge only exact reviewed head using the repository's merge
commit method.  Require merged-main CI for exact merge SHA.  Only then create
and push an annotated `v0.72.0`; verify:

```text
origin/main == refs/tags/v0.72.0^{}
refs/tags/v0.72.0 is an annotated tag object
PR head == exact reviewed candidate head
PR CI == success
main CI == success for exact main SHA
```

Any test/review/CI/identity failure stops release without moving or replacing a
tag.  A successful v0.72 release still authorizes no install/start or trade.

## Execution decision

The user's long-running authorization requests autonomous continuation and no
repeated approval prompts.  Execute this plan inline with
`superpowers:executing-plans`, task by task, with durable checkpoints and the
specified independent read-only reviews.  Do not dispatch new implementation
agents or run tasks concurrently against shared files.
