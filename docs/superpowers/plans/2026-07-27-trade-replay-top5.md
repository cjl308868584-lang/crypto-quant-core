# Complete-Trade Top-5 Replay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `LEAVE_TOP_5_POSITIVE_TRADES_OUT_MBB_LCB95_V1` executable through deterministic, path-dependent removal of complete position cycles and full economic replay.

**Architecture:** Economic snapshots first gain immutable event identities and source sequence numbers. A new `TradeReplaySnapshot v1` embeds the trusted source series and economic snapshots, proves that executable valuation facts reproduce the original path, derives complete zero-to-zero position cycles, removes the five largest positive cycles, and rebuilds the endpoint series before applying the existing MBB kernel. Estimator, evidence, release, and build-manifest layers bind the artifact and fail closed on every mismatch.

**Tech Stack:** Python 3.9+, `Decimal`, SQLite WAL, JSON Schema Draft 2020-12, RFC8785/JCS-style canonicalization, SHA-256, `unittest`, existing deterministic MBB implementation.

## Global Constraints

- `trade_id` is a derived zero-to-zero position cycle, never `exchange_trade_id`, a Fill, or a Proposal.
- All business arithmetic uses canonical `Decimal`; binary float remains forbidden.
- Fact ordering is `(event_time, source_event_sequence, stable fact ID)`.
- Original liquidation equity, position bases, expected exit fees, and source observation values must replay exactly before counterfactual deletion is allowed.
- Fill prices already contain spread and slippage; `implementation_shortfall_usdt` is never deducted again.
- Selected-trade Fill and Funding facts are removed; external cash flow and all allocated costs remain.
- Original positive-trade ranking is contribution descending, then `trade_id` ascending.
- `FAIL` and `INCONCLUSIVE` never become a passing release result.
- Legacy EconomicLedgerSnapshot v1.0 remains valid for existing estimators but is ineligible for complete-trade replay.
- The final package version is `0.13.0`; no Broker, API key, or real-order capability is added.

## File Structure

- Create `src/crypto_quant/trade_replay.py`: artifact hashing, semantic validation, original-path replay, cycle derivation, Top-5 selection, counterfactual replay, and Estimator callable.
- Create `config/trade-replay-snapshot-v1.schema.json`: strict external artifact contract.
- Create `tests/test_trade_replay.py`: focused behavioral and mutation-resistant replay tests.
- Modify `src/crypto_quant/ledger.py`: export immutable event identities and source sequences into EconomicLedgerSnapshot v1.1.
- Modify `src/crypto_quant/economics.py`: validate v1.1 identity and sequence invariants without breaking v1.0 consumers.
- Modify `config/economic-ledger-snapshot-v1.schema.json`: conditional v1.0/v1.1 fact requirements.
- Modify `src/crypto_quant/statistics.py` and `config/statistical-series-snapshot-v1.schema.json`: validate counterfactual primary series provenance and reuse the MBB kernel.
- Modify `src/crypto_quant/estimators.py`, `config/estimator-registry-v1.json`, `config/estimator-registry-v1.schema.json`, `config/estimator-golden-vectors-v1.json`: register, validate, and freeze the new executable Estimator.
- Modify `src/crypto_quant/release.py`, `src/crypto_quant/release_artifacts.py`, `config/release-evidence-v1.1.schema.json`, and `config/supporting-observation-bundle-v1.schema.json`: bind replay evidence and verify source completeness.
- Modify `src/crypto_quant/build.py`, `config/evaluator-build-manifest-v1.json`, `pyproject.toml`, `README.md`: include the artifact in the frozen build and publish v0.13.0.
- Create `docs/adr/0013-complete-trade-counterfactual-replay.md` and `docs/implementation-status-v0.13.0.md`: record decisions, evidence, and remaining fail-closed work.

---

### Task 1: Make Economic Snapshots Replay-Traceable

**Files:**
- Modify: `config/economic-ledger-snapshot-v1.schema.json`
- Modify: `src/crypto_quant/ledger.py`
- Modify: `src/crypto_quant/economics.py`
- Modify: `tests/test_economics.py`
- Modify: `tests/test_replay.py`

