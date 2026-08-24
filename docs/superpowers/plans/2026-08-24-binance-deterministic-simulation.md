# Binance Deterministic Simulation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fixture-only, deterministic Binance ETHUSDT Spot-long / USDⓈ-M perpetual-short simulation whose complete lifecycle is replayable from the replacement canonical event log without adding network, account, credential, Broker, real-order, install, or start authority.

**Architecture:** Preserve the v0.70 opportunity facade, extract its single event projection implementation, and add narrow v0.71 modules for the immutable simulation contract, strict fixture input, and signed accounting/lifecycle engine. The engine consumes only canonical bytes and a retained fixture event-root capability; the append-only event log remains the sole authority, while snapshots and results are deterministic projections. Formal contract and golden artifacts are generated only after their schemas, builders, loaders, and tests pass.

**Tech Stack:** Python 3.9-compatible stdlib, `Decimal`, existing canonical/event/instrument/order primitives, JSON Schema Draft 2020-12, `unittest`, Git/GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-24-binance-deterministic-simulation-design.md`

## Global Constraints

- Base is annotated `v0.70.0`, peeled commit `50c41c847c49771dfd169778c850d270fab794c8`.
- v0.69 plan bytes/hash and v0.70 event envelope/durability protocol remain unchanged.
- Only `v0.71.0-fixture` mappings are accepted before release; they are semantic bindings, not release provenance.
- Tests use fresh owner-only fixture event roots; no v0.70/v0.71 event mixing or migration.
- No network, SDK, system clock, arbitrary path, account, credential, Broker, real/testnet order, production root, install, start, scheduler, Runner, UI, or timer.
- All economic arithmetic uses exact `Decimal`; no float, random, AI, training, or caller-supplied PnL/outcome.
- Normal fixtures use immediate full fills; faults patch existing private boundaries only. No production fault callback, enum, environment switch, or command seam.
- Canonical event log is the sole authority; exports and in-memory snapshots are projections.
- Every new production module must remain at or below 700 physical lines. The reproducible v0.71 production budget is: current physical lines across exactly `challenger_replacement_opportunities.py`, `challenger_replacement_opportunity_evidence.py`, `challenger_replacement_opportunity_projection.py`, `challenger_replacement_simulation_contract.py`, `challenger_replacement_binance_simulation_input.py`, and `challenger_replacement_simulation.py`, minus the v0.70 baseline of 843 lines for the first two existing modules. The result must be at most 1,200. This counts edits to existing modules and makes a pure projection move net zero; schemas/tests/docs are excluded. A checked release test implements this exact formula, reports every component, and forbids unrelated production deletions from being credited. Crossing the limit stops v0.71 and triggers a semantic split.
- Each task follows exact RED -> minimal GREEN -> refactor and ends in a focused commit.
- Run the local full suite only once for the final code state. Do not repeat full review or full suite on unchanged code.

---

### Task 1: Freeze the simulation contract and artifact schema

**Files:**
- Create: `config/challenger-replacement-simulation-contract-v1.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-simulation-contract-v1.schema.json`
- Create: `src/crypto_quant/challenger_replacement_simulation_contract.py`
- Create: `tests/test_challenger_replacement_simulation_contract.py`
- Modify: `tests/challenger_replacement_v3_fixtures.py`

**Interfaces:**
- Consumes: `load_challenger_replacement_plan_v3`, `canonical_json`, `artifact_self_hash`, `_strict_json_bytes`.
- Produces: `build_challenger_replacement_simulation_contract(*, plan) -> dict` and `load_challenger_replacement_simulation_contract_bytes(data: bytes, *, plan) -> dict`. v0.71 exposes no path loader; committed-artifact tests read the one fixed repository path and pass its bytes to the loader.

- [ ] **Step 1: Write strict-schema and constant RED tests**

Add tests that require exact keys, mirrored schema bytes, exact v0.69 plan ID/hash/file SHA, mode/venue/asset, `100`, `0.5`, configured leverage `1`, cap `2`, slippage `0.001`, both taker fees `0.0015`, stop distance `0.02`, quote quantum `0.00000001`, all zero-authority fields, stable ID/self-hash, canonical bytes, and rejection of unknown keys, float, changed fee, changed plan, noncanonical newline, and prefilled release commit/tag fields.

```python
def test_contract_freezes_exact_fixture_only_assumptions(self):
    contract = build_challenger_replacement_simulation_contract(
        plan=fixture_v3_plan()
    )
    self.assertEqual(contract["mode"], "FIXTURE_ONLY_DETERMINISTIC_BINANCE_SIMULATION")
    self.assertEqual(contract["configured_leverage"], "1")
    self.assertEqual(contract["gross_exposure_limit"], "0.5")
    self.assertFalse(contract["authority"]["credentials_allowed"])
