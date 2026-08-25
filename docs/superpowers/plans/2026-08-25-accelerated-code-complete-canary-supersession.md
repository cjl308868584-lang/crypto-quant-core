# Accelerated Code-Complete and Canary Supersession Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Publish one immutable v0.75 plan-only governance release that supersedes only replacement-v3 operational qualification and incident recovery while leaving the v0.74 90-day economic research contract byte-identical and inactive.

**Architecture:** A parameterless builder creates the exact accelerated-Canary plan from frozen v0.69/v0.73/v0.74 identities. A second parameterless builder creates the immutable predecessor/successor binding. Strict absolute-path loaders require owner-controlled canonical bytes, package Schema validity, self-hash, stable ID, nested policy hashes, literal committed SHA-256 and semantic equality with rebuilt values; neither module reads runtime, market, account, credentials, orders, funds, state or outcomes.

**Tech Stack:** Python 3.9-compatible standard library, repository canonical JSON/hash and owner-controlled file helpers, jsonschema Draft 2020-12, unittest, JSON Schema, Git and GitHub Actions.

**Spec:** docs/superpowers/specs/2026-08-25-accelerated-code-complete-canary-supersession-design.md

## Global Constraints

- Work only in .worktrees/v0.75-accelerated-canary-supersession-design on codex/v0.75-accelerated-canary-supersession-design, based on annotated v0.74.0 peeled commit bfe0080b0a29a74550449a1eb2ac2907a2d2ddac.
- Never modify or regenerate v0.69-v0.74 formal artifacts, Schemas, fixtures, release manifests or tags.
- Preserve v0.74 economic plan file SHA-256 24fba7579ac36c037aaef4fbf34a69b56503358edbd64addbe01f30a70c33297, plan ID challenger_replacement_economic_evaluation_plan_13ba2b74dd8c330732789a3fccd36f017847047f9fd07ea0bcf36b66f54a943e and plan hash 7c02267a0895cb3d8ceea79b6a38415140de23fb1cfcf3350c7fddff62089fa4.
- The supersession applies only to future operational qualification, ceremony and stage-block recovery. It must not change the v0.74 economic start, population, 90-day tail, missingness, metrics, thresholds or result semantics.
- Preserve every false/zero authority in the spec. Builder and loader perform no market/account/private-network/Broker/order/credential/fund/production-root/event-log/outcome reads and no production writes.
- The formal plan and record contain no runtime fact, price, balance, secret, order, fill, fee, funding, PnL, drawdown, economic result, approval or activation.
- Ceremony events are structurally excluded from DecisionOpportunity strategy/economic cycle counts.
- TDD every behavior: exact RED, minimal GREEN, focused verification and one atomic commit per task.
- Run one independent full review; after fixes run only targeted rereview. Run the local full suite once for the final unchanged code state.
- Do not install, bootstrap, kickstart, start, access Binance, read credentials, submit orders, move funds or start 72-hour/90-day clocks.

---

## File Map

**Create:**

- src/crypto_quant/challenger_replacement_accelerated_canary_plan.py — parameterless plan builder, reason reducer and strict loader.
- src/crypto_quant/challenger_replacement_accelerated_canary_supersession.py — parameterless supersession-record builder, reason reducer and strict loader.
- src/crypto_quant/schemas/challenger-replacement-accelerated-canary-plan-v1.schema.json — exact-key plan Schema.
- src/crypto_quant/schemas/challenger-replacement-accelerated-canary-supersession-v1.schema.json — exact-key record Schema.
- artifacts/challenger-replacement/challenger-replacement-accelerated-canary-plan-v0.75.0.json — formal successor plan.
- artifacts/challenger-replacement/challenger-replacement-accelerated-canary-supersession-v0.75.0.json — immutable predecessor/successor binding.
- tests/test_challenger_replacement_accelerated_canary_plan.py — plan Schema/builder/loader/mutation/authority tests.
- tests/test_challenger_replacement_accelerated_canary_supersession.py — record Schema/builder/loader/mutation tests.
- tests/test_challenger_replacement_v075_release.py — committed artifact and release-boundary regressions.
- docs/adr/0075-accelerated-code-complete-canary-supersession.md — governance decision.
- docs/implementation-status-v0.75.0.md — exact nonactivation status.