**Interfaces:**
- Consumes: existing `EventLedger.economic_ledger_snapshot(...) -> dict`.
- Produces: EconomicLedgerSnapshot `schema_version == "1.1.0"` with `source_event_sequence` on every fact and Fill identity fields `exchange_trade_id`, `local_order_id`, and `venue_order_id`.

- [ ] **Step 1: Write failing schema and ledger-export tests**

Add `test_v11_snapshot_preserves_immutable_fact_identity_and_sequence` in `tests/test_economics.py`. Populate the existing economic ledger, build a snapshot, and assert these literal facts:

```python
self.assertEqual(snapshot["schema_version"], "1.1.0")
self.assertEqual(
    [
        (
            fill["fill_id"],
            fill["exchange_trade_id"],
            fill["local_order_id"],
            fill["venue_order_id"],
            fill["source_event_sequence"],
        )
        for fill in snapshot["fills"]
    ],
    [
        ("fill-1", "trade-1", "order-1", "venue-order-1", 3),
        ("fill-2", "trade-2", "order-2", "venue-order-2", 4),
    ],
)
self.assertEqual(
    [point["source_event_sequence"] for point in snapshot["equity_points"]],
    [1, 6, 9],
)
```

Add `test_v11_sequence_tampering_fails_semantic_validation` that duplicates one positive sequence, rehashes the snapshot, and expects `ECONOMIC_SNAPSHOT_SOURCE_SEQUENCE_DUPLICATE`. Add a v1.0 fixture regression assertion showing the existing five economic estimators remain `COMPUTED`.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
python -m unittest \
  tests.test_economics.EconomicLedgerIntegrationTests.test_v11_snapshot_preserves_immutable_fact_identity_and_sequence \
  tests.test_economics.EconomicEstimatorTests.test_v11_sequence_tampering_fails_semantic_validation -v
```

Expected: failure because `schema_version` is still `1.0.0` and the new fields/reason do not exist.

- [ ] **Step 3: Extend the schema conditionally**

Change `schema_version` to enum `["1.0.0", "1.1.0"]`. Add `$defs.positiveInteger`. Add optional identity/sequence properties to each fact. Add an `allOf` branch:

```json
{
  "if": {
    "properties": {"schema_version": {"const": "1.1.0"}},
    "required": ["schema_version"]
  },
  "then": {
    "properties": {
      "fills": {"items": {"$ref": "#/$defs/replayableFill"}},
      "funding_cashflows": {"items": {"$ref": "#/$defs/replayableFunding"}},
      "external_cash_flows": {"items": {"$ref": "#/$defs/replayableCashFlow"}},
      "allocated_costs": {"items": {"$ref": "#/$defs/replayableAllocatedCost"}},
      "equity_points": {"items": {"$ref": "#/$defs/replayableEquityPoint"}}
    }
  }
}
```

Each replayable definition composes the existing fact with the required `source_event_sequence`; replayable Fill additionally requires the three immutable order/trade IDs.

- [ ] **Step 4: Export source event sequence from SQLite**

In every EconomicLedgerSnapshot query, join the projection `source_event_id` to `events.event_id`, select `events.sequence AS source_event_sequence`, and include it in the returned fact. Include the three Fill identity fields already present in `payload_json`. Emit:

```python
"schema_version": "1.1.0"
```

Sort by fact time, `source_event_sequence`, then fact ID. Do not derive sequence from array index.

- [ ] **Step 5: Validate v1.1 semantic ordering**

In `economic_snapshot_reasons`, collect every v1.1 fact as:

```python
(parsed_time, source_event_sequence, fact_id)
```

Require sequence to be a positive non-boolean integer, globally unique, and increasing within the canonical `(time, sequence, ID)` ordering. Return these exact reasons where applicable:

```text
ECONOMIC_SNAPSHOT_SOURCE_SEQUENCE_INVALID
ECONOMIC_SNAPSHOT_SOURCE_SEQUENCE_DUPLICATE
ECONOMIC_SNAPSHOT_FACT_ORDER_INVALID
ECONOMIC_SNAPSHOT_FILL_IDENTITY_INVALID
```

Do not require the fields when `schema_version == "1.0.0"`.

- [ ] **Step 6: Run focused and regression tests**

Run:

```bash
python -m unittest tests.test_economics tests.test_replay -v
```

Expected: all tests pass, including v1.0 estimator compatibility and v1.1 traceability.

- [ ] **Step 7: Commit Task 1**

```bash
git add config/economic-ledger-snapshot-v1.schema.json \
  src/crypto_quant/ledger.py src/crypto_quant/economics.py \
  tests/test_economics.py tests/test_replay.py