```

- [ ] **Step 2: Run the contract tests and observe RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_simulation_contract -v`

Expected: import/schema failure because the v0.71 contract module and schema do not exist.

- [ ] **Step 3: Implement the minimal strict builder/bytes loader**

Use one private `_document(plan)` constructor, cached Draft 2020-12 validator, exact-key equality, canonical-byte equality, 64 KiB size bound, stable ID, and self-hash. Do not accept build identity, time, fee, path, or authority arguments.

- [ ] **Step 4: Run focused and adjacent contract tests**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_simulation_contract tests.test_challenger_replacement_plan_v3 -v
PYTHONPATH=src python3 -m compileall -q src/crypto_quant
git diff --check
```

Expected: all selected tests pass; compile and diff checks exit 0.

- [ ] **Step 5: Commit Task 1**

```bash
git add config/challenger-replacement-simulation-contract-v1.schema.json src/crypto_quant/schemas/challenger-replacement-simulation-contract-v1.schema.json src/crypto_quant/challenger_replacement_simulation_contract.py tests/test_challenger_replacement_simulation_contract.py tests/challenger_replacement_v3_fixtures.py
git commit -m "feat: freeze replacement simulation contract"
```

### Task 2: Add strict committed-fixture input

**Files:**
- Create: `config/challenger-replacement-binance-simulation-input-v1.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-binance-simulation-input-v1.schema.json`
- Create: `src/crypto_quant/challenger_replacement_binance_simulation_input.py`
- Create: `tests/test_challenger_replacement_binance_simulation_input.py`
- Modify: `tests/challenger_replacement_v3_fixtures.py`

**Interfaces:**
- Consumes: v0.69 plan, Task 1 contract, `InstrumentMetadata`, canonical time/Decimal/hash helpers.
- Produces only the production loader `load_challenger_replacement_binance_simulation_input_bytes(data: bytes, *, plan, contract, build_identity, opportunity_id) -> dict`. Deterministic input-document construction remains in `tests/challenger_replacement_v3_fixtures.py`; production exposes no separate price/bar/time builder.

- [ ] **Step 1: Write source validation RED tests**

Cover exactly 21 closed UTC 4h bars, last close boundary equals `scheduled_for`, OHLC ordering, positive prices, bid/last/ask ordering, positive perp mark, exact Spot/USDT_PERP IDs, unique effective metadata, multiplier, taker-fee equality with the contract, paired funding null/value fields, `COMMITTED_FIXTURE_NOT_LIVE_MARKET`, build hash, and all zero authority counts.

```python
def test_input_rejects_metadata_fee_conflict(self):
    metadata = fixture_v071_spot_metadata(taker_fee="0.001")
    with self.assertRaisesRegex(
        ChallengerReplacementSimulationInputError,
        "SIMULATION_CONTRACT_METADATA_CONFLICT",
    ):
        load_challenger_replacement_binance_simulation_input_bytes(
            fixture_v071_input_bytes(spot_metadata=metadata),
            plan=fixture_v3_plan(),
            contract=fixture_v071_contract(),
            build_identity=fixture_v071_build_identity(),
            opportunity_id=fixture_opportunity_id(),
        )
```

Also reject missing/extra/reordered bars, open latest bar, noncanonical Decimal/time, wrong multiplier/hash/window, socket/network attempts, and arbitrary caller outcome/PnL fields.

- [ ] **Step 2: Run the input tests and observe RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_binance_simulation_input -v`

Expected: import/schema failure for the missing input implementation.

- [ ] **Step 3: Implement the minimal byte loader**

Reuse `InstrumentMetadata.business_payload()` and validate the canonical payload/hash rather than adding a second metadata model. Tests build deterministic canonical bytes in the test fixture module. Production accepts only the complete canonical bytes plus frozen binding identities; it never exposes separate price/time inputs and never reads disk, time, environment, network, or account state.

