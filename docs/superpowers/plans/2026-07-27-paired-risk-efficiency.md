# Paired Risk-Efficiency Interval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Use `superpowers:test-driven-development` for every behavior change and `superpowers:verification-before-completion` before any completion claim.

**Goal:** Make paired maximum-drawdown and ES95 relative-improvement lower bounds executable, replayable, and release-bound for both AI-vs-baseline and Minor candidate-vs-active comparisons.

**Architecture:** A new `PairedRiskEvaluationSnapshot v1` embeds two trusted primary-endpoint series plus their exact EconomicLedgerSnapshot sources, derives complete reference/candidate pairs, replays cash-flow-adjusted log-return path segments, and binds comparison subjects. Two deterministic estimators apply identical paired moving-block indices to both arms, rebuild MDD or empirical ES95 inside every replicate, normalize risk reduction by the observed reference risk, and return a conservative one-sided 95% lower bound. Release evidence and supporting observations bind the entire nested artifact chain and never fall back to uploaded scalars.

**Tech Stack:** Python 3.9+, `Decimal`, JSON Schema Draft 2020-12, RFC8785/JCS-style canonicalization, SHA-256, existing EconomicLedgerSnapshot and StatisticalSeriesSnapshot contracts, existing deterministic MBB draw kernel, `unittest`.

## Global Constraints

- `RISK_EFFICIENCY` is the only valid endpoint for the new artifact and estimators.
- Reference/candidate are generic arm roles; do not overload legacy baseline/AI roles for Minor refresh.
- Every StatisticalSeries observation value is rederived from its EconomicLedgerSnapshot.
- Risk paths include all matched observation windows, including unchanged actions.
- Any unpaired observation makes the risk result `INCONCLUSIVE`.
- Bootstrap resamples matched observation segments; both arms receive the exact same segment indices.
- MDD and ES95 are recomputed inside each replicate.
- Empirical ES95 is the mean of the largest `max(1, ceil(0.05*M))` positive log-loss magnitudes.
- Replicate improvement divides by the fixed observed reference risk, never a random replicate denominator.
- All business arithmetic is fixed-context `Decimal`; binary float is forbidden.
- `FAIL` and `INCONCLUSIVE` never become a release PASS.
- Existing v1.1 paired-growth artifacts and estimators remain compatible.
- The final package version is `0.15.0`; no Broker, API key, deployment, or real-order capability is added.

## File Structure

- Create `src/crypto_quant/paired_risk.py`: artifact hash, builder, semantic replay, MDD/ES95 kernels, paired MBB, and estimator callables.
- Create `config/paired-risk-evaluation-snapshot-v1.schema.json`: strict external artifact contract.
- Create `tests/test_paired_risk.py`: math, builder, mutation, role, determinism, and estimator tests.
- Modify `src/crypto_quant/estimators.py`: callable registration, schema loading, and input validation.
- Modify `config/estimator-registry-v1.json` and `config/estimator-registry-v1.schema.json`: executable estimator entries and allowed input/callable IDs.
- Modify `config/estimator-golden-vectors-v1.json`: AI-vs-baseline and failure-closed fixtures/vectors.
- Modify `config/release-metrics-v1.1.json`: freeze exact MDD/ES95 bootstrap semantics.
- Modify `src/crypto_quant/release.py`, `src/crypto_quant/release_artifacts.py`, `config/release-evidence-v1.1.schema.json`, and `config/supporting-observation-bundle-v1.schema.json`: evidence input, reference, role, and nested-source validation.
- Modify `tests/test_evidence.py`, `tests/test_paired_statistics.py`, and `tests/test_release.py`: integration, trust-chain, and regression coverage.
- Modify `src/crypto_quant/build.py`, `config/evaluator-build-manifest-v1.json`, `pyproject.toml`, `src/crypto_quant/__init__.py`, and `README.md`: freeze and publish v0.15.0.
- Create `docs/adr/0015-paired-risk-efficiency-bootstrap.md` and `docs/implementation-status-v0.15.0.md`.

