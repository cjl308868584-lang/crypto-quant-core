# Replacement v3 Economic Preregistration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish one immutable v0.74 plan that preregisters the exact replacement-v3 90-day economic population, metrics, thresholds, costs, missingness sensitivity and final-result semantics without reading an outcome or granting runtime authority.

**Architecture:** A parameterless pure builder produces the sole canonical economic plan from frozen constants and exact predecessor identities. A strict package Schema and fail-closed absolute-path loader require canonical bytes, self-hash, stable ID, policy hashes and semantic equality with the rebuilt plan. The committed JSON is the only formal artifact; v0.74 contains no final evaluator, event reader, installer, network client or production writer.

**Tech Stack:** Python 3.9-compatible standard library, `jsonschema` Draft 2020-12, repository canonical JSON/hash helpers, `unittest`, JSON Schema, Git/GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-25-replacement-v3-economic-preregistration-design.md`

## Global Constraints

- Work only in `.worktrees/v0.74-economic-preregistration` on `codex/v0.74-economic-preregistration`, based on v0.73.0 peeled commit `34bd0e9ba96c769b7301c482730a03fb975c24ce`.
- Never modify or regenerate v0.69-v0.73 formal artifacts, schemas, fixtures or release tags.
- Preserve every false/zero authority from the spec, including zero economic-outcome reads.
- Builder and loader perform no market/account/network/Broker/order/credential/production-root/event-log/economic-outcome reads and no production writes.
- Formal plan contains no observed price, fill, fee, funding, PnL, drawdown, daily return, confidence interval, bootstrap replicate or final result.
- Use exact Decimal strings. Binary JSON numbers are limited to frozen integer counts, seed, days and cycles.
- TDD each behavior: exact RED, minimal GREEN, focused verification, commit.
- Run the local full suite once only for the final code state.
- No install, bootstrap, kickstart, scheduler, Runner, observer, UI, Binance request, credential, Broker, order, funds or production-root action.

---

## File Map

**Create:**

- `src/crypto_quant/challenger_replacement_economic_plan.py` — builder, hash/ID, reason reducer and strict loader.
- `src/crypto_quant/schemas/challenger-replacement-economic-evaluation-plan-v1.schema.json` — exact-key package Schema.
- `artifacts/challenger-replacement/challenger-replacement-economic-evaluation-plan-v0.74.0.json` — sole formal artifact.
- `tests/test_challenger_replacement_economic_plan.py` — Schema/builder/loader/mutation/authority tests.
- `tests/test_challenger_replacement_v074_release.py` — release regressions.
- `docs/adr/0074-replacement-v3-economic-preregistration.md`.
- `docs/implementation-status-v0.74.0.md`.

**Modify:**

- `src/crypto_quant/build.py` — append `_V074_RELEASE_PATHS` only.
- `src/crypto_quant/__init__.py`, `pyproject.toml`, `setup.py` — version `0.74.0`.
- `config/evaluator-build-manifest-v1.json` — canonical refresh to `1.68.0` only after candidate bytes settle.
- `scripts/refresh_evaluator_build_manifest.py` — expected package `0.74.0`
  and manifest `1.68.0` for the single refresh.
- `README.md` and only current-release expectations found by `rg -l '0\.73\.0|1\.67\.0' tests`.
- This plan — check boxes only after evidence exists.

---

### Task 1: Freeze the exact package Schema

**Files:**
- Create: `src/crypto_quant/schemas/challenger-replacement-economic-evaluation-plan-v1.schema.json`
- Create: `tests/test_challenger_replacement_economic_plan.py`

**Interfaces:**
- Consumes: approved spec and Draft 2020-12.
- Produces: package Schema consumed by the Task 2 builder and loader.

- [x] **Step 1: Write Schema RED tests**

Create `EconomicPlanSchemaTests` with:

```python
ROOT = Path(__file__).resolve().parents[1]
PACKAGE_SCHEMA = ROOT / "src/crypto_quant/schemas/challenger-replacement-economic-evaluation-plan-v1.schema.json"
EXPECTED_TOP_LEVEL_KEYS = {
    "$schema", "schema_version", "plan_id", "plan_hash",
    "foundation", "population_contract", "economic_measurement",
    "missingness_policy", "statistical_design", "sample_gates",
    "economic_gates", "final_state_machine", "interim_policy", "authority",
    "status", "eligibility", "warnings",
}