- [ ] **Step 4: Run focused/adjacent tests and static side-effect checks**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_binance_simulation_input tests.test_instruments tests.test_challenger_replacement_opportunities -v
rg -n "requests|urllib|httpx|aiohttp|socket|keyring|subprocess|sqlite3|random" src/crypto_quant/challenger_replacement_binance_simulation_input.py
PYTHONPATH=src python3 -m compileall -q src/crypto_quant
git diff --check
```

Expected: tests pass; the static scan has no runtime imports/calls for the forbidden facilities.

- [ ] **Step 5: Commit Task 2**

```bash
git add config/challenger-replacement-binance-simulation-input-v1.schema.json src/crypto_quant/schemas/challenger-replacement-binance-simulation-input-v1.schema.json src/crypto_quant/challenger_replacement_binance_simulation_input.py tests/test_challenger_replacement_binance_simulation_input.py tests/challenger_replacement_v3_fixtures.py
git commit -m "feat: validate Binance simulation fixtures"
```

### Task 3: Extract the single opportunity projection without behavior change

**Files:**
- Create: `src/crypto_quant/challenger_replacement_opportunity_projection.py`
- Modify: `src/crypto_quant/challenger_replacement_opportunities.py`
- Modify: `tests/test_challenger_replacement_opportunities.py`

**Interfaces:**
- Consumes: existing v0.70 opportunity/event semantics.
- Produces internal `initial_opportunity_projection(*, plan, build_identity) -> dict` and `apply_opportunity_event(projection, event, *, plan, build_identity) -> None`; preserves every existing public import from `challenger_replacement_opportunities.py`.

- [ ] **Step 1: Add behavior-preservation RED/static tests**

Freeze all public names, root-independent semantic projection bytes for the existing v1 fixture sequence, MISSED/OBSERVED terminal behavior, optimistic hash conflicts, and fixture build validation. Before moving code, define a test-only `v070_semantic_projection` that selects exactly: active/first/last/next/terminal schedules; terminal/observed/missed/consecutive/delay counters; reason counts; and, for each opportunity, only `stage`, `outcome`, `scheduled_for`, `capture_open`, `capture_close`, source/decision/result SHA-256, `reason_code`, and `detected_at` when present. It must exclude `events`, event hashes/sequences, raw bytes, last-event hash, next sequence, and orphan/root fields. Capture and hard-code that canonical semantic mapping's bytes/SHA-256 before moving code. Existing event-codec tests separately retain exact event validation. Add a static assertion that the facade remains at or below its pre-task 696 lines and contains no duplicate `_apply_event` state machine.

```python
def test_extracted_projection_replays_committed_v070_bytes_exactly(self):
    projection = v070_semantic_projection(
        replay_with_projection_module(existing_v070_fixture_sequence())
    )
    actual = canonical_json(projection).encode("utf-8")
    self.assertEqual(actual, V070_SEMANTIC_PROJECTION_BYTES)
    self.assertEqual(hashlib.sha256(actual).hexdigest(), V070_SEMANTIC_PROJECTION_SHA256)
```

- [ ] **Step 2: Run the extraction tests and observe RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_opportunities -v`

Expected: failure because the projection module/functions do not yet exist.

- [ ] **Step 3: Move, do not duplicate, the projection implementation**

Move the existing projection initialization/apply validation into the focused module, import it from the facade, preserve reason codes and public behavior, and delete the original duplicate functions. Do not add v2 behavior in this step.

- [ ] **Step 4: Verify exact v0.70 behavior and line budgets**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_opportunities tests.test_challenger_replacement_events tests.test_challenger_replacement_opportunity_evidence -v
wc -l src/crypto_quant/challenger_replacement_opportunities.py src/crypto_quant/challenger_replacement_opportunity_projection.py
PYTHONPATH=src python3 -m compileall -q src/crypto_quant
git diff --check
```

Expected: all tests pass; facade line count does not increase; no production module exceeds 700 lines.

- [ ] **Step 5: Commit Task 3**

```bash
git add src/crypto_quant/challenger_replacement_opportunity_projection.py src/crypto_quant/challenger_replacement_opportunities.py tests/test_challenger_replacement_opportunities.py
git commit -m "refactor: isolate opportunity projection"
```

### Task 4: Implement deterministic decision, snapshot, accounting, and risk

**Files:**
- Create: `src/crypto_quant/challenger_replacement_simulation.py`
- Create: `tests/test_challenger_replacement_simulation.py`
- Modify: `tests/challenger_replacement_v3_fixtures.py`

**Interfaces:**
- Consumes: validated input/contract, v0.69 decision policy, `InstrumentMetadata`, `RoundedOrderPlan`.
- Produces: `build_challenger_replacement_genesis_snapshot(*, plan, contract) -> dict`, `compute_challenger_replacement_simulation_decision(*, source, previous_projection, plan, contract) -> dict`, and `simulate_challenger_replacement_opportunity(*, source, previous_projection, plan, contract, build_identity) -> dict`.

- [ ] **Step 1: Add decision/snapshot/accounting RED tests**

Test long/short/flat, equality boundaries, 8h/24h exits, no same-opportunity reversal, FLAT/SPOT_LONG/PERP_SHORT mutual exclusion, VERIFIED/UNRESOLVED snapshots, parent/self hashes, and exact equations for cash, weighted entry, multiplier, Spot bid mark, perp mark, margin, realized/unrealized, funding, fees, equity, day start, high water, and drawdown.

```python
def test_short_profit_uses_negative_signed_quantity_once(self):
    result = simulate_perp_open_then_close(entry="2000", exit="1900")
    self.assertEqual(result["accounting"]["realized_pnl"], "2.5")
    self.assertGreater(Decimal(result["next_snapshot"]["cash"]), Decimal("100"))