git commit -m "feat: preserve economic replay fact identity"
```

### Task 2: Build the Original-Path Replay Core

**Files:**
- Create: `src/crypto_quant/trade_replay.py`
- Create: `tests/test_trade_replay.py`
- Modify: `tests/factories.py`

**Interfaces:**
- Consumes: EconomicLedgerSnapshot v1.1, `PRIMARY_ENDPOINT_CONTRIBUTION` source series, and executable valuation checkpoints.
- Produces the stable internal boundary `analyze_trade_replay_source(*, source_series_snapshot: Mapping[str, Any], economic_snapshots: Sequence[Mapping[str, Any]], valuation_checkpoints: Sequence[Mapping[str, Any]]) -> SourceReplayAnalysis`.

- [ ] **Step 1: Add a literal replay fixture factory**

In `tests/factories.py`, add:

```python
def complete_trade_replay_inputs(
    *,
    trade_pnls=("10", "9", "8", "7", "6", "5"),
    block_length=2,
    minimum_block_count=2,
):
    """Return source_series, economic_snapshots, valuation_checkpoints."""
```

The fixture uses approved capital `1000`, six consecutive non-overlapping periods, one zero-to-zero `BINANCE:SPOT:BTCUSDT` trade per period, one unit per trade, entry price `100`, exit prices `110, 109, 108, 107, 106, 105`, zero fees/funding/cost/flow, and start/end executable prices equal to the recorded entry/exit facts. It assigns literal source event sequences `1..24` and distinct source hashes. Each source observation value is the exact Decimal log growth derived from its period.

- [ ] **Step 2: Write failing original-replay and cycle tests**

Add tests with these exact names and behaviors:

- `test_split_fills_form_one_zero_to_zero_trade`
- `test_overlapping_instruments_form_independent_cycles`
- `test_opening_and_unclosed_positions_are_not_eligible`
- `test_fill_crossing_zero_fails_closed`
- `test_multiplier_change_fails_closed`
- `test_original_equity_must_replay_at_every_checkpoint`
- `test_funding_position_must_match_replayed_position`
- `test_trade_id_is_stable_and_uploader_cannot_supply_it`

For split fills, use BUY `1`, BUY `2`, SELL `1`, SELL `2`; assert one trade with ordered Fill IDs and realized contribution `"30"`. For a tampered middle EquityPoint changed from `"1010"` to `"1010.01"`, rehash only the source EconomicSnapshot and assert `analyze_trade_replay_source` raises `ValueError` containing `TRADE_REPLAY_ORIGINAL_EQUITY_MISMATCH`.

- [ ] **Step 3: Run tests and verify RED**

Run:

```bash
python -m unittest tests.test_trade_replay -v
```

Expected: import failure for `crypto_quant.trade_replay`.

- [ ] **Step 4: Implement canonical parsing and cycle derivation**

In `trade_replay.py`, use a fixed local Decimal context and immutable internal records. Implement:

```python
@dataclass(frozen=True)
class PositionState:
    quantity: Decimal
    average: Decimal
    multiplier: Decimal

@dataclass(frozen=True)
class CompletedTrade:
    trade_id: str
    instrument_id: str
    fill_ids: Tuple[str, ...]
    funding_ids: Tuple[str, ...]
    contribution_usdt: Decimal
    opened_at: str
    closed_at: str
    eligible: bool

@dataclass(frozen=True)
class SourceReplayAnalysis:
    scope: Mapping[str, Any]
    original_replay: Tuple[Mapping[str, Any], ...]
    completed_trades: Tuple[CompletedTrade, ...]
    funding_assignment: Mapping[str, str]
