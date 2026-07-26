# Replayable Statistical Decision Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Holm family adjustment, actual primary-endpoint CI width, and achieved power at the frozen MERE executable from one immutable, replayable statistical decision artifact.

**Architecture:** A strict `StatisticalDecisionSnapshot v1` embeds the cumulative trial registry and every evaluated candidate's trusted `StatisticalSeriesSnapshot`. A deterministic Decimal-only replay engine derives centered moving-block-bootstrap p-values, percentile CI width, Holm step-down decisions, ESS, and shifted-bootstrap power; three estimators consume that same artifact. Release evidence freezes the artifact and verifies its family, source, experiment, policy, scope, and sample bindings before any gate can pass.

**Tech Stack:** Python 3.9+, `Decimal`, JSON Schema Draft 2020-12, RFC8785/JCS-style canonicalization, SHA-256, deterministic moving-block bootstrap, `unittest`, existing Estimator Registry and release evaluator.

## Global Constraints

- The source of truth is `docs/superpowers/specs/2026-07-27-statistical-decision-evidence-design.md`.
- One snapshot covers one ledger, route, direction, venue, deployment line, evaluation window, endpoint, and approved capital.
- Every cumulative trial remains in the Holm family; `ABORTED`, `FAILED`, and `INVALID` trials use raw p-value `1`.
- Every `EVALUATED` trial embeds a self-hashed `StatisticalSeriesSnapshot`; no estimator accepts uploaded p-value, CI, power, or ESS scalars.
- Holm order is `(raw_p_value ASC, candidate_id ASC)` and stops after the first failed comparison.
- All business arithmetic uses canonical `Decimal`; binary float is forbidden.
- Bootstrap sampling exactly reuses `MBB_V1`, overlapping non-circular blocks, truncation to `n`, and the frozen seed.
- Source series retain `confidence_side=LOWER_ONE_SIDED`; the decision artifact uses `TWO_SIDED` for precision, so validators compare every shared bootstrap field except `confidence_side`.
- A structurally valid sample limitation is `INCONCLUSIVE`; any hash, binding, family, scope, design, or cached-result mismatch is `FAIL`.
- Production remains disabled; no Broker, exchange adapter, API key, or real-order capability is added.
- The final package version is `0.14.0`.

## File Structure

- Create `src/crypto_quant/statistical_decision.py`: artifact hash/build/validation, MBB replay, p-value, CI, Holm, ESS, power, and the three estimator callables.
- Create `config/statistical-decision-snapshot-v1.schema.json`: strict external artifact contract with conditional computed/inconclusive and evaluated/non-evaluated shapes.
- Create `tests/test_statistical_decision.py`: unit, mutation, tie-break, Decimal-context, and inconclusive tests.
- Modify `tests/factories.py`: deterministic statistical family fixture.
- Modify `src/crypto_quant/estimators.py` and `config/estimator-registry-v1.schema.json`: load the new artifact schema and expose/permit the three callables.
- Modify `config/estimator-registry-v1.json`, `config/estimator-golden-vectors-v1.json`, and their tests: publish executable implementations and deterministic vectors.
- Modify `config/release-metrics-v1.1.json`, `config/release-gates-v1.1.json`, `tests/test_release.py`, and `tests/test_governance.py`: add executable Holm metrics and required gates.
- Modify `src/crypto_quant/release.py`, `src/crypto_quant/release_artifacts.py`, `config/release-evidence-v1.1.schema.json`, `tests/test_evidence.py`, and `tests/test_release.py`: bind the artifact and verify every family source in Gate Evidence and Supporting Observations.
- Modify `src/crypto_quant/build.py`, `config/evaluator-build-manifest-v1.json`, `pyproject.toml`, `README.md`, and release documentation: freeze and publish v0.14.0.
- Refresh `config/evaluator-build-manifest-v1.json` mechanically after every task that changes a frozen source/config file, so intermediate commits remain loadable; Task 5 applies the final v0.14 version and evidence values.
- Create `docs/adr/0014-replayable-statistical-decision-evidence.md` and `docs/implementation-status-v0.14.0.md`: record exact semantics, verification evidence, and remaining fail-closed scope.

---

### Task 1: Build the Statistical Decision Artifact and Replay Engine

**Files:**
- Create: `src/crypto_quant/statistical_decision.py`
- Create: `config/statistical-decision-snapshot-v1.schema.json`
- Create: `tests/test_statistical_decision.py`
- Modify: `tests/factories.py`

**Interfaces:**
- Consumes: valid `StatisticalSeriesSnapshot` mappings and a manifest-compatible cumulative trial registry.
- Produces:

```python
def statistical_trial_registry_hash(
    trial_registry: Sequence[Mapping[str, Any]],
) -> str

def statistical_decision_snapshot_hash(
    snapshot: Mapping[str, Any],
) -> str

def build_statistical_decision_snapshot(
    *,
    snapshot_id: str,
    trial_family_id: str,
    current_candidate_id: str,
    release_gate_policy_id: str,
    release_gate_policy_version: str,
    metric_catalog_id: str,
    metric_catalog_version: str,
    statistical_design_policy_id: str,
    statistical_design_policy_hash: str,
    experiment_manifest_id: str,
    experiment_manifest_hash: str,
    expected_actual_total_trials: int,
    expected_trial_registry_hash: str,
    scope: Mapping[str, Any],
    design: Mapping[str, Any],
    trial_registry: Sequence[Mapping[str, Any]],
    generated_at: str,
) -> Dict[str, Any]

def statistical_decision_snapshot_reasons(
    snapshot: Mapping[str, Any],
) -> Tuple[str, ...]

def primary_endpoint_ci_width(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]

def achieved_power_at_mere(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]

def holm_family_adjusted_primary_pass(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]
```

- `statistical_trial_registry_hash` hashes only each member's candidate/status/recipe identity and source series hash, not the embedded source document:

```python
[
    {
        "candidate_id": item["candidate_id"],
        "candidate_status": item["candidate_status"],
        "recipe_release_id": item["recipe_release_id"],
        "recipe_release_hash": item["recipe_release_hash"],
        "source_series_hash": item["source_series_hash"],
    }
    for item in sorted(trial_registry, key=lambda value: value["candidate_id"])
]
```

- All three estimator callables take exactly `{"statistical_decision_snapshot": snapshot}`.

- [ ] **Step 1: Add the deterministic family fixture**

Add this public factory boundary in `tests/factories.py`:

```python
def statistical_decision_inputs(
    *,
    current_values=("4", "5", "6", "7", "8", "9"),
    competitor_values=("1", "1", "2", "1", "2", "1"),
    include_aborted=True,
    block_length=2,
    minimum_block_count=2,
    resample_count=1000,
    seed=29,
):
    """Return scope, design, trial registry, and manifest identity facts."""

def make_statistical_decision_snapshot(
    **fixture_overrides: Any,
) -> Dict[str, Any]:
    """Build the standard computed snapshot through the public builder."""
```

Construct `PRIMARY_ENDPOINT_CONTRIBUTION` series by deep-copying the existing complete-trade source-series fixture shape. Use:

```python
scope = {
    "evaluation_ledger": "OOS_LEDGER",
    "release_route": "BASELINE_ONLY",
    "direction": "LONG",
    "venue": "BINANCE_SPOT",
    "deployment_line_id": "line-statistical-decision",
    "deployment_line_hash": "a" * 64,
    "evaluation_window_start": "2025-01-01T00:00:00Z",
    "evaluation_window_end": "2025-01-07T00:00:00Z",
    "approved_production_capital_usdt": "1000",
    "endpoint_id": "PRIMARY_NET_GROWTH",
    "endpoint_unit": "log_growth",
    "endpoint_direction": "GREATER",
}
design = {
    "minimum_economic_effect": "2",
    "null_boundary": "0",
    "confidence_level": "0.95",
    "confidence_side": "TWO_SIDED",
    "ci_method": "PERCENTILE_MBB_V1",
    "raw_p_value_method": "CENTERED_MBB_GREATER_ADD_ONE_V1",
    "power_method": "SHIFTED_CENTERED_MBB_AT_MERE_V1",
    "effective_sample_method": "GEYER_INITIAL_POSITIVE_SEQUENCE_ESS_V1",
    "multiple_testing_method": "HOLM_V1",
    "family_wise_alpha": "0.05",
    "block_length": block_length,
    "minimum_block_count": minimum_block_count,
    "resample_count": resample_count,
    "seed": seed,
    "sampling_rule": "OVERLAPPING_NON_CIRCULAR_MBB_TRUNCATE_TO_N",
    "quantile_rule": "CONSERVATIVE_NEAREST_RANK_V1",
}
```

Use candidate IDs `candidate-current`, `candidate-competitor`, and optional `candidate-aborted`; recipes have matching IDs and distinct repeated-character hashes. The aborted member has both source fields `None`. Compute and return `expected_trial_registry_hash` by applying `business_hash` to the exact projection shown in Interfaces. Implement `make_statistical_decision_snapshot` by calling `statistical_decision_inputs(**fixture_overrides)` and passing every returned field into `build_statistical_decision_snapshot` with these fixed identities:

```python
snapshot_id="statistical-decision-fixture"
release_gate_policy_id="release-gates-v1.1"
release_gate_policy_version="1.1.5"
metric_catalog_id="release-metrics-v1.1"
metric_catalog_version="1.1.5"
statistical_design_policy_id="statistics-replay"
statistical_design_policy_hash="6" * 64
experiment_manifest_id="experiment-replay"
experiment_manifest_hash="7" * 64
generated_at="2025-01-07T00:00:00Z"
```

The Task 1 RED run fails at the production-module import; after implementation this helper is the shared fixture used by Task 2 and Task 4.

- [ ] **Step 2: Write the failing artifact and method tests**

Create `tests/test_statistical_decision.py` with `StatisticalDecisionTests(unittest.TestCase)` and these exact tests:

```text
test_builder_replays_ci_holm_ess_and_power
test_holm_ties_break_by_candidate_id
test_holm_stops_after_first_failed_step
test_aborted_trial_remains_in_family_with_p_one
test_trial_registry_omission_or_hash_mismatch_fails
test_source_series_tampering_fails_even_after_outer_rehash
test_cached_family_result_tampering_fails_after_outer_rehash
test_cached_ci_or_power_tampering_fails_after_outer_rehash
test_current_candidate_must_be_evaluated_and_match_scope
test_candidate_bootstrap_design_must_match_frozen_design
test_source_one_sided_lcb_and_decision_two_sided_ci_are_compatible
test_insufficient_blocks_builds_replayable_inconclusive_snapshot
test_zero_variance_builds_replayable_inconclusive_snapshot
test_bootstrap_resolution_below_holm_alpha_is_inconclusive
test_global_decimal_context_does_not_change_results_or_hash
```

The first test must assert literal invariants rather than only `not None`:

```python
self.assertEqual(snapshot["analysis_status"], "COMPUTED")
self.assertEqual(snapshot["analysis_reason_codes"], [])
self.assertEqual(len(snapshot["family_results"]), 3)
self.assertEqual(
    [row["candidate_id"] for row in snapshot["family_results"]],
    [
        row["candidate_id"]
        for row in sorted(
            snapshot["family_results"],
            key=lambda row: (Decimal(row["raw_p_value"]), row["candidate_id"]),
        )
    ],
)
self.assertEqual(
    snapshot["current_candidate_results"]["ci_width"],
    str(
        Decimal(snapshot["current_candidate_results"]["ci_upper"])
        - Decimal(snapshot["current_candidate_results"]["ci_lower"])
    ),
)
self.assertEqual(
    primary_endpoint_ci_width(
        {"statistical_decision_snapshot": snapshot}
    ),
    (
        "COMPUTED",
        snapshot["current_candidate_results"]["ci_width"],
        (),
    ),
)
self.assertEqual(
    holm_family_adjusted_primary_pass(
        {"statistical_decision_snapshot": snapshot}
    )[1],
    snapshot["current_candidate_results"]["holm_rejected"],
)
```