```

Use fixture quantities that make the expected result exact after multiplier/fee rounding; store explicit expected canonical documents rather than recomputing expected values with production helpers.

- [ ] **Step 2: Add risk-sizing RED tests**

Require largest legal step lots from adverse rounded fills, post-fill gross exposure `<=0.5`, min/max/min-notional, margin availability, no pyramiding, drift reduction before strategy action, equality triggers at daily loss `2` and drawdown `5`, continuous high water, 00:00 baseline after stop/funding/mark, and risk recalculation after every fill/fee/funding/stop/flatten.

- [ ] **Step 3: Run the simulation tests and observe RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_simulation -v`

Expected: import/attribute failures for the missing simulator.

- [ ] **Step 4: Implement the pure state transition**

Implement small private Decimal helpers for adverse quote rounding, quote debit/credit rounding, largest-legal-lots search, signed accounting, and risk recomputation. Do not add generic Broker, exchange adapter, storage, time, network, callbacks, or configurable strategy abstractions.

- [ ] **Step 5: Verify Task 4 and enforce the YAGNI checkpoint**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_simulation tests.test_challenger_replacement_binance_simulation_input tests.test_instruments tests.test_orders -v
wc -l src/crypto_quant/challenger_replacement_simulation.py src/crypto_quant/challenger_replacement_simulation_contract.py src/crypto_quant/challenger_replacement_binance_simulation_input.py
git diff --numstat v0.70.0^{}..HEAD -- src/crypto_quant
PYTHONPATH=src python3 -m compileall -q src/crypto_quant
git diff --check
```

Expected: focused tests pass; each module is at most 700 lines. Calculate the exact six-module physical-line formula from Global Constraints. If the remaining allowance cannot contain the already enumerated Tasks 5-6 interfaces/tests, stop here and split the version before adding lifecycle integration.

- [ ] **Step 6: Commit Task 4**

```bash
git add src/crypto_quant/challenger_replacement_simulation.py tests/test_challenger_replacement_simulation.py tests/challenger_replacement_v3_fixtures.py
git commit -m "feat: simulate signed replacement positions"
```

### Task 5: Complete order, fill, stop, and reconciliation semantics

**Files:**
- Modify: `src/crypto_quant/challenger_replacement_simulation.py`
- Modify: `tests/test_challenger_replacement_simulation.py`

**Interfaces:**
- Consumes: Task 4 transition and existing `orders.py` aggregation primitives.
- Produces deterministic lifecycle arrays inside the Task 4 result: intent, order events, fills, fees, funding, protective stop, reconciliation, lifecycle status/reason, and next snapshot.

- [ ] **Step 1: Add complete-cycle RED tests**

Add explicit golden expectations for Spot open/hold/close and Perp short open/hold/funding/close. Require intent/client IDs to be derived from frozen hashes, normal full-fill idempotence, stop trigger using completed-bar low/high plus conservative gap/slippage, stop persistence, cancel-before-close, verified flat before reversal, and exact three-way order/venue/ledger reconciliation.

- [ ] **Step 2: Add fixed fault RED tests**

Patch private existing aggregation boundaries to cover partial fill, fill-before-ack, duplicate, overfill, timeout/UNKNOWN, disconnect, late fill, stop missing, cancel-close failure with stop re-establishment, flatten failure, and ledger mismatch. Assert either VERIFIED remaining position or last-verified `position_certainty=UNRESOLVED`, unresolved intent IDs, `FAILED_CLOSED`, and no risk-increasing continuation.

```python
def test_unknown_close_reestablishes_stop_or_advances_unresolved_lock(self):
    with patch.object(simulation, "_aggregate_attempt", side_effect=unknown_attempt()):
        result = simulate_close_fixture()
    self.assertEqual(result["lifecycle_status"], "FAILED_CLOSED")
    self.assertIn(
        result["next_snapshot"]["position_certainty"],
        {"VERIFIED", "UNRESOLVED"},
    )