```

Use moving-average cost basis. A reducing Fill realizes:

```python
realized += (
    price - average if position > 0 else average - price
) * closed_quantity * multiplier
```

Reject `abs(delta) > abs(position)` on a reducing Fill. Derive:

```python
trade_id = "trd:" + business_hash({
    "scope": scope_identity,
    "instrument_id": instrument_id,
    "fill_ids": ordered_fill_ids,
})
```

Bind Funding to the active instrument cycle at settlement sequence and require exact signed `position_quantity`. Return all verified results through `SourceReplayAnalysis`; do not emit a partially populated external Artifact.

- [ ] **Step 5: Implement original liquidation-equity replay**

At each checkpoint calculate liquidation equity from:

```text
starting liquidation equity
+ change in realized/unrealized PnL from the opening state
- cumulative Fill fees
+ cumulative signed Funding
+ cumulative net external cash flow
```

Use long executable Bid or short executable Ask plus the frozen expected exit fee. Compare canonical Decimal values, position cost bases, and expected exit-fee accrual to the source EquityPoint. Separately derive the source observation using existing allocated-cost adjustment and require exact equality with the embedded source series.

- [ ] **Step 6: Run focused tests**

Run:

```bash
python -m unittest tests.test_trade_replay -v
```

Expected: all original-path, cycle, Funding, and tamper tests pass.

- [ ] **Step 7: Commit Task 2**

```bash
git add src/crypto_quant/trade_replay.py tests/test_trade_replay.py \
  tests/factories.py
git commit -m "feat: add complete-trade source replay core"
```

### Task 3: Implement Top-5 Counterfactual Replay

**Files:**
- Create: `config/trade-replay-snapshot-v1.schema.json`
- Modify: `src/crypto_quant/trade_replay.py`
- Modify: `src/crypto_quant/statistics.py`
- Modify: `config/statistical-series-snapshot-v1.schema.json`
- Modify: `tests/test_trade_replay.py`
- Modify: `tests/test_statistics.py`

**Interfaces:**
- Consumes: `SourceReplayAnalysis` from Task 2.
- Produces the external Artifact APIs:

- `trade_replay_snapshot_hash(snapshot: Mapping[str, Any]) -> str`
- `trade_replay_snapshot_reasons(snapshot: Mapping[str, Any]) -> Tuple[str, ...]`
- `build_trade_replay_snapshot(*, replay_id: str, source_series_snapshot: Mapping[str, Any], economic_snapshots: Sequence[Mapping[str, Any]], valuation_checkpoints: Sequence[Mapping[str, Any]], generated_at: str) -> Dict[str, Any]`

Exact public signature: `leave_top_5_positive_trades_out_mbb_lcb95(inputs: Mapping[str, Any]) -> Tuple[str, Any, Tuple[str, ...]]`.

The embedded counterfactual series remains `PRIMARY_ENDPOINT_CONTRIBUTION`, has top-level `counterfactual_replay_id`, and gives every observation a `counterfactual_replay_period_hash`.

- [ ] **Step 1: Write failing selection and counterfactual tests**

Add these exact tests:

- `test_selects_exactly_five_largest_positive_complete_trades`
- `test_equal_contribution_uses_trade_id_ascending`
- `test_fewer_than_five_removes_all_positive_trades`
- `test_no_positive_trade_removes_none_but_still_replays`
- `test_selected_trade_removes_all_fills_and_owned_funding`
- `test_external_flows_and_allocated_costs_are_preserved`
- `test_counterfactual_observations_are_rebuilt_not_subtracted`
- `test_counterfactual_series_tampering_fails_closed`
- `test_insufficient_blocks_is_inconclusive`

For fixture contributions `10,9,8,7,6,5`, assert that the selected set contains the five trade IDs corresponding to `10..6`, the remaining counterfactual total contribution is exactly `"5"`, and the original series remains byte-for-byte unchanged.

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```bash
python -m unittest \
  tests.test_trade_replay.CompleteTradeCounterfactualTests -v