For every mutation test, deep-copy the valid snapshot, alter the named nested value, recompute only `snapshot_hash`, and assert an exact stable reason such as:

```text
STATISTICAL_DECISION_TRIAL_REGISTRY_HASH_MISMATCH
STATISTICAL_DECISION_SOURCE_SERIES_INVALID:candidate-current
STATISTICAL_DECISION_FAMILY_RESULTS_REPLAY_MISMATCH
STATISTICAL_DECISION_CURRENT_RESULTS_REPLAY_MISMATCH
STATISTICAL_DECISION_CURRENT_CANDIDATE_INVALID
STATISTICAL_DECISION_BOOTSTRAP_DESIGN_MISMATCH:candidate-current
```

For the three inconclusive cases assert:

```python
self.assertEqual(snapshot["analysis_status"], "INCONCLUSIVE")
self.assertEqual(snapshot["family_results"], [])
self.assertIsNone(snapshot["current_candidate_results"])
for estimator in (
    primary_endpoint_ci_width,
    achieved_power_at_mere,
    holm_family_adjusted_primary_pass,
):
    status, value, reasons = estimator(
        {"statistical_decision_snapshot": snapshot}
    )
    self.assertEqual(status, "INCONCLUSIVE")
    self.assertIsNone(value)
    self.assertEqual(reasons, tuple(snapshot["analysis_reason_codes"]))
```

- [ ] **Step 3: Run the new test module and verify RED**

Run:

```bash
python -m unittest tests.test_statistical_decision -v
```

Expected: import failure for `crypto_quant.statistical_decision`.

- [ ] **Step 4: Add the strict JSON Schema**

Create `config/statistical-decision-snapshot-v1.schema.json` with top-level `additionalProperties: false`, the complete required list from the design, and these exact conditionals:

```json
{
  "if": {
    "properties": {"analysis_status": {"const": "COMPUTED"}},
    "required": ["analysis_status"]
  },
  "then": {
    "properties": {
      "analysis_reason_codes": {"maxItems": 0},
      "family_results": {"minItems": 1},
      "current_candidate_results": {"$ref": "#/$defs/currentResults"}
    }
  },
  "else": {
    "properties": {
      "analysis_status": {"const": "INCONCLUSIVE"},
      "analysis_reason_codes": {"minItems": 1},
      "family_results": {"maxItems": 0},
      "current_candidate_results": {"type": "null"}
    }
  }
}
```

The Trial conditional is:

```json
{
  "if": {
    "properties": {"candidate_status": {"const": "EVALUATED"}},
    "required": ["candidate_status"]
  },
  "then": {
    "properties": {
      "source_series_snapshot": {"type": "object"},
      "source_series_hash": {"$ref": "#/$defs/sha256"}
    }
  },
  "else": {
    "properties": {
      "source_series_snapshot": {"type": "null"},
      "source_series_hash": {"type": "null"}
    }
  }
}
```

Use the repository's canonical Decimal regex:

```json
{"type": "string", "pattern": "^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$"}
```

Require `uniqueItems: true` for `analysis_reason_codes`; semantic validation, not Schema, enforces sorted uniqueness and candidate ID uniqueness.

- [ ] **Step 5: Implement deterministic MBB primitives**

In `src/crypto_quant/statistical_decision.py`, import `_draw_start`, `geyer_initial_positive_sequence_ess`, `statistical_series_hash`, and `statistical_series_reasons` from `statistics.py`; do not duplicate the PRNG rule.

Add fixed-context internal helpers:

```python
def _statistic(values: Sequence[Decimal], aggregation: str) -> Decimal:
    total = sum(values, Decimal("0"))
    return total if aggregation == "SUM" else total / Decimal(len(values))

def _mbb_replicates(
    values: Sequence[Decimal],
    *,
    design: Mapping[str, Any],
    aggregation: str,
) -> Tuple[Decimal, ...]:
    length = design["block_length"]
    start_count = len(values) - length + 1
    blocks_per_sample = (len(values) + length - 1) // length
    replicates = []
    for replicate in range(design["resample_count"]):
        sampled = []
        for draw in range(blocks_per_sample):
            start = _draw_start(
                seed=design["seed"],
                replicate=replicate,
                draw=draw,
                start_count=start_count,
            )
            sampled.extend(values[start : start + length])
        replicates.append(_statistic(sampled[: len(values)], aggregation))
    return tuple(replicates)

def _ceil_fraction(numerator: int, denominator: int) -> int:
    return (numerator + denominator - 1) // denominator
```

`_mbb_replicates` must use `_draw_start(seed, replicate, draw, start_count)`, truncate to `n`, compute the requested statistic, and return replicates in generation order. Quantile callers make their own sorted copy.

Use exact integer ranks:

```python
lower_rank = max(1, _ceil_fraction(B * 5, 200))
upper_rank = min(B, _ceil_fraction(B * 195, 200))
critical_rank = min(
    B,
    _ceil_fraction(
        B * (alpha_denominator - alpha_numerator),
        alpha_denominator,
    ),
)
```

Represent alpha as `Fraction(Decimal(alpha_string))`; never convert through float.

- [ ] **Step 6: Implement semantic replay and builders**

Add an internal immutable result:

```python
@dataclass(frozen=True)
class StatisticalDecisionReplay:
    status: str
    reason_codes: Tuple[str, ...]
    family_results: Tuple[Mapping[str, Any], ...]
    current_results: Optional[Mapping[str, Any]]
```