**Modify:**

- src/crypto_quant/build.py — append _V075_RELEASE_PATHS only.
- src/crypto_quant/challenger_replacement_deployment.py — advance only current evaluator-manifest compatibility to package 0.75.0/manifest 1.69.0.
- src/crypto_quant/__init__.py, pyproject.toml, setup.py — package version 0.75.0.
- scripts/refresh_evaluator_build_manifest.py — expected package 0.75.0 and manifest 1.69.0.
- config/evaluator-build-manifest-v1.json — one canonical refresh after all candidate bytes settle.
- tests/test_challenger_replacement_deployment.py — exact current-manifest compatibility seam.
- README.md — current status and next v0.76/v0.77 boundaries.
- This plan — check boxes only after evidence exists.

---

### Task 1: Freeze the accelerated plan package Schema

**Files:**
- Create: src/crypto_quant/schemas/challenger-replacement-accelerated-canary-plan-v1.schema.json
- Create: tests/test_challenger_replacement_accelerated_canary_plan.py

**Interfaces:**
- Consumes: approved exact spec and Draft 2020-12.
- Produces: strict plan Schema used by Task 2.

- [ ] **Step 1: Write exact Schema RED tests**

Create AcceleratedCanaryPlanSchemaTests:

~~~python
ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "src/crypto_quant/schemas/challenger-replacement-accelerated-canary-plan-v1.schema.json"
EXPECTED_KEYS = {
    "$schema", "schema_version", "plan_id", "plan_hash", "foundation",
    "supersession_scope", "projection_contract", "code_complete_program",
    "simulation_qualification", "operational_ceremony", "hard_stop_policy",
    "canary_ladder", "credential_boundary", "approval_ledger", "authority",
    "status", "warnings",
}

def test_schema_is_draft_202012_and_exact_key(self):
    schema = json.loads(SCHEMA.read_text())
    Draft202012Validator.check_schema(schema)
    self.assertFalse(schema["additionalProperties"])
    self.assertEqual(set(schema["required"]), EXPECTED_KEYS)
~~~

Recursively require additionalProperties is false for every object. Require ordered fixed arrays through prefixItems plus items false. Freeze:

~~~text
status = ACCELERATED_CANARY_PLAN_PREREGISTERED_NOT_ACTIVATED
minimum_continuous_seconds = 259200
cadence_seconds = 14400
ceremony_label = OPERATIONAL_CEREMONY_NOT_STRATEGY_EVIDENCE
hard_stop_classes = [
  UNRESOLVED_ECONOMIC_ORDER_UNKNOWN,
  VENUE_LOCAL_POSITION_MISMATCH,
  PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP,
  RISK_INCREASE_ATTEMPT_AFTER_STAGE_LOSS_LIMIT
]
~~~

All authority values are literal false/zero consts.

- [ ] **Step 2: Run the Schema RED**

~~~bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_accelerated_canary_plan.AcceleratedCanaryPlanSchemaTests -v
~~~

Expected: import/file-not-found failure.

- [ ] **Step 3: Add the minimal exact Schema**

Use apply_patch. Freeze these nested object shapes exactly:

~~~text
foundation:
  v069_plan, v073_release, v074_economic_plan, v074_release
supersession_scope:
  changed_rules, unchanged_rules, effective_for_future_bound_start_only,
  retroactive_rewrite_allowed, economic_contract_changed, policy_hash
projection_contract:
  fact_source, economic_projection, operational_projection,
  projection_write_authority, exports_authoritative, ceremony_economic_use,
  policy_hash
code_complete_program:
  minimum_target_days, maximum_target_days, release_sequence,
  milestone, activation_at_milestone, policy_hash
simulation_qualification:
  start_source, minimum_continuous_seconds, cadence_seconds,
  fixture_time_counts, healthy_segment_rule, flat_missed_action,
  short_disconnect_action, exposed_miss_action, terminal_outcomes,
  complete_fault_matrix_required, replay_required, policy_hash