def test_schema_is_exact_key_draft_202012(self):
    schema = json.loads(PACKAGE_SCHEMA.read_text())
    Draft202012Validator.check_schema(schema)
    self.assertFalse(schema["additionalProperties"])
    self.assertEqual(set(schema["required"]), EXPECTED_TOP_LEVEL_KEYS)
    self.assertNotIn("result", schema["properties"])
    self.assertNotIn("observations", schema["properties"])
```

Walk every object Schema and require `additionalProperties is False`. Require exact terminal enum `[RESEARCH_CONTINUATION_GATE_PASS, RESEARCH_CONTINUATION_GATE_DID_NOT_PASS, INCONCLUSIVE_INSUFFICIENT_EVIDENCE]`. Require exact false/zero authority consts.

- [x] **Step 2: Run the RED**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_economic_plan.EconomicPlanSchemaTests -v
```

Expected: ERROR/FAIL because the Schema does not exist.

- [x] **Step 3: Add the minimal exact Schema**

Use `apply_patch`. Set Draft 2020-12 `$schema`, a fixed `$id`, `type: object`, `additionalProperties: false`, and all expected keys. Freeze exact nested keys:

```text
foundation: v069_plan, v069_owner_attestation, v070_result_evidence_schema,
            v071_simulation_contract, v072_golden_manifest, v073_release
population_contract: start_source, start_identity_fields, cadence_seconds,
            minimum_calendar_days, start_scheduled_for_or_null,
            tail_scheduled_for_or_null, window_kind, terminal_outcomes,
            historical_backfill_allowed, window_reset_allowed,
            alternate_start_allowed, tail_pre_action_mark_required, policy_hash
economic_measurement: starting_virtual_equity_usdt, capital_limit_usdt,
            gross_exposure_limit, technical_leverage_cap,
            configured_simulation_leverage, economic_asset,
            daily_boundary_count, daily_return_count, daily_return_formula,
            decimal_arithmetic_only, binary_float_allowed, spot_mark,
            perpetual_mark, fee_treatment, funding_treatment, policy_hash
missingness_policy: observed_coverage_minimum, terminal_coverage_required,
            exposed_miss_result, optimistic_flat_miss,
            pessimistic_flat_miss, flat_miss_notional_usdt,
            protective_stop_distance, market_slippage_per_side,
            taker_fee_per_side, flat_miss_loss_rate, flat_miss_loss_usdt,
            pass_requires_both_bounds, disagreement_result, policy_hash
statistical_design: primary_null, primary_alternative, family_size,
            family_wise_alpha, method, block_length_days, sample_length,
            resample_count, seed, draw_start_method, quantile,
            confidence_level, primary_endpoint,
            minimum_economic_effect_daily, power_method, policy_hash
interim_policy: economics_withheld_before_tail, early_success_allowed,
            pnl_based_early_stop_allowed, threshold_override_allowed,
            sample_override_allowed, rerun_to_seek_better_result_allowed,
            policy_hash
authority: production_activation, runtime_install_authorized,
            replacement_start_authorized, account_requests_allowed,
            credentials_allowed, broker_requests_allowed, real_orders_allowed,
            market_requests, production_state_writes, economic_outcome_reads
```

Use `prefixItems` plus `items: false` for ordered fixed arrays. Use lowercase SHA-256/stable-ID regexes, canonical Decimal regexes and canonical millisecond UTC timestamps.

- [x] **Step 4: Run Schema tests GREEN and commit**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_economic_plan.EconomicPlanSchemaTests -v
git add src/crypto_quant/schemas/challenger-replacement-economic-evaluation-plan-v1.schema.json tests/test_challenger_replacement_economic_plan.py
git commit -m "test: freeze replacement economic plan schema"
```

---

### Task 2: Implement the parameterless builder and strict loader

**Files:**
- Create: `src/crypto_quant/challenger_replacement_economic_plan.py`
- Modify: `tests/test_challenger_replacement_economic_plan.py`

**Interfaces:**
- Consumes: Task 1 Schema and frozen v0.69-v0.73 identities.
- Produces:

```python
class ChallengerReplacementEconomicPlanError(ValueError):
    reason_code: str