Implement `_replay_statistical_decision(snapshot, validate_cached=False)` in this order:

1. Validate IDs, hashes, timestamps, design constants, candidate uniqueness, current candidate, total Trial count, Registry projection hash, and family/manifest IDs.
2. For every EVALUATED member, call `statistical_series_reasons`, compare embedded/self/declaration hashes, compare scope fields and Bootstrap settings, and collect eligible Decimal values.
3. Record, but do not yet return, sample-limit reasons for insufficient blocks or zero variance.
4. Derive every evaluated raw p with the centered add-one rule where its sample is usable; assign exact `"1"` to non-evaluated members. A sample-limit reason makes the final artifact inconclusive, so its provisional p value is used only to determine the deterministic current rank and is never emitted as a computed family result.
5. Sort `(raw_p, candidate_id)`, derive each Holm threshold, add the resolution reason when `1 / (B + 1)` exceeds the current candidate threshold, and return `INCONCLUSIVE` with sorted unique reasons if any were recorded.
6. Apply Holm step-down and stop after the first failure.
7. For the current candidate, derive percentile CI, existing Geyer ESS, shifted-bootstrap power, and canonical result strings.
8. If `validate_cached=True`, compare derived status/reasons/family/current results with the Artifact caches and return exact replay mismatch reasons.

Use:

```python
def statistical_decision_snapshot_hash(snapshot):
    return artifact_self_hash(snapshot, "snapshot_hash")
```

The builder must assemble the zero-hash Artifact, call replay without cached comparison, populate either computed or inconclusive caches, set the final self-hash, and then require `statistical_decision_snapshot_reasons(artifact) == ()`. Invalid structure/binding input raises `ValueError`.

- [ ] **Step 7: Run focused tests and verify GREEN**

Run:

```bash
python -m unittest tests.test_statistical_decision -v
```

Expected: all Task 1 tests pass.

- [ ] **Step 8: Commit Task 1**

```bash
git add src/crypto_quant/statistical_decision.py \
  config/statistical-decision-snapshot-v1.schema.json \
  tests/test_statistical_decision.py tests/factories.py
git commit -m "feat: build replayable statistical decision snapshots"
```

### Task 2: Register the Three Executable Estimators

**Files:**
- Modify: `src/crypto_quant/estimators.py`
- Modify: `config/estimator-registry-v1.json`
- Modify: `config/estimator-registry-v1.schema.json`
- Modify: `config/estimator-golden-vectors-v1.json`
- Modify: `config/release-metrics-v1.1.json`
- Modify: `tests/test_estimators.py`

**Interfaces:**
- Consumes: the six public functions from Task 1 and the new JSON Schema.
- Produces executable Registry entries for:

```text
ACHIEVED_POWER_AT_MERE_V1
PRIMARY_ENDPOINT_CI_WIDTH_V1
HOLM_FAMILY_ADJUSTED_PRIMARY_PASS_V1
```

- [ ] **Step 1: Write failing Registry execution tests**

In `tests/test_estimators.py`, import the Task 1 builder/factory and add:

```python
def test_statistical_decision_estimators_are_executable(self):
    snapshot = make_statistical_decision_snapshot()
    expected = {
        "ACHIEVED_POWER_AT_MERE_V1": (
            "decimal",
            snapshot["current_candidate_results"]["achieved_power"],
        ),
        "PRIMARY_ENDPOINT_CI_WIDTH_V1": (
            "decimal",
            snapshot["current_candidate_results"]["ci_width"],
        ),
        "HOLM_FAMILY_ADJUSTED_PRIMARY_PASS_V1": (
            "boolean",
            snapshot["current_candidate_results"]["holm_rejected"],
        ),
    }
    for estimator_id, (_, expected_value) in expected.items():
        self.assertTrue(self.registry.is_executable(estimator_id))
        execution = self.registry.execute(
            estimator_id,
            {"statistical_decision_snapshot": snapshot},
        )
        self.assertEqual(execution.status, "COMPUTED")
        self.assertEqual(execution.value, expected_value)
```

Update the catalog/Registry partition assertions to the post-Task-3 final values:

```python
self.assertEqual(len(all_ids), 58)
self.assertEqual(len(executable), 24)
self.assertEqual(len(unavailable), 34)
```

Temporarily Task 2 will add the Holm algorithm to the catalog as part of its Registry prerequisite; Task 3 adds its metrics and gates.

- [ ] **Step 2: Run the focused Registry test and verify RED**

Run:

```bash
python -m unittest \
  tests.test_estimators.EstimatorRegistryTests.test_statistical_decision_estimators_are_executable -v
```

Expected: the Registry reports the three estimators unavailable or unknown.

- [ ] **Step 3: Load and route the new schema/callables**

In `src/crypto_quant/estimators.py`:

```python
from .statistical_decision import (
    achieved_power_at_mere,
    holm_family_adjusted_primary_pass,
    primary_endpoint_ci_width,
)
```

Add exact callable map entries:

```python
"achieved_power_at_mere": achieved_power_at_mere,
"primary_endpoint_ci_width": primary_endpoint_ci_width,
"holm_family_adjusted_primary_pass": holm_family_adjusted_primary_pass,
```

Add the same three callable IDs to the `callable_id` enum in
`config/estimator-registry-v1.schema.json`.

Load `statistical-decision-snapshot-v1.schema.json`, call `Draft202012Validator.check_schema`, retain it on the Registry instance beside the existing artifact schemas, and include its validation in fixture loading.

- [ ] **Step 4: Add exact Registry implementations**

Bump `registry_version` from `1.5.0` to `1.6.0` and Golden
`bundle_version` from `1.2.0` to `1.3.0`, then add:

```json
{
  "estimator_id": "ACHIEVED_POWER_AT_MERE_V1",
  "implementation_id": "statistical_decision.achieved-power-at-mere",
  "implementation_version": "1.0.0",
  "callable_id": "achieved_power_at_mere",
  "input_fields": ["statistical_decision_snapshot"],
  "output_type": "decimal",
  "deterministic": true,
  "binary_float_allowed": false,
  "golden_vector_ids": [
    "statistical-decision-power-computed",
    "statistical-decision-power-inconclusive"
  ]
}
```

Add equivalent entries:

```text
PRIMARY_ENDPOINT_CI_WIDTH_V1
implementation_id = statistical_decision.primary-endpoint-ci-width
callable_id = primary_endpoint_ci_width
vectors = statistical-decision-ci-computed, statistical-decision-ci-inconclusive

HOLM_FAMILY_ADJUSTED_PRIMARY_PASS_V1
implementation_id = statistical_decision.holm-family-adjusted-primary-pass
callable_id = holm_family_adjusted_primary_pass
output_type = boolean
vectors = statistical-decision-holm-computed, statistical-decision-holm-inconclusive
```

Add `HOLM_FAMILY_ADJUSTED_PRIMARY_PASS_V1` to `release-metrics-v1.1.json.algorithms` with:

```json
{
  "family_source": "StatisticalDecisionSnapshot cumulative trial registry",
  "method": "HOLM_STEP_DOWN",
  "familywise_alpha_source": "ReleaseGatePolicy",
  "missing_or_incomplete_family": "FAIL"
}
```

- [ ] **Step 5: Add deterministic Golden fixtures and vectors**

Build one computed and one insufficient-block snapshot through the public builder, serialize them into `config/estimator-golden-vectors-v1.json.fixtures` under:

```text
statistical-decision-computed
statistical-decision-inconclusive
```

Add six vectors named exactly as listed in Step 4. Copy literal expected values from the just-built snapshots; do not hand-calculate or round them. The inconclusive vectors all use:

```json
{
  "expected_status": "INCONCLUSIVE",
  "expected_value": null,
  "expected_reason_codes": ["STATISTICAL_DECISION_INSUFFICIENT_BLOCKS:candidate-current"]
}
```

Recompute the Golden `bundle_hash` and Registry `registry_hash` with `artifact_self_hash`; then update `estimator_registry_hash` in the Golden bundle and recompute the bundle hash again.

Run the complete Golden report once and update
`test_golden_vectors_are_deterministic` to assert `39` plus the literal new
`report_hash` printed by that run. Keep the 100-run equality check.

- [ ] **Step 6: Run Registry and Golden tests**

Run:

```bash
python -m unittest tests.test_estimators -v
```

Expected: Registry schema, input contracts, 39 Golden vectors, and the new executable estimator test pass. The build-manifest test may still fail until Task 5 and is excluded by running:

```bash
python -m unittest tests.test_estimators.EstimatorRegistryTests -v
```

- [ ] **Step 7: Commit Task 2**

```bash
git add src/crypto_quant/estimators.py \
  config/estimator-registry-v1.json \
  config/estimator-registry-v1.schema.json \
  config/estimator-golden-vectors-v1.json \
  config/release-metrics-v1.1.json \
  tests/test_estimators.py
git commit -m "feat: execute statistical decision estimators"
```

### Task 3: Make Holm, CI Width, and Power Required Policy Gates

**Files:**
- Modify: `config/release-metrics-v1.1.json`
- Modify: `config/release-gates-v1.1.json`
- Modify: `tests/test_release.py`
- Modify: `tests/test_governance.py`

**Interfaces:**
- Consumes: the three executable Estimator IDs from Task 2.
- Produces two new exact metrics and required Holm gates in `SAMPLE` and `AUDIT_BASE_ARM`; existing CI/power gates become executable without changing their IDs or thresholds.

- [ ] **Step 1: Write failing policy-shape tests**

Add to `tests/test_release.py`:

```python
def test_statistical_decision_gates_are_required(self):
    sample = {
        gate["gate_id"]: gate
        for gate in self.bundle.policy["gates"]["SAMPLE"]
    }
    audit = {
        gate["gate_id"]: gate
        for gate in self.bundle.policy["gates"]["AUDIT_BASE_ARM"]
    }
    self.assertEqual(
        sample["HOLM_ADJUSTED_PRIMARY_PASS"],
        {
            "gate_id": "HOLM_ADJUSTED_PRIMARY_PASS",
            "required": True,
            "metric_id": "primary_endpoint_holm_adjusted_pass",
            "comparator": "EQ",
            "threshold": True,
        },
    )
    self.assertEqual(
        audit["AUDIT_BASE_HOLM_ADJUSTED_PRIMARY_PASS"]["metric_id"],
        "audit_primary_endpoint_holm_adjusted_pass",
    )
```

Also assert:

```python
self.assertTrue(
    self.bundle.estimators.is_executable("ACHIEVED_POWER_AT_MERE_V1")
)
self.assertTrue(
    self.bundle.estimators.is_executable("PRIMARY_ENDPOINT_CI_WIDTH_V1")
)
self.assertTrue(
    self.bundle.estimators.is_executable(
        "HOLM_FAMILY_ADJUSTED_PRIMARY_PASS_V1"
    )
)
```

- [ ] **Step 2: Run the policy test and verify RED**

Run:

```bash
python -m unittest \
  tests.test_release.ReleaseEvaluatorTests.test_statistical_decision_gates_are_required -v
```

Expected: missing `HOLM_ADJUSTED_PRIMARY_PASS`.

- [ ] **Step 3: Update Metric Catalog definitions**

Bump `catalog_version` from `1.1.4` to `1.1.5`. Add exact overrides:

```json
"primary_endpoint_holm_adjusted_pass": {
  "value_type": "boolean",
  "unit": "boolean",
  "estimator_id": "HOLM_FAMILY_ADJUSTED_PRIMARY_PASS_V1"
},
"audit_primary_endpoint_holm_adjusted_pass": {
  "value_type": "boolean",
  "unit": "boolean",
  "estimator_id": "HOLM_FAMILY_ADJUSTED_PRIMARY_PASS_V1"
}
```

Keep the existing metric IDs and estimator IDs for power and CI. Update Registry and Golden `metric_catalog_version` to `1.1.5`, recompute their self hashes, and update the Golden Registry hash binding.

- [ ] **Step 4: Add required Holm gates**

First bump `config/release-gates-v1.1.json.policy_version` from `1.1.4` to
`1.1.5`; the gate set changes, so retaining the old policy version is
forbidden.

Insert after `STATISTICAL_DESIGN_FROZEN` in `SAMPLE`:

```json
{
  "gate_id": "HOLM_ADJUSTED_PRIMARY_PASS",
  "required": true,
  "metric_id": "primary_endpoint_holm_adjusted_pass",
  "comparator": "EQ",
  "threshold": true
}
```

Insert first in `AUDIT_BASE_ARM`:

```json
{
  "gate_id": "AUDIT_BASE_HOLM_ADJUSTED_PRIMARY_PASS",
  "required": true,
  "metric_id": "audit_primary_endpoint_holm_adjusted_pass",
  "comparator": "EQ",
  "threshold": true
}
```

Do not change the existing `0.80` power threshold or StatisticalDesignPolicy CI threshold references.

- [ ] **Step 5: Update policy count and referential-integrity assertions**

Where tests assert exact gate/catalog counts, update them to:

```text
Catalog algorithms: 58
Catalog exact overrides: 87
Policy gates: 151
Executable estimators: 24
Unavailable estimators: 34
```

Derive actual values with `jq` before editing the assertions; if the exact override baseline differs from 85 because another committed task changed it, use `baseline + 2`, document the observed number in the commit body, and keep the algorithm/gate increments exactly `+1` and `+2`.

- [ ] **Step 6: Run policy and governance tests**

Run:

```bash
python -m unittest tests.test_release tests.test_governance -v
```

Expected: all tests pass except evidence cases that intentionally gain the new required artifact in Task 4; update only fixture gate counts here, not trust-chain behavior.

- [ ] **Step 7: Commit Task 3**

```bash
git add config/release-metrics-v1.1.json \
  config/release-gates-v1.1.json \
  config/estimator-registry-v1.json \
  config/estimator-golden-vectors-v1.json \
  tests/test_release.py tests/test_governance.py
git commit -m "feat: require replayed Holm precision and power gates"
```

### Task 4: Bind Statistical Decisions into Release Evidence

**Files:**
- Modify: `src/crypto_quant/release.py`
- Modify: `src/crypto_quant/release_artifacts.py`
- Modify: `config/release-evidence-v1.1.schema.json`
- Modify: `tests/test_evidence.py`
- Modify: `tests/test_release.py`
- Modify: `tests/test_governance.py`

**Interfaces:**
- Consumes: trusted `statistical_decision_snapshot`, `experiment_manifest`, StatisticalDesignPolicy binding, GateEvidence scope, and Supporting Observation source hashes.
- Produces:

```python
_STATISTICAL_DECISION_ESTIMATOR_IDS = frozenset({
    "ACHIEVED_POWER_AT_MERE_V1",
    "PRIMARY_ENDPOINT_CI_WIDTH_V1",
    "HOLM_FAMILY_ADJUSTED_PRIMARY_PASS_V1",
})

def _statistical_decision_reference_reasons(
    evidence: Mapping[str, Any],
    trust: EvidenceTrustContext,
) -> Tuple[str, ...]
```

- [ ] **Step 1: Add a complete trusted-evidence fixture**

In `tests/test_evidence.py`, add a helper that builds a computed StatisticalDecisionSnapshot and inserts:

```python
evidence["frozen_release_inputs"]["statistical_decision_snapshot"] = {
    "artifact_id": snapshot["snapshot_id"],
    "artifact_hash": snapshot["snapshot_hash"],
    "frozen_at": "2025-01-01T00:00:00Z",
}
trust.artifact_documents["statistical_decision_snapshot"] = snapshot
trust.artifact_hashes["statistical_decision_snapshot"] = snapshot["snapshot_hash"]
```

Append to `evidence["artifact_hashes"]`:

```python
snapshot["snapshot_hash"]
snapshot["trial_registry_hash"]
*[item["source_series_hash"] for item in snapshot["trial_registry"]
  if item["candidate_status"] == "EVALUATED"]
```

The fixture's ExperimentManifest must set:

```python
manifest["economics"]["trial_family_id"] = snapshot["trial_family_id"]
manifest["economics"]["minimum_economic_effect"] = (
    snapshot["design"]["minimum_economic_effect"]
)
manifest["economics"]["multiplicity_method"] = "HOLM"
manifest["economics"]["family_wise_alpha"] = "0.05"
manifest["search_budget"]["actual_total_trials"] = len(
    snapshot["trial_registry"]
)
manifest["search_budget"]["trial_registry_hash"] = (
    snapshot["trial_registry_hash"]
)
```

Recompute the manifest self hash and propagate the new hash into Snapshot, Evidence freeze proof, and Trust Context before the final Snapshot hash is built.

- [ ] **Step 2: Write failing trust-chain mutation tests**

Add these exact tests:

```text
test_statistical_decision_gate_uses_trusted_snapshot_not_claimed_scalar
test_statistical_decision_freeze_id_and_hash_must_match
test_statistical_decision_scope_recipe_and_window_must_match_evidence
test_statistical_decision_manifest_family_and_trial_count_must_match
test_statistical_decision_policy_and_catalog_identity_must_match
test_statistical_decision_all_family_source_hashes_are_required
test_statistical_decision_effective_event_count_must_match_sample_status
test_statistical_decision_inconclusive_cannot_pass_gate
```