operational_ceremony:
  label, start_state, ordered_states, amount_source, spot_instrument,
  perpetual_instrument, perpetual_position_mode, perpetual_margin_mode,
  technical_leverage_cap, product_mutual_exclusion,
  protective_stop_required_while_exposed, close_reduce_only_required,
  evidence_exclusions, retry_policy, policy_hash
hard_stop_policy:
  absolute_classes, duplicate_order_mapping, unrecorded_fill_mapping,
  block_effect, project_effect, recovery_requirements,
  recoverable_flat_conditions, policy_hash
canary_ladder:
  E0, E1, E2, product_cycle_requirements, promotion_automatic, policy_hash
credential_boundary:
  venue, repository_external, owner_only, withdrawal_allowed,
  ip_allowlist_required, least_privilege_required, secret_logging_allowed,
  policy_hash
approval_ledger:
  separately_approved_actions, inference_from_general_approval_allowed,
  binding_fields, policy_hash
authority:
  production_activation, runtime_install_authorized,
  replacement_start_authorized, credentials_allowed,
  account_requests_allowed, broker_requests_allowed, real_orders_allowed,
  fund_movement_allowed, ceremony_authorized, e0_activation_authorized,
  market_requests, private_account_requests, production_state_writes,
  economic_outcome_reads
~~~

Use the repository lowercase SHA-256, stable-ID and canonical Decimal patterns.

- [ ] **Step 4: Run Schema tests GREEN and commit**

~~~bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_accelerated_canary_plan.AcceleratedCanaryPlanSchemaTests -v
git add src/crypto_quant/schemas/challenger-replacement-accelerated-canary-plan-v1.schema.json tests/test_challenger_replacement_accelerated_canary_plan.py
git commit -m "test: freeze accelerated canary plan schema"
~~~

---

### Task 2: Implement the parameterless plan builder and loader

**Files:**
- Create: src/crypto_quant/challenger_replacement_accelerated_canary_plan.py
- Modify: tests/test_challenger_replacement_accelerated_canary_plan.py

**Interfaces:**
- Consumes: Task 1 Schema and exact v0.69/v0.73/v0.74 identities.
- Produces:

~~~python
class ChallengerReplacementAcceleratedCanaryPlanError(ValueError):
    reason_code: str

def build_challenger_replacement_accelerated_canary_plan() -> Dict[str, Any]: ...
def challenger_replacement_accelerated_canary_plan_hash(plan: Mapping[str, Any]) -> str: ...
def challenger_replacement_accelerated_canary_plan_reasons(plan: Mapping[str, Any]) -> Tuple[str, ...]: ...
def load_challenger_replacement_accelerated_canary_plan(path: Path) -> Dict[str, Any]: ...
~~~

- [ ] **Step 1: Write builder RED tests**

Require an empty builder signature and deterministic canonical bytes. Freeze:

~~~python
V069_PLAN_FILE_SHA = "6fae2ae0df4b8402ddc1df1b5bca611e11df41eee8d42f591d5d7b5fb24a31c3"
V069_PLAN_ID = "challenger_replacement_plan_v3_e1b6a4187cb4bb4b371ea503f83284056d4f0c6c504feb7827971869a52f666f"
V069_PLAN_HASH = "f29474a1700b0c3cf313047e2d6e85182e68104d9584ec9df7b492aa7ab00486"
V073_PEELED_COMMIT = "34bd0e9ba96c769b7301c482730a03fb975c24ce"
V073_MANIFEST_HASH = "0117d3a17bdea7e2a22004d675175083e9d863722c6c176632d29e3c4c6e62d0"
V074_ECONOMIC_FILE_SHA = "24fba7579ac36c037aaef4fbf34a69b56503358edbd64addbe01f30a70c33297"
V074_ECONOMIC_PLAN_ID = "challenger_replacement_economic_evaluation_plan_13ba2b74dd8c330732789a3fccd36f017847047f9fd07ea0bcf36b66f54a943e"
V074_ECONOMIC_PLAN_HASH = "7c02267a0895cb3d8ceea79b6a38415140de23fb1cfcf3350c7fddff62089fa4"
V074_PEELED_COMMIT = "bfe0080b0a29a74550449a1eb2ac2907a2d2ddac"
V074_TAG_OBJECT = "86624de8be8d5117e4b4ef6fd825a9eb711c7c38"
V074_MANIFEST_FILE_SHA = "0db974c9d143abee2e3fc078c09db8893a82754f1c4209178fb982d3d449db12"
V074_MANIFEST_HASH = "699b50fe198b25934e67433d95ea75deb3f6e0657fa8c440a61c7d6c5349e2ec"
V074_TREE_HASH = "fe58cc252f9b548e6eedb25e8249c6329cd20ee50f7a0cec48fe88abbbe4bb8e"
~~~