def build_challenger_replacement_economic_plan() -> Dict[str, Any]: ...
def challenger_replacement_economic_plan_hash(plan: Mapping[str, Any]) -> str: ...
def challenger_replacement_economic_plan_reasons(plan: Mapping[str, Any]) -> Tuple[str, ...]: ...
def load_challenger_replacement_economic_plan(path: Path) -> Dict[str, Any]: ...
```

- [x] **Step 1: Write builder RED tests**

Require an empty builder signature. Freeze these identities:

```python
V069_PLAN_FILE_SHA = "6fae2ae0df4b8402ddc1df1b5bca611e11df41eee8d42f591d5d7b5fb24a31c3"
V069_PLAN_ID = "challenger_replacement_plan_v3_e1b6a4187cb4bb4b371ea503f83284056d4f0c6c504feb7827971869a52f666f"
V069_PLAN_HASH = "f29474a1700b0c3cf313047e2d6e85182e68104d9584ec9df7b492aa7ab00486"
V069_ATTESTATION_FILE_SHA = "b1ec38575b2e4f2b93b9f4838aa04633f382b60aef65843e4812d9b5c799b9c7"
V070_V2_SCHEMA_FILE_SHA = "755f4e049da22ab4300ce5ed68b73c0d9462581792b7b3955fff1712f6ca6dca"
V071_CONTRACT_FILE_SHA = "65a0af1cccee5ad60aeaa7b0266bb217fab680d866ea3191ca77d214a292d86f"
V072_GOLDEN_FILE_SHA = "c86993a5d56805eee3b703301f92d704cf0e7dacd06d4725a7ad9c3c16dd2b5f"
V073_COMMIT = "34bd0e9ba96c769b7301c482730a03fb975c24ce"
V073_MANIFEST_HASH = "0117d3a17bdea7e2a22004d675175083e9d863722c6c176632d29e3c4c6e62d0"
V073_TREE_HASH = "569afbae2352932a05a6c5daeb1c52049c9a3ec74034d666664579aa2bd0a97e"
V073_MANIFEST_FILE_SHA = "c41a46442993bac947773d383f722dfbaa358417ba67e87bf1e81db37c5e1c74"
```

Assert every value from Spec §§5–11: 90 daily returns, seven-day blocks, 10,000 resamples, seed `2026082574`, MERE `0.0005`, cycle gates 12/3/3, 5-of-6 blocks, 5% drawdown, 1.5x friction and 1.25-USDT flat-miss penalty. Assert start/tail are null, status is `ECONOMIC_EVALUATION_PLAN_PREREGISTERED_NOT_STARTED`, and result/observations are absent.

- [x] **Step 2: Run builder RED**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_economic_plan.EconomicPlanBuilderTests -v
```

Expected: import failure.

- [x] **Step 3: Implement the pure builder**

Reuse `business_hash`, `canonical_json`, `stable_id`, `artifact_self_hash`, `_read_owner_controlled_regular_file` and `_strict_json_bytes`. Add `policy_hash` with:

```python
def _with_policy_hash(value):
    result = copy.deepcopy(dict(value))
    result["policy_hash"] = business_hash(value)
    return result
```

Build exact ordered sample gates:

```text
CALENDAR_DAYS EQ 90
DAILY_RETURN_COUNT EQ 90
TERMINAL_COVERAGE EQ 1
OBSERVED_COVERAGE GTE 0.95
COMPLETED_CYCLES GTE 12
SPOT_COMPLETED_CYCLES GTE 3
PERPETUAL_COMPLETED_CYCLES GTE 3
NONEMPTY_FIXED_BLOCKS EQ 6
MINIMUM_MBB_BLOCKS GTE 12
ACHIEVED_POWER_AT_MERE GTE 0.80
```

Build exact ordered economic gates:

```text
MEAN_DAILY_NET_RETURN_LCB95 GT 0
TOTAL_NET_PNL_USDT GT 0
MAX_DRAWDOWN_FRACTION LT 0.05
NONNEGATIVE_FIXED_15_DAY_BLOCKS GTE 5 denominator 6
STRESS_1_5X_ADVERSE_FRICTION_TOTAL_NET_PNL_USDT GTE 0
```

Stable ID covers foundation identities, all policy hashes, ordered gate-array hashes and final-state-machine hash. `plan_hash` excludes only itself. Validate against Task 1 Schema and return a deep copy.

- [x] **Step 4: Run builder GREEN**

Run Step 2. Expected: PASS.

- [x] **Step 5: Write loader/mutation RED tests**