```

- [ ] **Step 3: Run the lifecycle tests and observe RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_simulation -v`

Expected: exact lifecycle/stop/reconciliation assertions fail against the Task 4 minimal transition.

- [ ] **Step 4: Implement only the frozen product lifecycle**

Reuse stable order aggregation data structures where their signed semantics pass the tests. Keep one normal full-fill path and private test-patched boundaries; do not create a reusable exchange/Broker platform.

- [ ] **Step 5: Run focused and adjacent lifecycle tests**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_simulation tests.test_orders tests.test_instruments tests.test_ledger tests.test_system_paper_broker -v
PYTHONPATH=src python3 -m compileall -q src/crypto_quant
git diff --check
```

Expected: selected tests pass without changing System Paper behavior.

- [ ] **Step 6: Commit Task 5**

```bash
git add src/crypto_quant/challenger_replacement_simulation.py tests/test_challenger_replacement_simulation.py
git commit -m "feat: close simulated order lifecycle"
```

### Task 6: Bind v2 results to the canonical opportunity log

**Files:**
- Create: `config/challenger-replacement-opportunity-result-evidence-v2.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-opportunity-result-evidence-v2.schema.json`
- Modify: `src/crypto_quant/challenger_replacement_opportunity_evidence.py`
- Modify: `src/crypto_quant/challenger_replacement_opportunity_projection.py`
- Modify: `src/crypto_quant/challenger_replacement_opportunities.py`
- Modify: `src/crypto_quant/challenger_replacement_simulation.py`
- Modify: `tests/test_challenger_replacement_opportunity_evidence.py`
- Modify: `tests/test_challenger_replacement_opportunities.py`
- Modify: `tests/test_challenger_replacement_simulation.py`

**Interfaces:**
- Consumes: Task 5 deterministic result and v0.70 retained event-root capability/state.
- Produces public `load_challenger_replacement_simulation_result_evidence_bytes(...) -> dict` and `run_challenger_replacement_fixture_simulation_opportunity(*, state, input_bytes) -> dict`. Result construction is a private function that accepts only the engine's frozen internal result type, not a caller mapping or caller-provided PnL/action/outcome.

- [ ] **Step 1: Add v2 evidence RED tests**

Require strict schema/canonical bytes/self-hash and exact plan/contract/build/opportunity/source/decision/previous-projection bindings, lifecycle arrays, snapshot, reconciliation, zero authority, and rejection of caller-provided PnL/action/outcome. Preserve committed v1 byte replay in isolated v0.70 fixture roots.

- [ ] **Step 2: Add event/projection RED tests**

Cover genesis v2 OBSERVED, second opportunity parent snapshot, v0.70/v0.71 root mixing rejection, MISSED while FLAT, deterministic `economic_gap_locked` after prior non-FLAT + unchanged v0.70 MISSED payload, failed-lifecycle OBSERVED coverage versus completeness, and exact build/root isolation. Add three explicit terminal-boundary cases: malformed/unbound `input_bytes` fails with zero events; a failure after durable INPUT remains active and does not fabricate MISSED; only `catch_up_missed_opportunities(detected_at > capture_close)` may append the existing canonical MISSED event.

- [ ] **Step 3: Add crash/restart/concurrency RED tests**

Use subprocess/fresh interpreter harnesses for crashes after INPUT, RESULT, and OBSERVED. Require INPUT retry to reuse exact source bytes, RESULT retry to return exact result with zero recompute, OBSERVED retry to return terminal projection, and same-opportunity two-process competition to produce one canonical lifecycle without duplicate economic fills.

- [ ] **Step 4: Run Task 6 tests and observe RED**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_opportunity_evidence tests.test_challenger_replacement_opportunities tests.test_challenger_replacement_simulation -v
```

Expected: schema dispatch, snapshot projection, gap lock, and fixture run entrypoint assertions fail before implementation.