Use exact expected reasons:

```text
STATISTICAL_DECISION_DOCUMENT_MISSING
STATISTICAL_DECISION_FREEZE_ID_MISMATCH
STATISTICAL_DECISION_FREEZE_HASH_MISMATCH
STATISTICAL_DECISION_TRUST_HASH_MISMATCH
STATISTICAL_DECISION_SCOPE_MISMATCH:<field>
STATISTICAL_DECISION_RECIPE_MISMATCH
STATISTICAL_DECISION_EXPERIMENT_MISMATCH
STATISTICAL_DECISION_TRIAL_COUNT_MISMATCH
STATISTICAL_DECISION_TRIAL_REGISTRY_HASH_MISMATCH
STATISTICAL_DECISION_POLICY_IDENTITY_MISMATCH
STATISTICAL_DECISION_SOURCE_HASH_MISSING:<candidate_id>
STATISTICAL_DECISION_SAMPLE_ESS_MISMATCH
```

- [ ] **Step 3: Run the mutation tests and verify RED**

Run:

```bash
python -m unittest tests.test_evidence -v
```

Expected: new statistical-decision cases fail because the artifact is not routed or referenced.

- [ ] **Step 4: Extend Evidence and release-artifact schema loading**

Add to `frozen_release_inputs.properties` in `config/release-evidence-v1.1.schema.json`:

```json
"statistical_decision_snapshot": {"$ref": "#/$defs/freezeProof"}
```

In the Estimator-dependent conditional, require this freeze proof whenever `estimator_id` is one of the three Task 2 IDs. Do not also require `trade_replay_snapshot`.

Add `statistical_decision_snapshot` to both `PolicyBundle._SCHEMAS` in
`src/crypto_quant/release.py` and `load_release_artifact_schemas` in
`src/crypto_quant/release_artifacts.py`:

```python
"statistical_decision_snapshot": _load_json_strict(
    Path(config_dir) / "statistical-decision-snapshot-v1.schema.json"
),
```

Update the release-artifact schema-count assertion in `tests/test_governance.py`
from the observed baseline to `baseline + 1`.

- [ ] **Step 5: Route the artifact to all three Estimators**

In `PolicyBundle._estimator_inputs`, add parameter:

```python
statistical_decision_snapshot: Optional[Mapping[str, Any]] = None
```

Before the StatisticalSeries route:

```python
if estimator_id in _STATISTICAL_DECISION_ESTIMATOR_IDS:
    return {
        "statistical_decision_snapshot": statistical_decision_snapshot,
    }
```

In gate evaluation, retrieve:

```python
statistical_decision = trust.artifact_documents.get(
    "statistical_decision_snapshot"
)
```

Run the dedicated reference validator for all three IDs, then pass only the trusted mapping into `_estimator_inputs`. Never read `observed_value`, `achieved_power`, `ci_width`, or p-value claims from GateEvidence as estimator input.

- [ ] **Step 6: Implement complete reference validation**

`_statistical_decision_reference_reasons` must:

1. Require document, freeze proof, Trust Context hash, valid self-hash, `replay_verified`, and `statistical_decision_snapshot_reasons(snapshot) == ()`.
2. Compare Artifact policy/catalog/experiment identity to the loaded PolicyBundle and trusted ExperimentManifest.
3. Compare Manifest `trial_family_id`, MERE, Holm method, alpha, `actual_total_trials`, and `trial_registry_hash`.
4. Compare GateEvidence scope fields, current candidate recipe, approved capital, endpoint, and evaluation window.
5. Require `snapshot_hash`, `trial_registry_hash`, and every evaluated source series hash in Evidence `artifact_hashes`.
6. Compare current `effective_event_count` to `evidence.sample_status.effective_event_count` with integer/non-boolean semantics.

Deduplicate with `tuple(sorted(set(reasons)))`. Reference failures must keep the Gate result `FAIL` even if the cached Artifact estimator result is favorable.

Because `_statistical_decision_reference_reasons` does not receive the
Supporting Observation bundle, enforce Supporting Observation completeness inside
`validate_supporting_observation_bundle`. When an observation estimator is in
`_STATISTICAL_DECISION_ESTIMATOR_IDS`, read its
`estimator_inputs.statistical_decision_snapshot` and require:

```python
required_sources = {
    snapshot["snapshot_hash"],
    snapshot["trial_registry_hash"],
    *(
        member["source_series_hash"]
        for member in snapshot["trial_registry"]
        if member["candidate_status"] == "EVALUATED"
    ),
}
if not required_sources.issubset(set(source_hashes)):
    reasons.append(
        f"SUPPORTING_STATISTICAL_DECISION_SOURCE_MISSING:{metric_id}"
    )
```

Keep the existing generic Schema; its `source_artifact_hashes` array already
accepts the required unique hashes.

- [ ] **Step 7: Run evidence and release tests**

Run:

```bash
python -m unittest tests.test_evidence tests.test_release -v
```

Expected: all trust, scope, binding, and gate evaluation tests pass.

- [ ] **Step 8: Commit Task 4**

```bash
git add src/crypto_quant/release.py src/crypto_quant/release_artifacts.py \
  config/release-evidence-v1.1.schema.json \
  tests/test_evidence.py tests/test_release.py
git commit -m "feat: bind statistical decisions to release evidence"
```

### Task 5: Freeze the Evaluator Build and Publish v0.14.0

**Files:**
- Modify: `src/crypto_quant/build.py`
- Modify: `config/evaluator-build-manifest-v1.json`
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `tests/test_estimators.py`
- Create: `docs/adr/0014-replayable-statistical-decision-evidence.md`
- Create: `docs/implementation-status-v0.14.0.md`

**Interfaces:**
- Consumes: the completed source/config/test state from Tasks 1-4.
- Produces: a self-consistent v0.14.0 build manifest, ADR, status report, annotated Git tag, and clean merged `main`.