---

### Task 1: Build and Validate the Paired Risk Artifact

**Files:**

- Create: `config/paired-risk-evaluation-snapshot-v1.schema.json`
- Create: `src/crypto_quant/paired_risk.py`
- Create: `tests/test_paired_risk.py`

**Interfaces:**

- Produces `paired_risk_evaluation_snapshot_hash(snapshot) -> str`.
- Produces `paired_risk_evaluation_snapshot_reasons(snapshot) -> tuple[str, ...]`.
- Produces `build_paired_risk_evaluation_snapshot(...) -> dict`.
- Consumes two `PRIMARY_ENDPOINT_CONTRIBUTION` StatisticalSeriesSnapshots and all exactly referenced EconomicLedgerSnapshots.

- [ ] **Step 1: Write the failing external-schema tests**

Create `PairedRiskArtifactTests` and first define fixture helpers by deep-copying the existing valid StatisticalSeries and EconomicLedger fixture shapes. Use at least six matched windows so later path tests have gains, losses, a recovery, and two tail losses.

Add:

```python
def test_schema_accepts_exact_ai_vs_baseline_artifact(self):
    errors = list(self.validator.iter_errors(self.ai_vs_baseline))
    self.assertEqual(errors, [])

def test_schema_rejects_unknown_fields_and_wrong_role_shape(self):
    ...

def test_schema_requires_both_arm_series_and_economic_sources(self):
    ...
```

The schema must use `additionalProperties: false` at every business object layer. Freeze:

```text
comparison_role:
  AI_VS_RECIPE_BASELINE
  MINOR_CANDIDATE_VS_ACTIVE_BUNDLE

arm role/type pairs:
  RECIPE_BASELINE / RECIPE_RELEASE
  AI_CANDIDATE / MODEL_BUNDLE
  ACTIVE_BUNDLE / MODEL_BUNDLE
  MINOR_CANDIDATE / MODEL_BUNDLE
```

- [ ] **Step 2: Run and verify RED**

Run:

```bash
python -m unittest \
  tests.test_paired_risk.PairedRiskArtifactTests.test_schema_accepts_exact_ai_vs_baseline_artifact \
  tests.test_paired_risk.PairedRiskArtifactTests.test_schema_rejects_unknown_fields_and_wrong_role_shape \
  tests.test_paired_risk.PairedRiskArtifactTests.test_schema_requires_both_arm_series_and_economic_sources -v
```

Expected: import/file failures because the schema and module do not exist.

- [ ] **Step 3: Implement the strict schema and hash shell**

Add the top-level fields and `$defs` described by the design. Embed StatisticalSeries and EconomicLedger documents as JSON objects but validate each later against its authoritative schema in Registry and semantic code. Keep a self-hash placeholder of 64 lowercase hex characters.

Implement:

```python
def paired_risk_evaluation_snapshot_hash(
    snapshot: Mapping[str, Any],
) -> str:
    return artifact_self_hash(snapshot, "snapshot_hash")
```

Do not implement statistical estimators yet.

- [ ] **Step 4: Write failing builder and semantic-replay tests**

Add:

```python
def test_builder_derives_pairs_and_replays_log_return_segments(self):
    ...

def test_builder_supports_minor_candidate_vs_active_roles(self):
    ...

def test_builder_reports_changed_unchanged_and_unpaired_windows(self):
    ...

def test_nested_series_or_economic_tampering_fails_after_rehash(self):
    ...

def test_observation_value_must_equal_replayed_economic_log_growth(self):
    ...

def test_scope_policy_capital_window_and_bootstrap_must_match(self):
    ...
```

Assert exact reason codes, including:

```text
PAIRED_RISK_SELF_HASH_MISMATCH
PAIRED_RISK_REPLAY_UNVERIFIED
PAIRED_RISK_COMPARISON_ROLE_INVALID
PAIRED_RISK_ARM_ROLE_INVALID
PAIRED_RISK_SOURCE_SERIES_INVALID
PAIRED_RISK_ECONOMIC_SOURCE_INVALID
PAIRED_RISK_SOURCE_MISSING
PAIRED_RISK_SOURCE_UNEXPECTED
PAIRED_RISK_OBSERVATION_GROWTH_MISMATCH
PAIRED_RISK_ARM_SCOPE_MISMATCH:<field>
PAIRED_RISK_ARM_SETTING_MISMATCH:<field>
PAIRED_RISK_PAIR_REPLAY_MISMATCH
PAIRED_RISK_REPORT_REPLAY_MISMATCH
```

- [ ] **Step 5: Run and verify RED**

Run:

```bash
python -m unittest tests.test_paired_risk.PairedRiskArtifactTests -v
```

Expected: builder/replay assertions fail.

- [ ] **Step 6: Implement builder and semantic validation**

In `paired_risk.py`:

1. validate canonical IDs/hashes/timestamps/Decimals;
2. validate each nested StatisticalSeries with `statistical_series_reasons`;
3. validate each nested EconomicSnapshot with `economic_snapshot_reasons`;
4. enforce the comparison-role matrix;
5. enforce common arm Scope, policies, capital, design, and windows;
6. map every source observation hash to exactly one embedded economic snapshot;
7. execute `cash_flow_adjusted_economic_log_growth` and compare exactly with `observation.value`;
8. derive each arm’s interval log returns from adjacent equity points with the same cash-flow/cost rule;
9. require each segment sum to equal the observation value;
10. pair and sort by `decision_time, proposal_id`;
11. derive changed/unchanged and unpaired report;
12. self-hash and run semantic validation before returning.

Use a fixed `Decimal` context of precision 50 and `ROUND_HALF_EVEN`.

- [ ] **Step 7: Verify focused GREEN and regressions**

Run:

```bash
python -m unittest tests.test_paired_risk.PairedRiskArtifactTests -v
python -m unittest tests.test_statistics tests.test_paired_statistics tests.test_economics -v
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add \
  config/paired-risk-evaluation-snapshot-v1.schema.json \
  src/crypto_quant/paired_risk.py \
  tests/test_paired_risk.py
git commit -m "feat: add replayable paired risk artifact"
```

---

### Task 2: Implement Deterministic MDD and ES95 Paired Intervals

**Files:**

- Modify: `src/crypto_quant/paired_risk.py`
- Modify: `tests/test_paired_risk.py`

**Interfaces:**

- Produces `paired_max_drawdown_relative_improvement_lcb95(inputs)`.
- Produces `paired_es95_relative_improvement_lcb95(inputs)`.

- [ ] **Step 1: Write failing pure-math tests**

Test internal kernels through public behavior or small module-level helpers:

```python
def test_max_drawdown_uses_initial_and_prior_log_equity_high_watermarks(self):
    ...

def test_es95_is_mean_of_largest_ceil_five_percent_positive_losses(self):
    ...

def test_es95_tail_count_has_minimum_one_and_no_interpolation(self):
    ...

def test_risk_statistics_ignore_process_decimal_context(self):
    ...
```

Include hand-calculated short vectors and a 40-return vector where `tail_count == 2`.

- [ ] **Step 2: Run and verify RED**

Run:

```bash
python -m unittest \
  tests.test_paired_risk.PairedRiskEstimatorTests.test_max_drawdown_uses_initial_and_prior_log_equity_high_watermarks \
  tests.test_paired_risk.PairedRiskEstimatorTests.test_es95_is_mean_of_largest_ceil_five_percent_positive_losses \
  tests.test_paired_risk.PairedRiskEstimatorTests.test_es95_tail_count_has_minimum_one_and_no_interpolation -v
```

Expected: estimator/helper functions do not exist.

- [ ] **Step 3: Implement exact risk kernels**

Implement:

```python
def _max_drawdown(log_returns: Sequence[Decimal]) -> Decimal:
    ...

def _empirical_es95(log_returns: Sequence[Decimal]) -> Decimal:
    ...
```

For MDD, keep cumulative and peak log equity and evaluate:

```python
Decimal("1") - (cumulative - peak).exp()
```

For ES95, compute `max(0, -return)` and average the largest integer tail.

- [ ] **Step 4: Write failing paired-bootstrap tests**

Add:

```python
def test_mdd_lcb_resamples_both_arms_with_identical_segment_indices(self):
    ...

def test_es95_lcb_resamples_both_arms_with_identical_segment_indices(self):
    ...

def test_unchanged_pairs_remain_in_risk_path(self):
    ...

def test_random_replicate_denominator_is_not_used(self):
    ...

def test_no_changed_pair_is_inconclusive(self):
    ...

def test_unpaired_window_is_inconclusive(self):
    ...

def test_insufficient_blocks_is_inconclusive(self):
    ...

def test_zero_reference_mdd_and_es95_are_independently_inconclusive(self):
    ...

def test_wrong_endpoint_and_invalid_artifact_fail(self):
    ...
```

Use a small `resample_count` only in direct unit fixtures if the schema’s production minimum is satisfied; otherwise precompute the exact expected value using the required minimum count and frozen seed. Expected reason codes:

```text
PAIRED_RISK_NO_CHANGED_PAIRS
PAIRED_RISK_INCOMPLETE_PAIRING
PAIRED_RISK_INSUFFICIENT_BLOCKS
PAIRED_RISK_REFERENCE_MDD_ZERO
PAIRED_RISK_REFERENCE_ES95_ZERO
PAIRED_RISK_ENDPOINT_MISMATCH
```

- [ ] **Step 5: Run and verify RED**

Run:

```bash
python -m unittest tests.test_paired_risk.PairedRiskEstimatorTests -v
```

Expected: paired estimators fail or are missing.

- [ ] **Step 6: Implement paired MBB**

Reuse the exact `_draw_start` seed material and rejection-sampling behavior from `statistics.py`; factor it into a shared internal helper only if all existing Golden outputs remain byte-for-byte unchanged.

For each replicate:

1. draw overlapping non-circular segment blocks;
2. flatten/truncate to `N` segment indices;
3. concatenate each selected reference segment’s internal returns;
4. concatenate the candidate segments with the same indices;
5. compute MDD or ES95 for each arm;
6. calculate `(reference_b - candidate_b) / observed_reference`;
7. sort canonical Decimal results;
8. select conservative 5% nearest rank.

Do not discard or redraw any replicate because a replicate risk is zero.

- [ ] **Step 7: Verify focused GREEN and deterministic repetition**

Run:

```bash
python -m unittest tests.test_paired_risk.PairedRiskEstimatorTests -v
for i in 1 2 3; do python -m unittest tests.test_paired_risk -q; done
```

Expected: identical outputs on every run.

- [ ] **Step 8: Commit**

```bash
git add src/crypto_quant/paired_risk.py tests/test_paired_risk.py
git commit -m "feat: compute paired MDD and ES95 lower bounds"
```

---

### Task 3: Register and Freeze the Estimators

**Files:**

- Modify: `src/crypto_quant/estimators.py`
- Modify: `config/estimator-registry-v1.json`
- Modify: `config/estimator-registry-v1.schema.json`
- Modify: `config/estimator-golden-vectors-v1.json`
- Modify: `config/release-metrics-v1.1.json`
- Modify: `tests/test_paired_risk.py`
- Modify: `tests/test_estimators.py`

**Interfaces:**

- Makes both existing Catalog estimator IDs executable.
- Registry validates the dedicated artifact schema before dispatch.

- [ ] **Step 1: Write failing Registry and Catalog tests**

Add:

```python
def test_catalog_risk_metrics_resolve_to_executable_estimators(self):
    ...

def test_registry_executes_exact_mdd_and_es95_golden_values(self):
    ...

def test_registry_rejects_schema_invalid_paired_risk_input(self):
    ...

def test_registry_rejects_missing_or_unexpected_estimator_inputs(self):
    ...

def test_registry_and_catalog_algorithm_sets_remain_complete(self):
    ...
```

Assert all six existing exact overrides resolve without renaming.

- [ ] **Step 2: Run and verify RED**

Run:

```bash
python -m unittest \
  tests.test_paired_risk.PairedRiskRegistryTests \
  tests.test_estimators -v
```

Expected: both IDs return `ESTIMATOR_NOT_EXECUTABLE`.

- [ ] **Step 3: Register callables and schema validation**

In `EstimatorRegistry.load`, load `paired-risk-evaluation-snapshot-v1.schema.json`. Validate `paired_risk_evaluation_snapshot` exactly as a dedicated input before callable dispatch. Invalid external structure returns:

```text
PAIRED_RISK_SNAPSHOT_SCHEMA_INVALID
```

Register callable IDs:

```text
paired_max_drawdown_relative_improvement_lcb95
paired_es95_relative_improvement_lcb95
```

Add executable registry entries with implementation version `1.0.0`, decimal output, deterministic true, binary float false.

- [ ] **Step 4: Add Golden fixture and vectors**

Freeze one valid AI-vs-baseline Artifact as a Golden fixture. Add at least:

- computed MDD LCB;
- computed ES95 LCB;
- zero-reference MDD inconclusive;
- zero-reference ES95 inconclusive;
- schema-invalid failure.

All fixture self-hashes and vector expected values must be generated by the implementation and then checked into JSON.

- [ ] **Step 5: Freeze Metric Catalog semantics**

Update the existing algorithm entries, without changing estimator IDs:

```text
path_source
pairing_unit
paired_sampling_rule
MDD formula
ES95 tail rule
bootstrap_statistic denominator rule
zero reference behavior
unpaired behavior
```

Bump Catalog and Registry versions according to existing versioning conventions.

- [ ] **Step 6: Verify GREEN and Golden report**

Run:

```bash
python -m unittest tests.test_paired_risk tests.test_estimators tests.test_release -v
python - <<'PY'
from pathlib import Path
from crypto_quant.estimators import EstimatorRegistry
from crypto_quant.release import load_json_strict

root = Path(".")
catalog = load_json_strict(root / "config/release-metrics-v1.1.json")
registry = EstimatorRegistry.load(root / "config", catalog)
report = registry.verify_golden_vectors(
    root / "config/estimator-golden-vectors-v1.json"
)
print(report)
assert report.passed
PY
```

Expected: all pass and Golden report has no failed vectors.

- [ ] **Step 7: Commit**

```bash
git add \
  src/crypto_quant/estimators.py \
  config/estimator-registry-v1.json \
  config/estimator-registry-v1.schema.json \
  config/estimator-golden-vectors-v1.json \
  config/release-metrics-v1.1.json \
  tests/test_paired_risk.py \
  tests/test_estimators.py
git commit -m "feat: register paired risk efficiency estimators"
```

---

### Task 4: Bind Paired Risk to Release Evidence

**Files:**

- Modify: `src/crypto_quant/release.py`
- Modify: `src/crypto_quant/release_artifacts.py`
- Modify: `config/release-evidence-v1.1.schema.json`
- Modify: `config/supporting-observation-bundle-v1.schema.json`
- Modify: `tests/test_evidence.py`
- Modify: `tests/test_paired_risk.py`
- Modify: `tests/test_release.py`

**Interfaces:**

- GateEvidence may freeze `paired_risk_evaluation_snapshot`.
- Supporting observations may execute either risk estimator only from that dedicated artifact.
- Evidence validator binds comparison roles and all nested sources.

- [ ] **Step 1: Write failing frozen-input and scope tests**

Add tests for:

```python
def test_ai_risk_evidence_binds_candidate_and_recipe_baseline_subjects(self):
    ...

def test_minor_risk_evidence_binds_candidate_and_active_bundle_subjects(self):
    ...

def test_wrong_comparison_role_or_subject_fails_evidence(self):
    ...

def test_snapshot_scope_policy_capital_and_endpoint_must_match_evidence(self):
    ...

def test_frozen_input_id_hash_and_document_are_required(self):
    ...
```

AI reference must match `ExperimentManifest.baseline_recipe_release_*`.
Minor reference must match `active_model_bundle_*` from the evidence/deployment-line chain.

- [ ] **Step 2: Write failing supporting-observation trust tests**

Add:

```python
def test_risk_supporting_observation_reexecutes_estimator(self):
    ...

def test_risk_supporting_observation_requires_every_nested_source_hash(self):
    ...

def test_uploaded_scalar_cannot_replace_paired_risk_artifact(self):
    ...

def test_wrong_estimator_artifact_family_fails_closed(self):
    ...
```

`source_artifact_hashes` must include:

- PairedRiskEvaluationSnapshot hash;
- both StatisticalSeries hashes;
- every nested EconomicLedgerSnapshot hash.

- [ ] **Step 3: Run and verify RED**

Run:

```bash
python -m unittest \
  tests.test_paired_risk.PairedRiskEvidenceTests \
  tests.test_evidence \
  tests.test_release -v
```

Expected: schema rejects the new frozen input or reference validators ignore it.

- [ ] **Step 4: Extend evidence schemas**

Add `paired_risk_evaluation_snapshot` to allowed frozen inputs and estimator inputs. Use a generic strict object reference at the GateEvidence layer; the Registry and semantic validator own full artifact validation.

Conditionally require the dedicated input for the two risk estimator IDs. Do not permit `statistical_series_snapshot` as an alternative.

- [ ] **Step 5: Implement release reference validation**

In `release.py`:

- accept the artifact document in evaluation APIs;
- call `paired_risk_evaluation_snapshot_reasons`;
- bind frozen artifact ID/hash;
- compare artifact Scope, endpoint, capital, policy bindings, experiment, and candidate model to evidence;
- bind AI baseline recipe or Minor active bundle according to `comparison_role`;
- require all nested source hashes in evidence;
- reject a comparison role inconsistent with release kind/metric context.

In `release_artifacts.py`:

- load the new schema;
- validate estimator input family;
- reexecute through Registry;
- verify status/value/reason/version/execution hash;
- calculate exact nested-source closure and reject missing or extra claims according to existing source rules.

- [ ] **Step 6: Verify focused GREEN and legacy regressions**

Run:

```bash
python -m unittest \
  tests.test_paired_risk \
  tests.test_evidence \
  tests.test_release \
  tests.test_paired_statistics \
  tests.test_endpoint_reevaluation \
  tests.test_trade_replay -v
```

Expected: all pass; legacy paired growth and trade replay evidence remain unchanged.

- [ ] **Step 7: Commit**

```bash
git add \
  src/crypto_quant/release.py \
  src/crypto_quant/release_artifacts.py \
  config/release-evidence-v1.1.schema.json \
  config/supporting-observation-bundle-v1.schema.json \
  tests/test_evidence.py \
  tests/test_paired_risk.py \
  tests/test_release.py
git commit -m "feat: bind paired risk evidence to releases"
```

---

### Task 5: Freeze the Evaluator Build and Publish v0.15.0

**Files:**

- Modify: `src/crypto_quant/build.py`
- Modify: `config/evaluator-build-manifest-v1.json`
- Modify: `pyproject.toml`
- Modify: `src/crypto_quant/__init__.py`
- Modify: `README.md`
- Create: `docs/adr/0015-paired-risk-efficiency-bootstrap.md`
- Create: `docs/implementation-status-v0.15.0.md`
- Modify tests as required by build/version assertions.

**Interfaces:**