- [ ] **Step 5: Implement minimal v2 dispatch and orchestration**

The projection module dispatches on the exact evidence schema/version and remains the only event state machine. The fixture runner accepts canonical `input_bytes` only, derives scheduled/observed time exclusively from validated bytes, replays before every append, uses optimistic last-event hash, and never silently rebases a stale caller. Malformed or unbound bytes fail before INPUT with zero events. A decision/runtime failure after durable INPUT leaves the opportunity active for exact retry; it does not have a trusted later detection time and therefore cannot create MISSED. Only the existing explicit catch-up API, called with canonical `detected_at` after capture close, may append MISSED. A complete observed source/decision whose simulated lifecycle fails maps to OBSERVED with failed status and risk lock.

- [ ] **Step 6: Verify event integration and size gates**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_opportunity_evidence tests.test_challenger_replacement_opportunities tests.test_challenger_replacement_simulation tests.test_challenger_replacement_events tests.test_challenger_replacement_plan_v3 -v
wc -l src/crypto_quant/challenger_replacement_opportunities.py src/crypto_quant/challenger_replacement_opportunity_projection.py src/crypto_quant/challenger_replacement_simulation.py src/crypto_quant/challenger_replacement_simulation_contract.py src/crypto_quant/challenger_replacement_binance_simulation_input.py
git diff --numstat v0.70.0^{}..HEAD -- src/crypto_quant
PYTHONPATH=src python3 -m compileall -q src/crypto_quant
git diff --check
```

Expected: all selected tests pass; facade line count does not increase; every module is at most 700 lines; the checked six-module production budget is at most 1,200 lines. If any limit fails, stop and split before artifacts or release work.

- [ ] **Step 7: Commit Task 6**

```bash
git add config/challenger-replacement-opportunity-result-evidence-v2.schema.json src/crypto_quant/schemas/challenger-replacement-opportunity-result-evidence-v2.schema.json src/crypto_quant/challenger_replacement_opportunity_evidence.py src/crypto_quant/challenger_replacement_opportunity_projection.py src/crypto_quant/challenger_replacement_opportunities.py src/crypto_quant/challenger_replacement_simulation.py tests/test_challenger_replacement_opportunity_evidence.py tests/test_challenger_replacement_opportunities.py tests/test_challenger_replacement_simulation.py
git commit -m "feat: bind simulation results to opportunities"
```

### Task 7: Publish immutable contract and golden fixture artifacts locally

**Files:**
- Create: `artifacts/challenger-replacement/challenger-replacement-binance-simulation-contract-v0.71.0.json`
- Create: `artifacts/challenger-replacement/challenger-replacement-binance-golden-fixture-manifest-v0.71.0.json`
- Create: `config/challenger-replacement-binance-golden-fixture-manifest-v1.schema.json`
- Create the exact ordered Spot documents under `tests/fixtures/challenger_replacement_v071/spot-cycle/`: `01-input.json`, `02-result.json`, `03-input.json`, `04-result.json`, `05-input.json`, `06-result.json`.
- Create the exact ordered Perp documents under `tests/fixtures/challenger_replacement_v071/perp-cycle/`: `01-input.json`, `02-result.json`, `03-input.json`, `04-result.json`, `05-input.json`, `06-result.json`, `07-input.json`, `08-result.json`.
- Create: `tests/test_challenger_replacement_v071_artifacts.py`

**Interfaces:**
- Consumes: passed schemas/builders/loaders and exact v0.69 plan.
- Produces committed byte/hash regressions. The golden manifest is a strict test-only schema: exact sorted path/SHA-256/schema-kind/opportunity-order entries, contract hash, stable ID, and self-hash. Every listed file is an individual production-schema input or result document, not a new bundle format or runtime authority. Root-bound event bytes are deliberately not committed as portable goldens.

- [ ] **Step 1: Add pre-artifact RED tests**

Freeze exact paths, the 14-file ordered fixture inventory, canonical bytes, file SHA-256, contract self-hash, fixture-manifest contract binding/self-hash, and semantic replay of Spot/Perp normal streams. Load every input with the v0.71 input loader and every result with the v2 result loader. In a fresh owner-only event root, run each input through the fixture runner and require its computed result bytes to equal the paired committed result; then assert terminal status, lifecycle status, and next snapshot from the sole projection. Do not compare or normalize root-bound event hashes/device/inode fields. Assert neither artifact contains future commit/tag/CI identity and no changed/reordered/extra file is accepted. Failed lifecycle remains covered by Task 5/6 fixed private-boundary tests; it is not encoded as an unversioned portable market fixture.

- [ ] **Step 2: Run tests and observe RED for absent formal artifacts**

Run: `PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_v071_artifacts -v`

Expected: exact missing-artifact assertions fail.

- [ ] **Step 3: Generate canonical fixture bytes with reviewed builders**

Use a fixed repository invocation that prints the Task 1 contract bytes and the exact 14 input/result documents plus manifest to stdout; pass no arbitrary destination, PnL, action, fee, time, or outcome. Add the one manifest schema and write only the exact Task 7 inventory (two artifacts, one schema, and 14 fixture files) through `apply_patch`, then load and replay every byte before staging.

- [ ] **Step 4: Run committed-artifact and adjacent golden tests**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_v071_artifacts tests.test_challenger_replacement_simulation_contract tests.test_challenger_replacement_simulation tests.test_challenger_replacement_opportunities -v
git diff --check
```