- [ ] **Step 1: Add failing build-manifest expectations**

Update `EvaluatorBuildTests.test_manifest_binds_complete_evaluator_file_set`:

```python
self.assertIn(
    "config/statistical-decision-snapshot-v1.schema.json",
    expected,
)
self.assertIn("src/crypto_quant/statistical_decision.py", expected)
self.assertEqual(manifest["manifest_version"], "1.7.0")
self.assertEqual(manifest["package_version"], "0.14.0")
self.assertEqual(manifest["metric_catalog_version"], "1.1.5")
self.assertEqual(manifest["golden_vector_count"], 39)
self.assertEqual(build.executable_estimator_count, 24)
self.assertEqual(build.unavailable_estimator_count, 34)
```

- [ ] **Step 2: Run the build test and verify RED**

Run:

```bash
python -m unittest \
  tests.test_estimators.EvaluatorBuildTests.test_manifest_binds_complete_evaluator_file_set -v
```

Expected: missing new Schema and v0.13 manifest/version values.

- [ ] **Step 3: Freeze the new build input**

Add to `_FROZEN_CONFIG_PATHS` in `src/crypto_quant/build.py`:

```python
"config/statistical-decision-snapshot-v1.schema.json",
```

`src/crypto_quant/statistical_decision.py` is included automatically by the existing source glob.

Set:

```toml
# pyproject.toml
version = "0.14.0"
```

In `config/evaluator-build-manifest-v1.json`, set:

```text
manifest_version = 1.7.0
package_version = 0.14.0
metric_catalog_version = 1.1.5
catalog_algorithm_count = 58
golden_vector_count = 39
executable_estimator_count = 24
unavailable_estimator_count = 34
```

Mechanically recompute every `file_hashes` entry from `EvaluatorBuild.expected_file_paths`, then `build_input_tree_hash`, then `manifest_hash`. Do not manually copy file hashes.

- [ ] **Step 4: Write the ADR**

Create `docs/adr/0014-replayable-statistical-decision-evidence.md` with:

```text
Status: Accepted
Context: policy declared Holm/power/CI but no replayable execution existed
Decision: one unified StatisticalDecisionSnapshot
Math: exact raw p, CI ranks, Holm step-down, shifted MBB power
Family rule: failed/aborted/invalid trials remain with p=1
Trust: full source/hash/manifest/policy/evidence bindings
Consequences: stronger false-positive control; larger artifacts and conservative power
Rejected alternatives: scalar claims; split artifacts
Safety: production remains disabled
```

Copy formulas exactly from the approved design; do not redefine them.

- [ ] **Step 5: Write the implementation status**

Create `docs/implementation-status-v0.14.0.md` and record:

- the three newly executable estimators;
- exact total/executable/unavailable estimator counts;
- Golden vector count and final report hash;
- full unit-test count and command;
- final evaluator build hash;
- new required Gate IDs;
- mutation/fail-closed coverage;
- unchanged `DESIGN_BASELINE` and production-disabled state;
- remaining work in order:
  1. paired risk-efficiency intervals;
  2. offline Paper evidence ingestion;
  3. sealed real evidence population and independent review.

- [ ] **Step 6: Update README without profitability claims**

Change the current version to `0.14.0`, add links to the new Schema, ADR, and status document, and replace the v0.13 capability paragraph with:

```text
系统可以从累计 Trial Registry 和冻结统计序列重放原始 p 值、Holm
step-down、双侧区间宽度、ESS 和 MERE 功效；失败/中止/无效 Trial
不会因删除或改名逃避 family 惩罚。仓库仍只有合成 Golden Fixture，
不能声称策略已经赚钱或 AI 已优于基线。
```

Keep the explicit no-Broker/no-key/no-real-order statement.

- [ ] **Step 7: Run focused verification**

Run:

```bash
python -m unittest \
  tests.test_statistical_decision \
  tests.test_estimators \
  tests.test_release \
  tests.test_evidence \
  tests.test_governance -v
```

Expected: all focused tests pass.

- [ ] **Step 8: Run complete verification**

Run:

```bash
python -m unittest discover -s tests -v
make validate
git diff --check
git status --short
```

Expected:

- every unit test passes;
- schema, governance, Registry, Golden Vector, evaluator build, and release validation pass;
- policy evaluation may still report intentional Fail-Closed `DESIGN_BASELINE`/missing real bindings, but `make validate` exits `0`;
- `git diff --check` has no output;
- only intended v0.14 files are modified.

Copy the actual test count, Golden report hash, and evaluator build hash into `docs/implementation-status-v0.14.0.md`; then mechanically refresh the build manifest once more because the status/README files are not frozen inputs, while source/config/version changes already are.

- [ ] **Step 9: Commit Task 5**

```bash
git add src/crypto_quant/build.py \
  config/evaluator-build-manifest-v1.json \
  pyproject.toml README.md tests/test_estimators.py \
  docs/adr/0014-replayable-statistical-decision-evidence.md \
  docs/implementation-status-v0.14.0.md
git commit -m "chore: publish evaluator build v0.14.0"
```

- [ ] **Step 10: Review, merge, and tag**

Use `superpowers:requesting-code-review` on the complete diff. Apply only verified findings through `superpowers:receiving-code-review`, rerun Step 8, then use `superpowers:finishing-a-development-branch` to merge the isolated branch into `main`.

On clean `main`, rerun:

```bash
python -m unittest discover -s tests -v
make validate
```

Then create:

```bash
git tag -a v0.14.0 -m "v0.14.0 replayable statistical decision evidence"
```

Verify:

```bash
git status --short
git log -8 --oneline --decorate
git tag -n1 v0.14.0
```

Expected: clean `main`, passing verification, and annotated `v0.14.0` on the final release commit.