```

Expected: failures because selection and counterfactual fields are absent.

- [ ] **Step 3: Create the strict replay Artifact schema**

Define a closed Draft 2020-12 schema requiring:

```text
$schema, schema_version=1.0.0, replay_id, replay_hash,
hash_algorithm=SHA-256, canonicalization=RFC8785_JCS,
source_series_snapshot, source_series_hash,
source_economic_snapshots, source_economic_snapshot_hashes,
scope, policy_bindings, approved_production_capital_usdt,
bootstrap_design, valuation_checkpoints, original_replay,
completed_trades, selected_trade_ids, counterfactual_series,
generated_at, replay_verified=true
```

Require unique IDs/hashes, canonical Decimal strings, UTC times, non-empty source arrays, strict checkpoint/instrument objects, and `additionalProperties: false` at every object boundary.

- [ ] **Step 4: Extend StatisticalSeriesSnapshot v1.2**

Allow schema version `1.2.0`. Add optional top-level `counterfactual_replay_id` and observation `counterfactual_replay_period_hash`. Add conditional rules:

```text
if counterfactual_replay_id exists:
  schema_version == 1.2.0
  series_kind == PRIMARY_ENDPOINT_CONTRIBUTION
  every observation requires counterfactual_replay_period_hash
else:
  no observation may carry counterfactual_replay_period_hash
```

Extend `statistical_series_reasons` to enforce the same semantics, not just Schema validation.

- [ ] **Step 5: Implement stable selection**

Derive selected IDs only from original completed trades:

```python
positive = [trade for trade in completed if trade.contribution_usdt > 0]
selected = tuple(
    trade.trade_id
    for trade in sorted(
        positive,
        key=lambda trade: (-trade.contribution_usdt, trade.trade_id),
    )[:5]
)
```

Never trust `selected_trade_ids` from the Artifact without comparing it to this derived tuple.

- [ ] **Step 6: Replay the remaining facts**

Remove every Fill and assigned Funding whose derived `trade_id` is selected. Preserve all other facts, checkpoints, external flows, and allocated costs. Re-run the same position/equity engine from the original starting state. For each source observation, create a new value from the replayed economic path and calculate:

```python
counterfactual_replay_period_hash = business_hash({
    "replay_id": replay_id,
    "period_start": period_start,
    "period_end": period_end,
    "selected_trade_ids": selected_ids,
    "replayed_equity_points": period_points,
})
```

Preserve all original observation metadata and Bootstrap design.

- [ ] **Step 7: Build, hash, and independently validate the Artifact**

`build_trade_replay_snapshot` calls `analyze_trade_replay_source`, derives selection and the counterfactual series, then creates the complete object with a zero hash and computes `replay_hash`. `trade_replay_snapshot_reasons` calls the source analysis and counterfactual replay again, comparing source hashes, scopes, cycle IDs, Funding assignments, original replay, selected IDs, counterfactual observations, and all nested hashes. The builder calls the validator and raises `ValueError` on any reason.

- [ ] **Step 8: Call the existing MBB kernel**

After independent artifact validation, call the existing internal MBB function with the rebuilt series. Return:

- `COMPUTED` and canonical Decimal for sufficient samples;
- `INCONCLUSIVE` with `STATISTICAL_SERIES_INSUFFICIENT_BLOCKS`;
- `FAIL` with sorted `TRADE_REPLAY_*` reasons for any trust or replay mismatch.

- [ ] **Step 9: Run replay and statistics tests**

Run:

```bash
python -m unittest tests.test_trade_replay tests.test_statistics -v
```

Expected: all tests pass.

- [ ] **Step 10: Commit Task 3**

```bash
git add config/trade-replay-snapshot-v1.schema.json \
  src/crypto_quant/trade_replay.py src/crypto_quant/statistics.py \
  config/statistical-series-snapshot-v1.schema.json \
  tests/test_trade_replay.py tests/test_statistics.py