Cover relative path, exact canonical bytes plus one final LF, literal committed file SHA-256, duplicate key, float, whitespace, missing or multiple LF, symlink, directory, wrong mode, hardlink and oversized file. Mutate every foundation/policy/gate/authority/warning/status/eligibility leaf, recompute claimed hashes/ID, and require semantic mismatch. Freeze public reason codes:

```text
CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_SCHEMA_INVALID
CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_HASH_MISMATCH
CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_POLICY_HASH_MISMATCH
CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_ID_MISMATCH
CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_SEMANTIC_MISMATCH
CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_FILE_SHA256_MISMATCH
CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_PATH_INVALID
CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_JSON_DUPLICATE_KEY
CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_JSON_FLOAT_FORBIDDEN
CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_JSON_INVALID
CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_CANONICAL_BYTES_REQUIRED
```

- [x] **Step 6: Run loader RED**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_economic_plan.EconomicPlanLoaderTests tests.test_challenger_replacement_economic_plan.EconomicPlanMutationTests -v
```

Expected: FAIL because reason reduction/loading are absent.

- [x] **Step 7: Implement strict reasons and loader**

Use the released v3 order: exact canonical-plus-one-LF bytes and literal committed file SHA, Schema, self-hash, policy hashes, stable ID, rebuilt semantic equality. Require an absolute owner-controlled regular-file path and strict JSON. Map packaged-Schema I/O/construction failures and all other expected lower-level errors to fixed public codes; never leak raw `OSError`, Schema construction errors, `KeyError`, `TypeError`, `ValueError`, recursion or canonicalization errors.

- [x] **Step 8: Run Task 2 tests and commit**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_economic_plan -v
python3 -m compileall -q src/crypto_quant/challenger_replacement_economic_plan.py tests/test_challenger_replacement_economic_plan.py
git add src/crypto_quant/challenger_replacement_economic_plan.py tests/test_challenger_replacement_economic_plan.py
git commit -m "feat: preregister replacement economic plan"
```

---

### Task 3: Publish and replay the sole committed artifact

**Files:**
- Create: `artifacts/challenger-replacement/challenger-replacement-economic-evaluation-plan-v0.74.0.json`
- Modify: `tests/test_challenger_replacement_economic_plan.py`

**Interfaces:**
- Consumes: Task 2 builder/loader.
- Produces: exact committed bytes and frozen future authority identity.

- [x] **Step 1: Write artifact RED tests**

Require artifact bytes equal `canonical_json(builder()).encode() + b"\n"`, strict loader replay equal builder, and a literal non-placeholder file SHA-256. Snapshot/recheck exact bytes for v0.69 plan/attestation, v0.71 contract, v0.72 golden manifest and the v0.73 manifest until final refresh.

- [x] **Step 2: Run artifact RED**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_economic_plan.EconomicPlanArtifactTests -v
```

Expected: missing formal plan file.

- [x] **Step 3: Add exact canonical bytes**

Print the parameterless builder result to stdout:

```bash
PYTHONPATH=src python3 - <<'PY'
from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_replacement_economic_plan import build_challenger_replacement_economic_plan
print(canonical_json(build_challenger_replacement_economic_plan()))
PY
```

Use `apply_patch` to add that exact one-line JSON plus LF. Compute `sha256sum`, insert the literal digest in tests with `apply_patch`, and expose no production output-path/publisher API.

- [x] **Step 4: Run replay and adjacent frozen tests**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_economic_plan.EconomicPlanArtifactTests tests.test_challenger_replacement_plan_v3 tests.test_challenger_replacement_plan_v3_supersession tests.test_challenger_replacement_simulation_contract tests.test_challenger_replacement_v072_artifacts tests.test_challenger_replacement_readiness -v
```

Expected: PASS and no frozen-byte mutation.

- [x] **Step 5: Commit exact bytes**

```bash
git add artifacts/challenger-replacement/challenger-replacement-economic-evaluation-plan-v0.74.0.json tests/test_challenger_replacement_economic_plan.py
git commit -m "feat: freeze replacement economic evaluation plan"
```

---

### Task 4: Close scope and authority regressions

**Files:**
- Modify: `tests/test_challenger_replacement_economic_plan.py`
- Modify: `src/crypto_quant/build.py`

**Interfaces:**
- Consumes: completed Task 1–3 files.
- Produces: static/runtime proof that v0.74 remains plan-only and deterministic build inventory includes its formal inputs.