Expected: no skips; every formal artifact and lifecycle golden replays exactly.

- [ ] **Step 5: Commit Task 7**

```bash
git add artifacts/challenger-replacement/challenger-replacement-binance-simulation-contract-v0.71.0.json artifacts/challenger-replacement/challenger-replacement-binance-golden-fixture-manifest-v0.71.0.json config/challenger-replacement-binance-golden-fixture-manifest-v1.schema.json tests/fixtures/challenger_replacement_v071 tests/test_challenger_replacement_v071_artifacts.py
git commit -m "test: freeze Binance simulation goldens"
```

### Task 8: Close documentation, release metadata, verification, and publication

**Files:**
- Create: `docs/adr/0071-binance-deterministic-simulation.md`
- Create: `docs/implementation-status-v0.71.0.md`
- Create: `tests/test_challenger_replacement_v071_release.py`
- Modify: `README.md`
- Modify: `src/crypto_quant/__init__.py`
- Modify: `src/crypto_quant/build.py`
- Modify: `src/crypto_quant/challenger_replacement_deployment.py` only for the exact current manifest version/hash loader literals required by existing tests; no deployment behavior change.
- Modify: `pyproject.toml`
- Modify: `setup.py`
- Modify: `scripts/refresh_evaluator_build_manifest.py`
- Modify: `config/evaluator-build-manifest-v1.json`
- Modify: `tests/test_estimators.py`
- Modify: `tests/test_challenger_replacement_v066_release.py`
- Modify: `tests/test_challenger_replacement_v067_release.py`
- Modify: `tests/test_challenger_replacement_v068_release.py`
- Modify: `tests/test_challenger_replacement_v069_release.py`
- Modify: `tests/test_challenger_replacement_v070_release.py`
- Modify: `tests/test_nautilus_v065_release.py`
- Modify: `tests/test_nautilus_v0651_hardening.py`
- Modify: `tests/test_v064_public_ci_bundle.py`

**Interfaces:**
- Consumes: final v0.71 code/artifacts.
- Produces package `0.71.0`, manifest `1.65.0`, candidate status `CANDIDATE_FIXTURE_SIMULATION_LOCAL_VERIFICATION_PENDING`, final status `FIXTURE_DETERMINISTIC_SIMULATION_VERIFIED_NOT_STARTED`, and a release identity that does not authorize runtime use.

- [ ] **Step 1: Add release/static RED tests**

Require exact version/manifest inventory and hashes, spec/plan/ADR/status claims, immutable v0.69/v0.70 ancestry, contract/golden artifact SHA binding, no production authority, no forbidden imports/public APIs, no module above 700 lines, and the exact six-module line-budget formula `(current total - 843) <= 1200`. The test prints the six per-file counts and separately asserts the branch did not delete or modify unrelated production modules to gain budget credit.