git commit -m "feat: replay top five complete-trade removal"
```

### Task 4: Register and Freeze the Estimator

**Files:**
- Modify: `src/crypto_quant/estimators.py`
- Modify: `config/estimator-registry-v1.schema.json`
- Modify: `config/estimator-registry-v1.json`
- Modify: `config/estimator-golden-vectors-v1.json`
- Modify: `config/release-metrics-v1.1.json`
- Modify: `tests/test_estimators.py`
- Modify: `tests/test_trade_replay.py`

**Interfaces:**
- Consumes: `trade_replay_snapshot`.
- Produces: executable registry entry for `LEAVE_TOP_5_POSITIVE_TRADES_OUT_MBB_LCB95_V1`.

- [ ] **Step 1: Write failing registry tests**

Assert:

```python
self.assertTrue(
    registry.is_executable(
        "LEAVE_TOP_5_POSITIVE_TRADES_OUT_MBB_LCB95_V1"
    )
)
self.assertEqual(
    registry.execute(
        "LEAVE_TOP_5_POSITIVE_TRADES_OUT_MBB_LCB95_V1",
        {"trade_replay_snapshot": valid_replay},
    ).status,
    "COMPUTED",
)
```

Also mutate the replay schema, self-hash, source hash, selected IDs, and counterfactual series after rehashing each outer level. Assert that every mutation returns `FAIL`, proving semantic replay rather than only outer-hash checking.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
python -m unittest tests.test_estimators tests.test_trade_replay -v
```

Expected: current result is `FAIL / ESTIMATOR_NOT_EXECUTABLE`.

- [ ] **Step 3: Load and enforce the new schema**

Add `trade_replay_schema` to `EstimatorRegistry.__init__`, load `config/trade-replay-snapshot-v1.schema.json`, call `Draft202012Validator.check_schema`, and validate `trade_replay_snapshot` before dispatch. Schema failure returns only:

```text
TRADE_REPLAY_SCHEMA_INVALID
```

- [ ] **Step 4: Add the callable and registry contract**

Import the callable from `trade_replay.py`, add it to `_CALLABLES`, add the callable enum in registry Schema, and append an implementation:

```json
{
  "estimator_id": "LEAVE_TOP_5_POSITIVE_TRADES_OUT_MBB_LCB95_V1",
  "implementation_id": "trade_replay.leave-top-5-positive-trades-out-mbb-lcb95",
  "implementation_version": "1.0.0",
  "callable_id": "leave_top_5_positive_trades_out_mbb_lcb95",
  "input_fields": ["trade_replay_snapshot"],
  "output_type": "decimal",
  "deterministic": true,
  "binary_float_allowed": false,
  "golden_vector_ids": [
    "trade-replay-top5-computed",
    "trade-replay-top5-inconclusive",
    "trade-replay-top5-funding-mismatch"
  ]
}
```

- [ ] **Step 5: Add three Golden Vectors**

Freeze one valid replay fixture with enough blocks, one valid replay with insufficient blocks, and one schema-valid but semantically invalid Funding assignment. Store literal expected status, value, and sorted reason codes. Update Registry version to `1.5.0`, Golden bundle version, Catalog version to `1.1.4`, all self-hashes, and remove this Estimator from the unavailable complement by virtue of registry inclusion.

- [ ] **Step 6: Run Golden and registry tests**

Run:

```bash
python -m unittest tests.test_estimators tests.test_trade_replay -v
```

Expected: Golden report passes; executable estimator count increases from 20 to 21 and unavailable count decreases from 37 to 36.

- [ ] **Step 7: Commit Task 4**

```bash
git add src/crypto_quant/estimators.py \
  config/estimator-registry-v1.schema.json \
  config/estimator-registry-v1.json \
  config/estimator-golden-vectors-v1.json \
  config/release-metrics-v1.1.json \
  tests/test_estimators.py tests/test_trade_replay.py
git commit -m "feat: register complete-trade replay estimator"
```

### Task 5: Bind Replay Evidence into Release Evaluation

**Files:**
- Modify: `config/release-evidence-v1.1.schema.json`
- Modify: `config/supporting-observation-bundle-v1.schema.json`
- Modify: `src/crypto_quant/release.py`
- Modify: `src/crypto_quant/release_artifacts.py`
- Modify: `tests/test_release.py`
- Modify: `tests/test_evidence.py`
- Modify: `tests/test_trade_replay.py`

**Interfaces:**
- Consumes: Gate inputs containing `trade_replay_snapshot`.
- Produces: frozen input proof and source-completeness validation for every metric resolved by the new Estimator.