- [x] **Step 1: Write authority/inventory RED tests**

Parse the new module AST and reject imports containing:

```python
FORBIDDEN = {
    "requests", "urllib", "socket", "http", "websocket", "binance",
    "broker", "order", "credential", "install", "launchctl", "scheduler",
    "runner", "observer", "dashboard", "opportunity_events",
    "opportunity_projection", "simulation", "lifecycle",
}
```

Patch file/process/network boundaries while calling only the builder. Permit
only the package Schema read through `importlib.resources`; fail on
artifact/event/production paths or subprocess/network calls. Require
`EvaluatorBuild.expected_file_paths(ROOT)` to contain these nine v0.74 inputs.
The module and package Schema enter through existing globs; the remaining seven
enter through the fixed release tuple:

```text
src/crypto_quant/challenger_replacement_economic_plan.py
src/crypto_quant/schemas/challenger-replacement-economic-evaluation-plan-v1.schema.json
artifacts/challenger-replacement/challenger-replacement-economic-evaluation-plan-v0.74.0.json
tests/test_challenger_replacement_economic_plan.py
tests/test_challenger_replacement_v074_release.py
docs/superpowers/specs/2026-08-25-replacement-v3-economic-preregistration-design.md
docs/superpowers/plans/2026-08-25-replacement-v3-economic-preregistration.md
docs/adr/0074-replacement-v3-economic-preregistration.md
docs/implementation-status-v0.74.0.md
```

- [x] **Step 2: Run authority RED**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_economic_plan.EconomicPlanAuthorityTests -v
```

Expected: inventory failure because `_V074_RELEASE_PATHS` is absent. The AST and no-side-effect subtests should already pass.

- [x] **Step 3: Add the minimal build inventory**

Add `_V074_RELEASE_PATHS` after `_V073_RELEASE_PATHS` with only the artifact,
two tests, spec, plan, ADR and status paths. Append
`list(_V074_RELEASE_PATHS)` to `EvaluatorBuild.expected_file_paths`. Do not
repeat the module or package Schema already captured by existing globs, change
old tuples or add dynamic artifact/docs/test globs. Missing Task 5 files remain
an intentional inventory RED until created.

- [x] **Step 4: Commit the authority boundary**

```bash
git add src/crypto_quant/build.py tests/test_challenger_replacement_economic_plan.py
git commit -m "test: close v074 economic plan authority"
```

---

### Task 5: Independent review, release metadata and final local verification

**Files:**
- Create: `tests/test_challenger_replacement_v074_release.py`
- Create: `docs/adr/0074-replacement-v3-economic-preregistration.md`
- Create: `docs/implementation-status-v0.74.0.md`
- Modify: `README.md`, `pyproject.toml`, `setup.py`, `src/crypto_quant/__init__.py`
- Modify: current-release expectation tests found by the fixed `rg` command.
- Modify: `config/evaluator-build-manifest-v1.json`
- Modify: `scripts/refresh_evaluator_build_manifest.py`
- Modify: this plan only after evidence exists.

**Interfaces:**
- Consumes: final Task 1–4 candidate and independent findings.
- Produces: locally verified v0.74.0 candidate; no operational artifact.

- [x] **Step 1: Request one independent complete review**

Provide:

```text
base v0.73.0^{} = 34bd0e9ba96c769b7301c482730a03fb975c24ce
approved spec and this implementation plan
git diff v0.73.0^{}...HEAD
focused test evidence from Tasks 1-4
```

Require explicit Critical/Important/Minor findings. Clear Critical/Important through targeted RED/GREEN commits and targeted rereview only. Do not repeat whole-branch review without code changes.

- [ ] **Step 2: Write release-metadata RED tests**

Create `V074ReleaseTests` requiring:

```python
self.assertEqual(
    (crypto_quant.__version__, manifest["package_version"], manifest["manifest_version"]),
    ("0.74.0", "0.74.0", "1.68.0"),
)
```

Require all `_V074_RELEASE_PATHS` in expected inventory and manifest hashes. Require status text:

```text
ECONOMIC_EVALUATION_PLAN_PREREGISTERED_NOT_STARTED
production_activation=false
runtime_install_authorized=false
replacement_start_authorized=false
real_orders_allowed=false
economic_outcome_reads=0
no seven-day timer started
no 90-day timer started
```

Require README to point to v0.74 status and state that final evaluator and install/start remain future independent milestones.

- [ ] **Step 3: Run release RED**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_v074_release -v
```