- [ ] **Step 2: Run release tests and observe RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_v071_release -v`

Expected: version/manifest/docs assertions fail while metadata is still v0.70.

- [ ] **Step 3: Update candidate documentation and metadata**

Document exact equations, no-authority boundary, fixture-only provenance, failed lifecycle/gap behavior, rejected generic Broker/Nautilus embedding, and future v0.72 evaluator/observer work. Before independent review, status is exactly `CANDIDATE_FIXTURE_SIMULATION_LOCAL_VERIFICATION_PENDING`; it must not claim full-suite/review/CI evidence that has not happened. Update package/build versions and deterministic manifest using the repository's existing builder/replay process. Every predecessor release test retains its historical assertions and changes only the exact current-manifest expectations required to replay `1.65.0`.

- [ ] **Step 4: Run focused, adjacent, fault, and golden validation**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_simulation_contract tests.test_challenger_replacement_binance_simulation_input tests.test_challenger_replacement_simulation tests.test_challenger_replacement_opportunity_evidence tests.test_challenger_replacement_opportunities tests.test_challenger_replacement_events tests.test_challenger_replacement_v071_artifacts tests.test_challenger_replacement_v071_release -v
PYTHONPATH=src python3 -m unittest tests.test_instruments tests.test_orders tests.test_ledger tests.test_system_paper_broker tests.test_challenger_replacement_plan_v3 tests.test_challenger_replacement_v070_release -v
PYTHONPATH=src python3 -m compileall -q src/crypto_quant
make validate
git diff --check
git status --short
```

Expected: all focused/adjacent tests pass; `make validate` exits 0 while its production-activation checks remain fail-closed; worktree contains only planned candidate changes.

- [ ] **Step 5: Commit the final candidate code state**

```bash
git add README.md docs/implementation-status-v0.71.0.md docs/adr/0071-binance-deterministic-simulation.md src/crypto_quant/__init__.py src/crypto_quant/build.py src/crypto_quant/challenger_replacement_deployment.py pyproject.toml setup.py scripts/refresh_evaluator_build_manifest.py config/evaluator-build-manifest-v1.json tests/test_estimators.py tests/test_challenger_replacement_v066_release.py tests/test_challenger_replacement_v067_release.py tests/test_challenger_replacement_v068_release.py tests/test_challenger_replacement_v069_release.py tests/test_challenger_replacement_v070_release.py tests/test_nautilus_v065_release.py tests/test_nautilus_v0651_hardening.py tests/test_v064_public_ci_bundle.py tests/test_challenger_replacement_v071_release.py
git commit -m "chore: prepare v0.71.0 simulation release"
```

- [ ] **Step 6: Request one independent complete review**

Provide the reviewer the spec, plan, full branch diff from `v0.70.0^{}`, line-count report, focused results, and safety boundary. Critical/Important findings must be fixed with a new exact RED regression; perform only targeted re-review after fixes.

- [ ] **Step 7: Run the final local full suite exactly once**

Run:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
PYTHONPATH=src python3 -m compileall -q src/crypto_quant
make validate
git diff --check
git status --short
```

Expected: full suite passes with only explicitly reviewed skips; compile/diff/status are clean; expected production activation remains disabled.

- [ ] **Step 8: Seal final local evidence without changing production code**

Update only `docs/implementation-status-v0.71.0.md` from the pending candidate status to `FIXTURE_DETERMINISTIC_SIMULATION_VERIFIED_NOT_STARTED`, recording the exact pre-evidence `reviewed_production_candidate_head` (not the future self-containing commit), full-suite command/count/exit, focused validation, line-budget result, and Critical/Important=0. Refresh `config/evaluator-build-manifest-v1.json`; run `PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_v071_release tests.test_estimators -v`, `PYTHONPATH=src python3 -m compileall -q src/crypto_quant`, and `git diff --check`; then commit those two files. The final release commit/manifest binds the status bytes, avoiding a self-referential HEAD field. Request targeted review only of this evidence/manifest delta; do not repeat the full suite because production code did not change.

- [ ] **Step 9: Publish through the already-approved public release flow**

Immediately before remote writes, verify PUBLIC repository, exact `origin`, ADMIN permission, branch/head, and clean worktree. Push the branch, open Draft PR, wait for Python 3.9/3.12 and macOS arm64 CI, merge exact reviewed head, wait for main CI, then create annotated `v0.71.0`. Verify `origin/main`, tag object type, and peeled tag all match the merge commit. Any CI/identity mismatch stops publication without retagging or selecting a different result.

## Self-review checklist

- [ ] Every design section 1-16 maps to at least one task above.
- [ ] No task writes a production root, calls a service, reads credentials/account state, or submits an order.
- [ ] Contract, source, accounting, stop, MISSED gap, failed lifecycle, replay, concurrency, and release identity each have a precise RED test.
- [ ] v0.70 v1 replay and v0.69 plan bytes remain committed regressions.
- [ ] Formal artifacts are generated only after their schema/builder/loader tests exist.
- [ ] Exact function names and schema versions are consistent across tasks.
- [ ] No unresolved marker, vague error-handling instruction, or hidden production injection seam remains.