- Produces a self-consistent v0.15.0 build manifest.
- Records exact verification evidence and remaining fail-closed scope.

- [ ] **Step 1: Write failing build/version tests**

Extend existing build tests to assert:

```python
self.assertEqual(manifest["package_version"], "0.15.0")
self.assertIn(
    "paired-risk-evaluation-snapshot-v1.schema.json",
    manifest["artifact_schema_files"],
)
self.assertEqual(crypto_quant.__version__, "0.15.0")
```

Also assert the Registry/Catalog versions in the manifest equal the actual config documents.

- [ ] **Step 2: Run and verify RED**

Run the focused build/version tests.

Expected: current package/build reports v0.14.0 and the new schema is absent from the manifest.

- [ ] **Step 3: Update build inputs and versions**

- Include `paired-risk-evaluation-snapshot-v1.schema.json` in frozen build inputs.
- Bump build manifest version according to the repository convention.
- Set both `pyproject.toml` and `src/crypto_quant/__init__.py` to `0.15.0`.
- Mechanically refresh hashes with the existing build refresh command/helper; never hand-edit computed hashes.

- [ ] **Step 4: Write ADR and status report**

ADR-0015 records:

- why delta-series and uploaded scalar approaches were rejected;
- generic reference/candidate roles;
- full matched path requirement;
- segment-level paired MBB;
- empirical ES95 definition;
- fixed observed-reference denominator;
- failure-closed boundaries.

`implementation-status-v0.15.0.md` records:

- executable estimator count and remaining unavailable count;
- exact test count;
- Golden vector count/report hash;
- evaluator build hash;
- the six newly executable Gate metrics;
- synthetic-data limitation;
- next priorities.

- [ ] **Step 5: Refresh README**

Add links to:

- the v0.15 status report;
- ADR-0015;
- PairedRisk schema.

Update the capability paragraph to state that paired MDD/ES95 intervals are executable for AI-vs-baseline and Minor candidate-vs-active, while real profitability evidence and offline/Paper ingestion are still absent.

- [ ] **Step 6: Run focused then full verification**

Run:

```bash
python -m unittest tests.test_paired_risk tests.test_estimators tests.test_evidence tests.test_release -v
python -m unittest discover -s tests -v
python -m compileall -q src tests
git diff --check
```

Then run the exact Golden/build verification commands documented by the repository and capture:

- total test count;
- Golden vector count and report hash;
- evaluator build hash.

Insert those actual values into the status report, refresh the build only if a frozen input changed, and rerun all verification.

- [ ] **Step 7: Request code review and address findings**

Use `superpowers:requesting-code-review`. Review must inspect:

- formulas and Decimal determinism;
- block-pairing correctness;
- changed/unchanged and unpaired semantics;
- role/subject/evidence binding;
- nested source closure;
- schema strictness;
- backward compatibility.

Use `superpowers:receiving-code-review` before applying findings. Any correction follows TDD and receives a separate commit.

- [ ] **Step 8: Commit release metadata**

```bash
git add \
  src/crypto_quant/build.py \
  config/evaluator-build-manifest-v1.json \
  pyproject.toml \
  src/crypto_quant/__init__.py \
  README.md \
  docs/adr/0015-paired-risk-efficiency-bootstrap.md \
  docs/implementation-status-v0.15.0.md \
  tests
git commit -m "chore: publish evaluator build v0.15.0"
```

- [ ] **Step 9: Final verification, integration, and tag**

Use `superpowers:verification-before-completion`, then `superpowers:finishing-a-development-branch`.

After clean verification:

```bash
git switch main
git merge --ff-only codex/v0.15-paired-risk-efficiency
git tag -a v0.15.0 -m "v0.15.0 paired risk efficiency intervals"
git status --short
git log -8 --oneline --decorate
git tag -n1 v0.15.0
```

Expected: clean `main`, annotated `v0.15.0` on the final reviewed release commit, and no remote push attempted when no remote is configured.