Expected: missing release files and old 0.73.0/1.67.0 identity.

- [ ] **Step 4: Write ADR/status/README and update version identity once**

ADR records three alternatives, selected daily MBB design, missingness bounds
and no-outcome/no-authority boundary. Status separates completed
preregistration from all not-started runtime/economic claims. Set package
`0.74.0` in three version files and set the refresh script's exact expected
package/manifest constants to `0.74.0`/`1.68.0`. Mechanically update only
current-release expectations from 0.73.0/1.67.0 to 0.74.0/1.68.0; preserve
historical foundation constants and artifacts.

- [ ] **Step 5: Refresh the manifest once after all candidate bytes settle**

Inspect the current parameterless CLI, then run its supported command:

```bash
PYTHONPATH=src python3 scripts/refresh_evaluator_build_manifest.py
```

Do not hand-edit hash fields. Re-run the v0.74 release test and manifest consumers identified by `rg -l 'manifest_version|package_version' tests | sort`.

- [ ] **Step 6: Run final local verification exactly once**

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
python3 -m compileall -q src tests
make validate
git diff --check
git status --short
```

Run the forbidden-authority scan. Record exact full-test counts, manifest hash/tree hash/file SHA, economic plan file SHA/plan ID/plan hash, and new production/test line counts. Any unexpected failure stops release. An expected policy-level DESIGN_BASELINE/production-disabled result is acceptable only when `make validate` exits zero and the exact result is documented.

- [ ] **Step 7: Commit the final candidate and require clean status**

```bash
git add README.md pyproject.toml setup.py config src artifacts docs tests
git commit -m "feat: release replacement economic preregistration"
git status --short --branch
```

Expected: clean branch ahead of `origin/main`.

---

### Task 6: Public GitHub release workflow

**Files:** None. Git/GitHub evidence only.

**Interfaces:**
- Consumes: exact clean Task 5 candidate.
- Produces: public PR, green PR/main CI and annotated v0.74.0 identity.

- [ ] **Step 1: Reverify remote authority**

```bash
gh auth status
gh repo view cjl308868584-lang/crypto-quant-core --json nameWithOwner,visibility,viewerPermission,defaultBranchRef
git remote get-url origin
git fetch origin main --tags
git rev-parse origin/main
git status --short --branch
git ls-remote --tags origin refs/tags/v0.74.0
```

Require exact PUBLIC repository, ADMIN, default main, clean candidate and absent tag.

- [ ] **Step 2: Push only the isolated branch and create Draft PR**

```bash
git push -u origin codex/v0.74-economic-preregistration
gh pr create --draft --base main --head codex/v0.74-economic-preregistration --title "v0.74.0: preregister replacement economic evaluation" --body "Plan-only 90-day economic preregistration; no install, start, credentials, orders, funds or outcome read."
```

- [ ] **Step 3: Wait for exact PR-head CI**

Require Python 3.9, Python 3.12 and macOS arm64 all green on exact PR head. Investigate any failure through systematic debugging/TDD; never rerun blindly.

- [ ] **Step 4: Merge and wait for exact merged-main CI**

Mark ready and merge only after exact-head green. Fetch `origin/main`, record merge SHA, and require the same three jobs green on that exact SHA.

- [ ] **Step 5: Create and verify annotated tag**

```bash
git tag -a v0.74.0 <exact-merged-main-sha> -m "v0.74.0: replacement economic preregistration"
git push origin refs/tags/v0.74.0
git cat-file -t v0.74.0
git rev-parse 'v0.74.0^{}'
git rev-parse origin/main
```

Require object type `tag` and peeled tag equal origin/main. Add PR comment with head, merge SHA, PR/main CI runs, tag object and peeled identity. Do not mutate released bytes to check this operational step.

---

## Completion Check

v0.74 completes only when Tasks 1–6 have actual evidence, formal plan replays byte-for-byte, every constant is caller-invariant, v0.69-v0.73 bytes remain frozen, review is Critical/Important zero, the single final local suite and all remote jobs are green, and annotated v0.74.0 peels exactly to origin/main.

The only valid conclusion is `ECONOMIC_EVALUATION_PLAN_PREREGISTERED_NOT_STARTED`. It is not operational/economic PASS, profitability, AI advantage, Canary authority, installation or start.