Assert economic projection is V074_ECONOMIC_RESEARCH_PROJECTION_V1_UNCHANGED; operational projection is ACCELERATED_OPERATIONAL_CANARY_PROJECTION_V2; PASS needs one uninterrupted 259,200-second segment; ceremony states and exclusions match the spec; E0/E1/E2 values match v0.69; only four hard stops exist; authority is false/zero.

- [ ] **Step 2: Run builder RED**

~~~bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_accelerated_canary_plan.AcceleratedCanaryPlanBuilderTests -v
~~~

Expected: production-module import failure.

- [ ] **Step 3: Implement the minimal pure builder**

Reuse business_hash, canonical_json, stable_id, artifact_self_hash, _read_owner_controlled_regular_file and _strict_json_bytes. Do not add a generic governance framework or public output-path API.

~~~python
def _with_policy_hash(value: Mapping[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["policy_hash"] = business_hash(value)
    return result

def challenger_replacement_accelerated_canary_plan_hash(
    plan: Mapping[str, Any],
) -> str:
    return artifact_self_hash(plan, "plan_hash")
~~~

Stable ID input contains exact foundation identities and every nested policy hash. Use prefix challenger_replacement_accelerated_canary_plan_. Return a deep copy.

- [ ] **Step 4: Run builder GREEN**

Run Step 2. Expected: PASS.

- [ ] **Step 5: Write strict loader and mutation RED tests**

Cover absolute-path-only, canonical one-line JSON plus one LF, literal artifact SHA, duplicate key, float, whitespace, missing/multiple LF, symlink, directory, wrong mode, hardlink and oversized file. Mutate every foundation, policy, ordered state, stage value, authority, status and warning leaf; recompute claimed hashes/ID and still require semantic mismatch.

Freeze reason codes:

~~~text
CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_SCHEMA_INVALID
CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_HASH_MISMATCH
CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_POLICY_HASH_MISMATCH
CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_ID_MISMATCH
CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_SEMANTIC_MISMATCH
CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_FILE_SHA256_MISMATCH
CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_PATH_INVALID
CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_JSON_DUPLICATE_KEY
CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_JSON_FLOAT_FORBIDDEN
CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_JSON_INVALID
CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_CANONICAL_BYTES_REQUIRED
~~~

- [ ] **Step 6: Run loader RED, implement minimal loader and run GREEN**

~~~bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_accelerated_canary_plan.AcceleratedCanaryPlanLoaderTests tests.test_challenger_replacement_accelerated_canary_plan.AcceleratedCanaryPlanMutationTests -v
~~~

Loader return is forbidden unless Schema, hashes, stable ID, exact rebuilt semantics and literal committed file SHA all pass. No bypass flag or caller-provided expected policy.

- [ ] **Step 7: Commit Task 2**

~~~bash
git add src/crypto_quant/challenger_replacement_accelerated_canary_plan.py tests/test_challenger_replacement_accelerated_canary_plan.py
git commit -m "feat: add accelerated canary plan loader"
~~~

---

### Task 3: Freeze and implement the supersession record

**Files:**
- Create: src/crypto_quant/schemas/challenger-replacement-accelerated-canary-supersession-v1.schema.json
- Create: src/crypto_quant/challenger_replacement_accelerated_canary_supersession.py
- Create: tests/test_challenger_replacement_accelerated_canary_supersession.py

**Interfaces:**
- Consumes: Task 2 parameterless plan builder.
- Produces:

~~~python
class ChallengerReplacementAcceleratedCanarySupersessionError(ValueError):
    reason_code: str

def build_challenger_replacement_accelerated_canary_supersession() -> Dict[str, Any]: ...
def challenger_replacement_accelerated_canary_supersession_hash(record: Mapping[str, Any]) -> str: ...
def challenger_replacement_accelerated_canary_supersession_reasons(record: Mapping[str, Any]) -> Tuple[str, ...]: ...
def load_challenger_replacement_accelerated_canary_supersession(path: Path) -> Dict[str, Any]: ...
~~~

- [ ] **Step 1: Write Schema and builder RED tests**

Require exact keys:

~~~python
EXPECTED_KEYS = {
    "$schema", "schema_version", "record_id", "record_hash", "reason",
    "predecessor", "successor", "changed_operational_rules",
    "preserved_economic_authority", "effectivity", "authority", "status",
    "warnings",
}
~~~

Freeze:

~~~text
reason = SUPERSEDED_FUTURE_ACTIVATION_ACCELERATED_OPERATIONAL_QUALIFICATION
status = SUPERSESSION_PREREGISTERED_NOT_ACTIVATED
effectivity = ONLY_START_RECEIPTS_CREATED_AFTER_V075_AND_BINDING_SUCCESSOR_PLAN
retroactive_effect = NONE
v074_economic_plan_disposition = IMMUTABLE_UNCHANGED_AUTHORITY
~~~

Derive successor file SHA without input:

~~~python
plan = build_challenger_replacement_accelerated_canary_plan()
plan_bytes = canonical_json(plan).encode("utf-8") + b"\n"
successor_file_sha256 = hashlib.sha256(plan_bytes).hexdigest()
~~~

- [ ] **Step 2: Run RED**

~~~bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_accelerated_canary_supersession -v
~~~

Expected: import/file-not-found failure.

- [ ] **Step 3: Add exact Schema and minimal builder/loader**

Reuse Task 2 patterns without a base class or generic storage abstraction. Stable ID prefix is challenger_replacement_accelerated_canary_supersession_; record hash excludes only record_hash. Loader requires canonical bytes, literal committed SHA, Schema, record hash, stable ID and exact rebuilt record.

- [ ] **Step 4: Add mutation and no-authority tests**

Mutate every predecessor/successor identity, changed rule, preserved-economic field, effectivity, authority, status and warning leaf. Recompute claimed record hash/ID and require semantic mismatch. Static-scan both modules for network/runtime/client imports and production-write calls.

- [ ] **Step 5: Run GREEN and commit**

~~~bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_accelerated_canary_plan tests.test_challenger_replacement_accelerated_canary_supersession -v
git add src/crypto_quant/schemas/challenger-replacement-accelerated-canary-supersession-v1.schema.json src/crypto_quant/challenger_replacement_accelerated_canary_supersession.py tests/test_challenger_replacement_accelerated_canary_supersession.py
git commit -m "feat: bind accelerated canary supersession"
~~~

---

### Task 4: Publish and replay both formal artifacts

**Files:**
- Create: artifacts/challenger-replacement/challenger-replacement-accelerated-canary-plan-v0.75.0.json
- Create: artifacts/challenger-replacement/challenger-replacement-accelerated-canary-supersession-v0.75.0.json
- Create: tests/test_challenger_replacement_v075_release.py
- Modify: Task 2/3 modules and tests only to insert literal committed file SHA values after bytes settle.

**Interfaces:**
- Consumes: Task 2/3 deterministic builders and strict loaders.
- Produces: exact immutable bytes included in the release manifest.

- [ ] **Step 1: Write committed-artifact RED tests**

~~~python
PLAN_PATH = ROOT / "artifacts/challenger-replacement/challenger-replacement-accelerated-canary-plan-v0.75.0.json"
RECORD_PATH = ROOT / "artifacts/challenger-replacement/challenger-replacement-accelerated-canary-supersession-v0.75.0.json"

self.assertEqual(
    PLAN_PATH.read_bytes(),
    canonical_json(build_challenger_replacement_accelerated_canary_plan()).encode() + b"\n",
)
self.assertEqual(
    RECORD_PATH.read_bytes(),
    canonical_json(build_challenger_replacement_accelerated_canary_supersession()).encode() + b"\n",
)
~~~

Require strict replay, literal nonzero SHA values, successor SHA binding, exact predecessor bytes and false/zero authority.

- [ ] **Step 2: Run artifact RED**

~~~bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_v075_release -v
~~~

Expected: artifacts absent.

- [ ] **Step 3: Materialize canonical bytes**

Print each builder's exact canonical JSON to a reviewed temporary path, inspect it, and use apply_patch to add exactly that one line plus one LF. Do not add a CLI, configurable output path, runtime publisher or production-root operation.

- [ ] **Step 4: Freeze literal artifact SHA values**

~~~bash
shasum -a 256 artifacts/challenger-replacement/challenger-replacement-accelerated-canary-plan-v0.75.0.json artifacts/challenger-replacement/challenger-replacement-accelerated-canary-supersession-v0.75.0.json
~~~

Use apply_patch for literal module constants and tests. Re-run Task 2-4 tests.

- [ ] **Step 5: Commit Task 4**

~~~bash
git add src/crypto_quant/challenger_replacement_accelerated_canary_plan.py src/crypto_quant/challenger_replacement_accelerated_canary_supersession.py artifacts/challenger-replacement/challenger-replacement-accelerated-canary-plan-v0.75.0.json artifacts/challenger-replacement/challenger-replacement-accelerated-canary-supersession-v0.75.0.json tests/test_challenger_replacement_accelerated_canary_plan.py tests/test_challenger_replacement_accelerated_canary_supersession.py tests/test_challenger_replacement_v075_release.py
git commit -m "test: freeze accelerated canary artifacts"
~~~

---

### Task 5: Close cross-contract and authority regressions

**Files:**
- Modify: tests/test_challenger_replacement_v075_release.py
- Modify: tests/test_challenger_replacement_accelerated_canary_plan.py
- Modify: src/crypto_quant/challenger_replacement_accelerated_canary_plan.py only if a minimal pure helper is required.

**Interfaces:**
- Consumes: Task 4 committed artifacts.
- Produces: falsifiable proof that operational acceleration cannot mutate research or grant authority.

- [ ] **Step 1: Write cross-contract RED tests**

Load exact v0.69, v0.74 and v0.75 artifacts and require:

~~~python
self.assertEqual(
    v075["foundation"]["v074_economic_plan"]["file_sha256"],
    sha256(V074.read_bytes()).hexdigest(),
)
self.assertEqual(
    v075["projection_contract"]["economic_projection"],
    "V074_ECONOMIC_RESEARCH_PROJECTION_V1_UNCHANGED",
)
self.assertFalse(v075["supersession_scope"]["economic_contract_changed"])
self.assertFalse(v075["supersession_scope"]["retroactive_rewrite_allowed"])
~~~

Add pure fixture classification assertions: ceremony label is excluded from strategy/economic counts; a failed old block remains in history when a later block is permitted; incident unlock cannot change economic start/window; disconnected segments cannot sum to 72 hours; exact hard-stop set has four values; E0/E1/E2 risk values equal v0.69.

- [ ] **Step 2: Run RED and add only the minimal pure policy helper if necessary**

~~~bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_accelerated_canary_plan.AcceleratedCanaryPlanCrossContractTests tests.test_challenger_replacement_v075_release -v
~~~

Prefer immutable-plan assertions. Do not implement the v0.76 runtime evaluator, state machine, scheduler, projection writer or network client early.

- [ ] **Step 3: Add forbidden-capability static gate**

Require the two new modules contain no imports/calls for sqlite3, requests, urllib, http.client, socket, subprocess, launchctl, keyring, Binance SDKs, filesystem writes or environment-secret reads. Path is allowed only for strict loader input and package Schema access.

- [ ] **Step 4: Run adjacent tests GREEN and commit**

~~~bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_plan_v3 \
  tests.test_challenger_replacement_v069_release \
  tests.test_challenger_replacement_readiness \
  tests.test_challenger_replacement_readiness_observer \
  tests.test_challenger_replacement_economic_plan \
  tests.test_challenger_replacement_v074_release \
  tests.test_challenger_replacement_accelerated_canary_plan \
  tests.test_challenger_replacement_accelerated_canary_supersession \
  tests.test_challenger_replacement_v075_release -v
git add tests/test_challenger_replacement_accelerated_canary_plan.py tests/test_challenger_replacement_v075_release.py src/crypto_quant/challenger_replacement_accelerated_canary_plan.py
git commit -m "test: enforce accelerated canary boundaries"
~~~

---

### Task 6: Release documentation, version and build manifest

**Files:**
- Create: docs/adr/0075-accelerated-code-complete-canary-supersession.md
- Create: docs/implementation-status-v0.75.0.md
- Modify: README.md
- Modify: src/crypto_quant/build.py
- Modify: src/crypto_quant/challenger_replacement_deployment.py
- Modify: src/crypto_quant/__init__.py
- Modify: pyproject.toml
- Modify: setup.py
- Modify: scripts/refresh_evaluator_build_manifest.py
- Modify: config/evaluator-build-manifest-v1.json
- Modify: tests/test_challenger_replacement_deployment.py
- Modify: tests/test_challenger_replacement_v075_release.py

**Interfaces:**
- Consumes: final Task 1-5 bytes.
- Produces: package 0.75.0, manifest 1.69.0 and exact nonactivation release status.

- [ ] **Step 1: Write release metadata RED tests**

~~~python
self.assertEqual(
    (crypto_quant.__version__, manifest["package_version"], manifest["manifest_version"]),
    ("0.75.0", "0.75.0", "1.69.0"),
)
~~~

Require _V075_RELEASE_PATHS includes both artifacts, two modules, two Schemas, three tests, approved spec, this plan, ADR and status. Status must include:

~~~text
ACCELERATED_CANARY_PLAN_PREREGISTERED_NOT_ACTIVATED
CODE_COMPLETE_NOT_ACTIVATED_NOT_YET_REACHED
production_activation=false
runtime_install_authorized=false
credentials_allowed=false
real_orders_allowed=false
fund_movement_allowed=false
no 72-hour timer started
no 90-day timer started
v0.74 economic contract remains immutable
~~~

- [ ] **Step 2: Run release RED**

~~~bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_v075_release tests.test_challenger_replacement_deployment -v
~~~

Expected: current version/manifest/status mismatch.

- [ ] **Step 3: Add ADR, status and README update**

ADR records dual projections and rejected alternatives. Status lists exact plan/record IDs, hashes and file SHAs plus no-authority facts. README says v0.75 is plan-only, v0.76/v0.77 remain future and earliest E0 is not authorization.

- [ ] **Step 4: Advance only current release metadata**

Add _V075_RELEASE_PATHS; change current package versions to 0.75.0; change refresh constants to 0.75.0/1.69.0; update only exact deployment compatibility and tests. Do not rewrite historical identities.

- [ ] **Step 5: Refresh manifest exactly once**

~~~bash
PYTHONPATH=src python3 scripts/refresh_evaluator_build_manifest.py
~~~

Do not hand-edit manifest hashes. Re-run release/deployment/manifest consumers found by rg -l 'manifest_version|package_version' tests.

- [ ] **Step 6: Run focused GREEN and commit**

~~~bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_v075_release tests.test_challenger_replacement_deployment -v
git add README.md pyproject.toml setup.py config src scripts docs tests
git commit -m "feat: prepare v0.75 accelerated canary plan"
~~~

---

### Task 7: Independent review and final local verification

**Files:**
- Modify only files required by verified review findings.

**Interfaces:**
- Consumes: Task 6 candidate.
- Produces: clean reviewed release candidate and one final full-suite result.

- [ ] **Step 1: Request one complete independent review**

Give reviewer exact base bfe0080b0a29a74550449a1eb2ac2907a2d2ddac, candidate HEAD, approved spec and this plan. Require Critical/Important/Minor findings and checks for economic immutability, uninterrupted 72 hours, ceremony exclusion, four hard stops, stage-block recovery, no side effects, strict loader and no generic platform expansion.

- [ ] **Step 2: Resolve Critical/Important findings through targeted TDD**

For each valid finding: exact RED, minimal fix, focused GREEN, atomic commit and targeted rereview. Do not repeat whole review without code changes. Critical/Important must be zero.

- [ ] **Step 3: Run focused and adjacent verification**

Run Task 5 Step 4 plus build/deployment/manifest tests.

- [ ] **Step 4: Run final local suite exactly once**

~~~bash
PYTHONPATH=src python3 -m unittest discover -s tests
python3 -m compileall -q src tests
make validate
git diff --check
git status --short
~~~

Record exact pass/skip/failure count, manifest hash/tree/file SHA, plan/record SHA/ID/hash and source/test line counts. Unexpected failure stops release. DESIGN_BASELINE/production-disabled policy output is acceptable only if make validate exits zero.

- [ ] **Step 5: Require clean candidate status**

~~~bash
git status --short --branch
~~~

Do not create a commit when no bytes changed.

---

### Task 8: Public GitHub release workflow

**Files:** None; Git/GitHub evidence only.

**Interfaces:**
- Consumes: clean Task 7 candidate.
- Produces: public PR, green PR/main CI and annotated v0.75.0 identity.

- [ ] **Step 1: Reverify remote authority**

~~~bash
gh auth status
gh repo view cjl308868584-lang/crypto-quant-core --json nameWithOwner,visibility,viewerPermission,defaultBranchRef
git remote get-url origin
git fetch origin main --tags
git rev-parse origin/main
git status --short --branch
git ls-remote --tags origin refs/tags/v0.75.0
~~~

Require PUBLIC repository, ADMIN, default main, candidate based on current origin/main, clean status and absent tag.

- [ ] **Step 2: Push branch and create Draft PR**

~~~bash
git push -u origin codex/v0.75-accelerated-canary-supersession-design
gh pr create --draft --base main --head codex/v0.75-accelerated-canary-supersession-design --title "v0.75.0: preregister accelerated Canary qualification" --body "Plan-only operational supersession; v0.74 economic research unchanged; no install, start, credential, account request, order or funds."
~~~

- [ ] **Step 3: Wait for exact PR-head CI**

Require Python 3.9, Python 3.12 and macOS arm64 success on exact PR head. Debug failures; never rerun blindly.

- [ ] **Step 4: Merge and wait for exact merged-main CI**

Mark ready and merge normally only after exact-head green. Fetch origin/main, record merge SHA and require all three jobs green on that SHA.

- [ ] **Step 5: Create and verify annotated tag**

~~~bash
git tag -a v0.75.0 <exact-merged-main-sha> -m "v0.75.0: accelerated Canary qualification preregistration"
git push origin refs/tags/v0.75.0
git cat-file -t v0.75.0
git rev-parse 'v0.75.0^{}'
git rev-parse origin/main
~~~

Require object type tag and peeled tag equals origin/main. Record release identities in the local durable ledger without mutating released bytes.

---

## Completion Check

v0.75 completes only when Tasks 1-8 have evidence, both artifacts replay byte-for-byte, every policy is caller-invariant, v0.69-v0.74 artifacts remain frozen, review Critical/Important is zero, one final local suite and all remote jobs are green, and annotated v0.75.0 peels exactly to origin/main.

The only valid conclusion is ACCELERATED_CANARY_PLAN_PREREGISTERED_NOT_ACTIVATED. It is not CODE_COMPLETE_NOT_ACTIVATED, a 72-hour PASS, ceremony/E0 authority, profitability, AI advantage, installation, start or live-trading qualification.