- [ ] **Step 1: Write failing release/evidence tests**

Create a Top-5 Trade GateEvidence using the valid replay fixture. Assert its `frozen_release_inputs` requires `trade_replay_snapshot`, and Supporting Observation source hashes must include:

```text
replay_hash
source_series_hash
every source_economic_snapshot_hash
counterfactual_series.series_hash
every counterfactual_replay_period_hash
```

Add one test per omitted hash and expect `SUPPORTING_TRADE_REPLAY_SOURCE_INCOMPLETE:<metric_id>`. Add Scope and policy mismatch tests with exact reason prefixes.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
python -m unittest tests.test_release tests.test_evidence -v
```

Expected: frozen input Schema rejects the new proof or source omissions are not detected.

- [ ] **Step 3: Extend the release evidence schema**

Add `trade_replay_snapshot` to `$defs.frozenReleaseInputs.properties`. Add a conditional for the three metric IDs:

```text
baseline_leave_top_5_positive_trades_out_net_log_growth_lcb95
audit_base_leave_top5_positive_trades_net_log_growth_lcb95
audit_ai_leave_top5_positive_trades_net_log_growth_lcb95
```

The condition requires `trade_replay_snapshot` and `statistical_series_snapshot` proof entries.

- [ ] **Step 4: Freeze the replay artifact in metric inputs**

Extend `MetricResolver` and evaluator entry points with:

```python
trade_replay_snapshot: Optional[Mapping[str, Any]] = None
```

Add it only when the registered Estimator input field requires it. Freeze its `replay_id`, `replay_hash`, Schema ID, and canonical business hash. Do not allow callers to supply it to unrelated estimators.

- [ ] **Step 5: Verify Supporting Observation completeness**

In `validate_supporting_observation_bundle`, compare replay Scope/policy/experiment/capital fields to `expected_scope`. Independently construct the required source set from the validated Artifact and require it to be a subset of `source_hashes`. Add exact reasons:

```text
SUPPORTING_TRADE_REPLAY_SCOPE_MISMATCH:<metric_id>:<field>
SUPPORTING_TRADE_REPLAY_POLICY_MISMATCH:<metric_id>:<binding>
SUPPORTING_TRADE_REPLAY_REFERENCE_MISMATCH:<metric_id>:<field>
SUPPORTING_TRADE_REPLAY_SOURCE_INCOMPLETE:<metric_id>
```

- [ ] **Step 6: Prove all three release gates resolve normally**

In `tests/test_release.py`, evaluate Base, Audit Base, and Audit AI variants with a valid replay Artifact and assert their comparison result follows the Estimator Decimal. Repeat without the Artifact and assert fail-closed `ESTIMATOR_INPUT_MISSING:trade_replay_snapshot`.

- [ ] **Step 7: Run release/evidence tests**

Run:

```bash
python -m unittest tests.test_release tests.test_evidence tests.test_trade_replay -v
```

Expected: all tests pass.

- [ ] **Step 8: Commit Task 5**

```bash
git add config/release-evidence-v1.1.schema.json \
  config/supporting-observation-bundle-v1.schema.json \
  src/crypto_quant/release.py src/crypto_quant/release_artifacts.py \
  tests/test_release.py tests/test_evidence.py tests/test_trade_replay.py
git commit -m "feat: bind complete-trade replay evidence"
```

### Task 6: Publish v0.13.0 Artifacts and Documentation

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/crypto_quant/__init__.py`
- Modify: `src/crypto_quant/build.py`
- Modify: `config/evaluator-build-manifest-v1.json`
- Modify: `README.md`
- Create: `docs/adr/0013-complete-trade-counterfactual-replay.md`
- Create: `docs/implementation-status-v0.13.0.md`
- Modify: build and release tests that assert exact counts/versions.

**Interfaces:**
- Consumes: complete implementation and frozen config.
- Produces: reproducible evaluator build `0.13.0` and user-facing delivery record.

- [ ] **Step 1: Write failing version/build assertions**

Update tests to expect:

```text
package_version = 0.13.0
metric_catalog_version = 1.1.4
estimator_registry_version = 1.5.0
executable_estimator_count = 21
unavailable_estimator_count = 36
golden_vector_count = previous count + 3
```

Assert `config/trade-replay-snapshot-v1.schema.json` is in `EvaluatorBuild.expected_file_paths`.

- [ ] **Step 2: Run build tests and verify RED**

Run:

```bash
python -m unittest tests.test_estimators tests.test_release -v
```

Expected: package/build-manifest versions and frozen file set mismatch.

- [ ] **Step 3: Update package and frozen build inputs**

Set package and module versions to `0.13.0`. Add the TradeReplay Schema to `_FROZEN_CONFIG_PATHS`. Regenerate every manifest file hash, `build_input_tree_hash`, Registry/Golden self-hash, Golden report hash, and final manifest hash through the repository’s canonical helpers. Increment manifest version to `1.6.0`.

- [ ] **Step 4: Write ADR-0013**

Record the approved zero-to-zero definition, rejected alternatives, event-sequence requirement, original-path reproduction gate, conservative cost behavior, Funding binding, and why synthetic fixtures are not profit evidence.

- [ ] **Step 5: Write implementation status v0.13.0**

List exact implementation files, executable/unavailable counts, Golden count, tests, and remaining fail-closed items. Set the next increment to Holm correction, CI width/MERE power, paired risk efficiency, offline paper pipeline, and first sealed non-Golden evidence.

- [ ] **Step 6: Update README**

Add v0.13.0 to the delivery history. Explain in plain language that the system can now test whether five completed trades dominate profits, but still cannot claim the strategy or AI earns money without sealed historical/paper evidence.

- [ ] **Step 7: Run targeted build validation**

Run:

```bash
python -m unittest tests.test_estimators tests.test_release tests.test_trade_replay -v
make validate
```

Expected: all targeted tests and deterministic manifest validation pass.

- [ ] **Step 8: Commit Task 6**

```bash
git add pyproject.toml src/crypto_quant/__init__.py src/crypto_quant/build.py \
  config/evaluator-build-manifest-v1.json README.md \
  docs/adr/0013-complete-trade-counterfactual-replay.md \
  docs/implementation-status-v0.13.0.md \
  tests/test_estimators.py tests/test_release.py
git commit -m "chore: publish evaluator build v0.13.0"
```

### Task 7: Full Verification, Audit, and Tag

**Files:**
- Modify only if verification exposes a defect; every fix must start with a reproducing failing test.

**Interfaces:**
- Consumes: all v0.13 commits.
- Produces: verified Git state and annotated `v0.13.0` tag.

- [ ] **Step 1: Run whitespace and repository checks**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; only intended plan-tracking edits, if any.

- [ ] **Step 2: Run the entire automated suite**

Run:

```bash
make test
```

Expected: every test passes with zero failures/errors.

- [ ] **Step 3: Run deterministic artifact validation**

Run:

```bash
make validate
```

Expected: all JSON Schemas validate, all self-hashes/build hashes match, and all Golden Vectors pass.

- [ ] **Step 4: Run production-policy audit**

Run:

```bash
PYTHONPATH=src python3 scripts/validate_release_config.py
PYTHONPATH=src python3 scripts/validate_governance_templates.py
```

Expected: the release config reports that the design baseline cannot produce a production PASS, and governance validation reports `production_eligible=false`; neither failure-closed result is caused by the new Top-5 Estimator being unavailable.

- [ ] **Step 5: Audit requirement coverage**

For each numbered behavior in design section 9, point to a named passing test. Confirm the three Top-5 Trade gates resolve through the new Estimator; confirm no Broker/API-key/real-order code was added; confirm documentation counts match runtime counts.

- [ ] **Step 6: Confirm final Git state**

Run:

```bash
git log --oneline --decorate -8
git status --short
```

Expected: clean worktree, implementation commits present, current branch `main`.

- [ ] **Step 7: Create the release tag**

Run:

```bash
git tag -a v0.13.0 -m "v0.13.0 complete-trade counterfactual replay"
git show --stat --oneline v0.13.0
```

Expected: tag resolves to the verified v0.13.0 release commit.
