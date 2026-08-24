# DecisionOpportunity Event Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a v3-bound append-only DecisionOpportunity runtime that records every due four-hour opportunity as immutable `OBSERVED` or `MISSED`, permits later natural recovery after misses, and exposes only read-only non-economic health.

**Architecture:** Keep the audited v0.66 event store as the sole durable authority and add a separate v3 semantic module rather than branching the v2 runtime. A strict fixture-only result-evidence document proves the v0.70 state contract without pretending to simulate Binance; a pure catch-up function derives expired opportunities from explicit time boundaries and appends only `MISSED` facts.

**Tech Stack:** Python 3.9+ stdlib, integer-ratio coverage arithmetic, existing canonical/event capability APIs, `jsonschema`, `unittest`, GitHub Actions Python 3.9/3.12 and macOS arm64.

**Spec:** `docs/superpowers/specs/2026-08-24-decision-opportunity-event-runtime-design.md`

## Global Constraints

- Release foundation is annotated `v0.69.0`, peeled commit `f98f8c49f5c6a2bb28d04ee01d3b1b0ba0348550`.
- Exact v3 plan path is `artifacts/challenger-replacement/challenger-replacement-plan-v0.69.0.json`; file SHA-256 is `6fae2ae0df4b8402ddc1df1b5bca611e11df41eee8d42f591d5d7b5fb24a31c3`; plan hash is `f29474a1700b0c3cf313047e2d6e85182e68104d9584ec9df7b492aa7ab00486`.
- Canonical storage authority remains `state/challenger-replacement-events-v1`; no second database, export or mutable projection is authoritative.
- v3 terminal outcomes are exactly `OPPORTUNITY_OBSERVED` and `OPPORTUNITY_MISSED`; a miss is never backfilled or replaced but does not terminate later opportunities.
- Catch-up receives explicit fixture/orchestration `start_scheduled_for` and `detected_at`; v0.70 does not claim they came from a trusted production clock/detector and must not derive authority from wall clock, install time, tag time or caller-supplied outcome/price/PnL.
- v0.70 has no natural runner and no production start boundary. Its result-evidence builder is fixture-only and must report network/Broker/order/credential/production-write counts as zero.
- Keep `challenger_replacement_events.py` storage semantics unchanged unless a new focused red test proves a necessary generic fix.
- Keep v2 `challenger_replacement_runtime.py` and v2 replay behavior unchanged; v3 lives in focused modules.
- No new scheduler, deployment, LaunchAgent, install, start receipt, production root, network, Binance SDK, credential, account, Broker, order, fill, fee, position, PnL, generic UI or production fault seam. The only allowed existing-deployment change is the exact two-literal current-manifest compatibility correction (`1.64.0`/`0.70.0`) if the final full suite proves the committed candidate loader otherwise rejects the complete v0.70 manifest; deployment artifact, path, authority and behavior remain unchanged.
- `production_activation=false`, `runtime_install_authorized=false`, `replacement_start_authorized=false`, `credentials_allowed=false`, `account_requests_allowed=false`, `broker_requests_allowed=false`, `real_orders_allowed=false` remain true as negative authority gates.
- New v3 production module target is at most 700 physical lines. Stop and simplify before commit if the gate is exceeded.
- Every task follows RED -> minimal GREEN -> refactor. Run the local full suite only once at the milestone final code state.

---

## File Map

**Create production files**

- `src/crypto_quant/challenger_replacement_opportunity_evidence.py`: strict fixture-only result-evidence builder/bytes loader; no path or runtime I/O.
- `src/crypto_quant/challenger_replacement_opportunities.py`: v3 identity, opportunity time grid, projection, optimistic append and catch-up orchestration.
- `src/crypto_quant/schemas/challenger-replacement-opportunity-result-evidence-v1.schema.json`: packaged strict result-evidence schema.
- `config/challenger-replacement-opportunity-result-evidence-v1.schema.json`: byte-identical repository schema mirror.

**Create test files**

- `tests/challenger_replacement_v3_fixtures.py`: exact committed v3 plan/build fixture, safe temporary event-root and deterministic opportunity helpers.
- `tests/test_challenger_replacement_opportunity_evidence.py`: schema, canonical bytes, zero-authority and identity tests.
- `tests/test_challenger_replacement_opportunities.py`: schedule, projection, state machine, no-backfill, concurrency and recovery tests.
- `tests/test_challenger_replacement_v070_release.py`: scope, static boundary, predecessor hashes, version and manifest gates.

**Modify only for release identity**

- `src/crypto_quant/build.py`: inventory the new modules, schemas, tests and release docs.
- `pyproject.toml`, `setup.py`, `src/crypto_quant/__init__.py`: `0.70.0` package identity.
- `scripts/refresh_evaluator_build_manifest.py`: expected package `0.70.0`, manifest `1.64.0`.
- `config/evaluator-build-manifest-v1.json`: generated exact file inventory/hashes.
- `tests/test_estimators.py`: expected package/manifest identities.
- `README.md`: concise v0.70 checkpoint and unchanged nonactivation boundary.
- `docs/adr/0070-decision-opportunity-event-runtime.md`: architectural decision and nonclaims.
- `docs/implementation-status-v0.70.0.md`: exact implementation/test/release status.
- `src/crypto_quant/challenger_replacement_deployment.py`: only the two current-manifest compatibility literals described above; no deployment semantics.

**Must not modify**

- `src/crypto_quant/challenger_replacement_events.py`
- `src/crypto_quant/challenger_replacement_runtime.py`
- v0.64/v0.67/v0.68/v0.69 committed artifacts and schemas
- install/observer/start/CLI modules and every deployment behavior other than the exact two compatibility literals above

---

### Task 1: Freeze v3 fixtures and fixture-only result evidence

**Files:**
- Create: `tests/challenger_replacement_v3_fixtures.py`
- Create: `tests/test_challenger_replacement_opportunity_evidence.py`
- Create: `config/challenger-replacement-opportunity-result-evidence-v1.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-opportunity-result-evidence-v1.schema.json`
- Create: `src/crypto_quant/challenger_replacement_opportunity_evidence.py`

**Interfaces:**
- Consumes: exact plan returned by `load_challenger_replacement_plan_v3(absolute_path)` and an explicit v0.70 fixture build identity mapping.
- Produces: `ChallengerReplacementOpportunityEvidenceError`, `build_challenger_replacement_fixture_result_evidence(*, opportunity_id, scheduled_for, observed_at, source_bundle_sha256, decision_sha256) -> dict`, and `load_challenger_replacement_fixture_result_evidence_bytes(data: bytes, *, opportunity_id, scheduled_for, observed_at, source_bundle_sha256, decision_sha256) -> dict`.

- [ ] **Step 1: Write exact plan/build fixtures and failing schema tests**

Create fixture helpers with these signatures:

```python
def fixture_v3_plan():
    return load_challenger_replacement_plan_v3(
        ROOT / "artifacts/challenger-replacement/"
        "challenger-replacement-plan-v0.69.0.json"
    )

def fixture_v070_build_identity():
    return {
        "release_tag": "v0.70.0-fixture",
        "peeled_commit": "7" * 40,
        "package_version": "0.70.0",
        "manifest_version": "1.64.0",
        "build_input_tree_hash": "1" * 64,
        "manifest_hash": "2" * 64,
        "manifest_file_sha256": "3" * 64,
    }
```

Add tests proving config/package schema bytes are identical, Draft 2020-12 valid, `additionalProperties` is false, and the public builder/loader names do not yet import.

- [ ] **Step 2: Run RED**

Run:

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_opportunity_evidence
```

Expected: import or missing-schema failure for the new opportunity evidence API.

- [ ] **Step 3: Add strict schema and minimal canonical builder/loader**

The schema requires exact keys and constants:

```json
{
  "$schema": "./challenger-replacement-opportunity-result-evidence-v1.schema.json",
  "schema_version": "1.0.0",
  "mode": "FIXTURE_ONLY_NO_BROKER_NO_ORDER",
  "opportunity_id": "ETHUSDT@2026-08-24T00:00:00.000Z",
  "scheduled_for": "2026-08-24T00:00:00.000Z",
  "observed_at": "2026-08-24T00:05:00.000Z",
  "source_bundle_sha256": "<64 lowerhex>",
  "decision_sha256": "<64 lowerhex>",
  "authority": {
    "network_requests": 0,
    "broker_requests": 0,
    "orders": 0,
    "credentials_used": false,
    "production_state_writes": 0
  }
}
```

Use existing `_strict_json_bytes`, `canonical_json`, `Draft202012Validator` and `business_hash` patterns. Reject duplicate keys, JSON float/NaN, noncanonical bytes, wrong opportunity/schedule/observed/source/decision binding, unknown fields and any nonzero/true authority value with fixed reason codes. This loader validates fixture binding only; it must not claim market or strategy semantics.

- [ ] **Step 4: Add semantic failure tests**

Add table tests for every exact-key deletion/addition, wrong mode/version, malformed hash, opportunity mismatch, observation outside the supplied window, source/decision mismatch, nonzero authority count and `credentials_used=true`. Rebuild canonical bytes and assert byte equality on successful replay.

- [ ] **Step 5: Run GREEN and static boundary scan**

Run:

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_opportunity_evidence
rg -n "requests|urllib|httpx|aiohttp|websocket|binance|broker|order|sqlite3|Path\(" \
  src/crypto_quant/challenger_replacement_opportunity_evidence.py
```

Expected: tests pass; scan finds only literal schema/authority vocabulary, no imported runtime/network/path facility.

- [ ] **Step 6: Commit**

```bash
git add tests/challenger_replacement_v3_fixtures.py \
  tests/test_challenger_replacement_opportunity_evidence.py \
  config/challenger-replacement-opportunity-result-evidence-v1.schema.json \
  src/crypto_quant/schemas/challenger-replacement-opportunity-result-evidence-v1.schema.json \
  src/crypto_quant/challenger_replacement_opportunity_evidence.py
git commit -m "feat: freeze opportunity result evidence contract"
```

---

### Task 2: Implement deterministic opportunity identity and schedule projection

**Files:**
- Create: `tests/test_challenger_replacement_opportunities.py`
- Create: `src/crypto_quant/challenger_replacement_opportunities.py`

**Interfaces:**
- Consumes: `utc_datetime`, exact v3 plan and explicit UTC boundaries.
- Produces: `ChallengerReplacementOpportunityError`, `opportunity_id_for(scheduled_for: str) -> str`, `derive_due_opportunities(*, start_scheduled_for: str, detected_at: str, terminal_scheduled_for: Tuple[str, ...]) -> Tuple[dict, ...]`, and `opportunity_health(*, projection: dict, start_scheduled_for: Optional[str], detected_at: str) -> dict` returning exact integer numerator/denominator coverage.

- [ ] **Step 1: Write schedule RED tests**

Cover UTC grid values `00/04/08/12/16/20`, exact ID format, capture offsets `+120/+600`, closed OBSERVED endpoints, MISSED only when `detected_at > capture_close`, month/year rollover, and explicit failures for off-grid, non-UTC, missing milliseconds, bool/int, `detected_at < start`, duplicate or out-of-order terminal schedule.

The core expected vector is:

```python
self.assertEqual(
    derive_due_opportunities(
        start_scheduled_for="2026-08-24T00:00:00.000Z",
        detected_at="2026-08-24T12:11:00.000Z",
        terminal_scheduled_for=("2026-08-24T00:00:00.000Z",),
    ),
    (
        {"opportunity_id": "ETHUSDT@2026-08-24T04:00:00.000Z", ...},
        {"opportunity_id": "ETHUSDT@2026-08-24T08:00:00.000Z", ...},
        {"opportunity_id": "ETHUSDT@2026-08-24T12:00:00.000Z", ...},
    ),
)
```

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_opportunities.OpportunityScheduleTests
```

Expected: module/API import failure.

- [ ] **Step 3: Implement pure schedule helpers**

Use timezone-aware `datetime`, integer seconds and the v3 plan offsets. Do not call `datetime.now`, `time.time` or `_utc_now`. Return all due opportunities including the currently open one with an explicit derived status `EXPIRED`, `ELIGIBLE_WINDOW`, or `NOT_OPEN`; the caller, not the helper, decides whether to append.

- [ ] **Step 4: Add exact-ratio health RED then GREEN**

Test exact `(numerator, denominator, threshold)` values `(0,0,None)`, `(1,1,True)`, `(19,20,True)`, `(18,20,False)`, and large counts. Implement the 95% gate as `observed * 100 >= due * 95`; return no Decimal/float display value. Patch the global Decimal context to several precisions and prove output unchanged. Require statuses:

```text
NOT_STARTED_NO_START_BOUNDARY
PRE_TAIL_ELIGIBILITY_ONLY
BLOCKED_LIFECYCLE_EVIDENCE_NOT_IMPLEMENTED
```

Any nonzero due count remains blocked from operational qualification in v0.70.

- [ ] **Step 5: Run focused GREEN and static clock scan**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_opportunities.OpportunityScheduleTests \
  tests.test_challenger_replacement_opportunities.OpportunityHealthTests
rg -n "datetime\.now|time\.time|_utc_now|float\(" \
  src/crypto_quant/challenger_replacement_opportunities.py
```

Expected: tests pass and scan is empty.

- [ ] **Step 6: Commit**

```bash
git add src/crypto_quant/challenger_replacement_opportunities.py \
  tests/test_challenger_replacement_opportunities.py
git commit -m "feat: derive decision opportunity schedule"
```

---

### Task 3: Add strict v3 event projection and optimistic append

**Files:**
- Modify: `src/crypto_quant/challenger_replacement_opportunities.py`
- Modify: `tests/test_challenger_replacement_opportunities.py`

**Interfaces:**
- Consumes: `ChallengerReplacementEventRoot`, `build_challenger_replacement_event`, `publish_challenger_replacement_event`, `replay_challenger_replacement_events`, a mapping whose canonical v3 semantics exactly match the frozen v0.69 plan, and v0.70 build identity.
- Produces: `ChallengerReplacementOpportunityState(event_root, plan, build_identity)`, `.replay() -> dict`, and `.append(event_type, opportunity_id, worker_id, recorded_at, payload, expected_last_event_hash) -> ChallengerReplacementEventPublication`.

- [ ] **Step 1: Write genesis state-machine RED**

Construct nonempty canonical JSON source/decision fixture bytes and a result-evidence document that binds their exact hashes and observation time, then assert:

```python
state.append(event_type="INPUT_PREPARED", ...)
state.append(event_type="RESULT_PREPARED", ...)
state.append(event_type="OPPORTUNITY_OBSERVED", ...)
projection = state.replay()
self.assertEqual(projection["observed_opportunity_count"], 1)
self.assertIsNone(projection["active_opportunity_id"])
```

Also test direct `OPPORTUNITY_MISSED`, INPUT→MISSED and RESULT→MISSED exact payloads.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_opportunities.OpportunityStateTests
```

Expected: missing state class/append behavior.

- [ ] **Step 3: Implement minimal projection/apply helper**

Use one private `_apply_event(projection, event, plan, build_identity)` for replay and pre-publish validation. First require `challenger_replacement_plan_v3_reasons(plan) == ()` and exact frozen v0.69 plan ID/hash constants; do not claim path provenance. Validate envelope `slot_id == opportunity_id`, plan/build hashes, payload exact keys, nonempty canonical JSON source/decision fixture bytes, evidence byte hashes, fixture evidence binding, capture window, stage parent hashes and monotonic times. Do not call v2 source/decision loaders or claim v3 market/strategy semantic validation. Keep private previous-observed source/decision bytes/hashes out of public projection.

`append` must fresh replay, compare `expected_last_event_hash`, apply to a copy, publish once and return the publisher outcome. It may confirm only an immediate exact retry whose last event has the supplied parent token and byte-identical frozen candidate, returning `ALREADY_COMMITTED`; any older token or changed candidate raises `CHALLENGER_REPLACEMENT_OPPORTUNITY_SEQUENCE_CONFLICT`. Do not rebase internally.

- [ ] **Step 4: Add invariant RED tests**

Table-test wrong plan/build, v2 terminal types, `slot_id != opportunity_id`, skip/repeat stage, two active opportunities, event after terminal, different terminal outcome/reason, malformed capture/result evidence, out-of-order schedule, duplicate schedule and OBSERVED outside capture window.

- [ ] **Step 5: Implement terminal/parent invariants and reason accounting**

Only OBSERVED updates previous observed source/decision. MISSED records exact reason/detection delay and leaves parent unchanged. The next INPUT must use the next due opportunity while the decision parent can cross one or more MISSED outcomes.

- [ ] **Step 6: Run focused GREEN**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_opportunities.OpportunityStateTests \
  tests.test_challenger_replacement_opportunities.OpportunityInvariantTests
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/crypto_quant/challenger_replacement_opportunities.py \
  tests/test_challenger_replacement_opportunities.py
git commit -m "feat: project immutable opportunity outcomes"
```

---

### Task 4: Implement no-backfill catch-up and fixture-only observed flow

**Files:**
- Modify: `src/crypto_quant/challenger_replacement_opportunities.py`
- Modify: `tests/test_challenger_replacement_opportunities.py`

**Interfaces:**
- Consumes: Task 1 evidence API and Task 3 state API.
- Produces: `catch_up_missed_opportunities(*, state, start_scheduled_for, detected_at, worker_id, reason_code) -> dict`. Fixture OBSERVED events are assembled explicitly in tests through the state API; v0.70 exposes no natural or production observed runner.

- [ ] **Step 1: Write direct catch-up RED**

Starting at `00:00` and detecting at `12:11`, prove four expired opportunities are appended as MISSED in order, each binds the supplied fixture/orchestration `detected_at` without claiming trusted production clock provenance, no source/decision/result bytes exist, and explicitly assembled fixture events for a later `16:05` opportunity can become OBSERVED without changing prior outcomes.

- [ ] **Step 2: Prove zero side effects before implementation**

Patch the lowest existing source builder, decision builder and any fixture evidence builder, plus `socket.socket`, to raise if called. Patch the event publisher only to count canonical event writes. Assert catch-up calls only the publisher for MISSED events and never touches market/network/decision/simulation/Broker/order/export boundaries.

Run:

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_opportunities.OpportunityCatchUpTests
```

Expected: missing catch-up API.

- [ ] **Step 3: Implement ordered catch-up**

Fresh replay before each append. For every derived `EXPIRED` opportunity with no terminal event, append only `OPPORTUNITY_MISSED` using a parent-hash token. On sequence conflict return the fixed conflict for the caller to replay; do not silently continue. Stop before an `ELIGIBLE_WINDOW` opportunity and return it as read-only eligibility. Stop before `NOT_OPEN` too, but return no eligible opportunity and append no event.

- [ ] **Step 4: Write partial-stage expiry RED and implement**

Create INPUT and RESULT crash boundaries, advance explicit `detected_at` past capture close, and prove catch-up appends MISSED bound to the exact current stage/hash. Ensure no decision rebuild at RESULT, no source rebuild at INPUT and exact retry adds zero events.

- [ ] **Step 5: Write fixture OBSERVED recovery RED and implement only state semantics**

Use test helpers, not a production runner API, to append already-canonical fixture source bytes, decision bytes and Task 1 result-evidence bytes through `state.append`. Prove INPUT, RESULT and OBSERVED replay across each crash boundary and never recompute committed bytes. Production code only applies/replays the frozen state semantics.

- [ ] **Step 6: Add caller injection failures**

Assert catch-up has no parameters named `outcome`, `price`, `pnl`, `fault_injector`, `path`, `broker` or `credentials`, and that the module exports no natural/production observed runner. Reject non-string worker/detected/reason, unknown reason code and absent explicit start boundary.

- [ ] **Step 7: Run GREEN**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_opportunities.OpportunityCatchUpTests \
  tests.test_challenger_replacement_opportunities.OpportunityFixtureRuntimeTests
```

Expected: all tests pass; no side-effect mock is called.

- [ ] **Step 8: Commit**

```bash
git add src/crypto_quant/challenger_replacement_opportunities.py \
  tests/test_challenger_replacement_opportunities.py
git commit -m "feat: recover missed decision opportunities"
```

---

### Task 5: Prove v3 semantic crash, concurrency, isolation and YAGNI boundaries

**Files:**
- Modify: `tests/test_challenger_replacement_opportunities.py`
- Modify only if a new generic RED proves necessary: `src/crypto_quant/challenger_replacement_events.py`

**Interfaces:**
- Consumes: all v0.70 public APIs.
- Produces: no new public production API.

- [ ] **Step 1: Add v3 semantic fresh-process crash table**

Using subprocess/multiprocessing test harnesses only, inject crashes after INPUT, after RESULT and after terminal through existing private wrappers. Start a new interpreter that only replays/retries and assert exact terminal outcome and no recomputation after durable semantic boundaries. Do not recreate the already frozen v0.66 staging/fsync matrix in new tests; the existing event regressions remain an adjacent gate.

- [ ] **Step 2: Run crash RED or verification**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_opportunities.OpportunityCrashTests
```

Expected: new tests either pass using the frozen event store or fail at one precise v3 orchestration boundary. Do not edit the store merely to manufacture a change.

- [ ] **Step 3: Fix only the proven minimal boundary**

If RED is v3 semantic/orchestration behavior, fix only `challenger_replacement_opportunities.py`. If and only if the failure proves a generic event-store bug, add a focused event test first and minimally fix `challenger_replacement_events.py`. Do not add callbacks or configuration seams.

- [ ] **Step 4: Add real two-process outcome races**

Use a test-only barrier around the existing private no-replace primitive. Same opportunity/same event must yield `{COMMITTED, ALREADY_COMMITTED}`; same opportunity/different outcome must yield `{COMMITTED, CONFLICT}`; different workers sharing a stale projection must leave one valid next event and one sequence conflict.

- [ ] **Step 5: Add v3 root-identity propagation tests**

Use one representative swapped-root and one untrusted canonical-final fixture to prove v3 replay/catch-up preserves the exact event-store failure reason and performs no semantic append. Do not duplicate every symlink/hardlink/FIFO/socket case already covered by `tests.test_challenger_replacement_events`.

- [ ] **Step 6: Run focused/adjacent tests and line/static gates**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_events \
  tests.test_challenger_replacement_opportunity_evidence \
  tests.test_challenger_replacement_opportunities \
  tests.test_challenger_replacement_plan_v3 \
  tests.test_challenger_replacement_plan_v3_supersession \
  tests.test_challenger_replacement_runtime
python3 -m compileall -q src tests
wc -l src/crypto_quant/challenger_replacement_opportunities.py
rg -n "sqlite3|PRAGMA|WAL|SHM|fault_injector|requests|urllib|httpx|aiohttp|websocket|subprocess|Popen|Broker|Order|PnL" \
  src/crypto_quant/challenger_replacement_opportunities.py \
  src/crypto_quant/challenger_replacement_opportunity_evidence.py
git diff --check
```

Expected: tests/compileall/diff-check pass; opportunities module <=700 lines; static scan has no imported or executable forbidden facility.

- [ ] **Step 7: Commit test hardening**

```bash
git add tests/test_challenger_replacement_opportunities.py \
  src/crypto_quant/challenger_replacement_opportunities.py \
  src/crypto_quant/challenger_replacement_events.py
git commit -m "test: harden opportunity recovery boundaries"
```

Omit unchanged files from `git add`; do not create an empty implementation change.

---

### Task 6: Freeze release docs, version and build manifest

**Files:**
- Create: `tests/test_challenger_replacement_v070_release.py`
- Create: `docs/adr/0070-decision-opportunity-event-runtime.md`
- Create: `docs/implementation-status-v0.70.0.md`
- Modify: `src/crypto_quant/build.py`
- Modify: `pyproject.toml`
- Modify: `setup.py`
- Modify: `src/crypto_quant/__init__.py`
- Modify: `scripts/refresh_evaluator_build_manifest.py`
- Modify: `config/evaluator-build-manifest-v1.json`
- Modify: `tests/test_estimators.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: final reviewed v0.70 code/test inventory.
- Produces: package `0.70.0`, manifest `1.64.0`, committed release regression and nonactivation documentation.

- [ ] **Step 1: Write release RED tests before changing versions**

Assert package/version/manifest identities, required inventory entries, exact v0.69 artifact hashes, unchanged v2 runtime source hash, static absence of forbidden imports/public APIs, no PnL projection fields, and the README/status nonclaims.

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_v070_release
```

Expected: failures on version `0.69.0`, manifest `1.63.0`, missing inventory/docs.

- [ ] **Step 2: Add ADR and implementation status**

ADR must record: separate v3 semantic module, single event authority, MISSED recovery/no-backfill, fixture-only evidence, split v0.71/v0.72/v0.73, and rejected alternatives. Status must report exact test/review/CI fields without claiming them before execution; use `PENDING_VERIFICATION` values until each gate is actually completed.

- [ ] **Step 3: Update package/manifest source inventory**

Set:

```text
package_version = 0.70.0
manifest_version = 1.64.0
```

Add every new source/schema/test/spec/plan/ADR/status path to `EvaluatorBuild.expected_file_paths`. Do not remove predecessor release inputs.

- [ ] **Step 4: Refresh manifest once and run release GREEN**

```bash
PYTHONPATH=src python3 scripts/refresh_evaluator_build_manifest.py
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_v070_release \
  tests.test_estimators
git diff --check
```

Expected: pass and manifest replay exact.

- [ ] **Step 5: Commit release candidate**

```bash
git add pyproject.toml setup.py src/crypto_quant/__init__.py \
  src/crypto_quant/build.py scripts/refresh_evaluator_build_manifest.py \
  config/evaluator-build-manifest-v1.json tests/test_estimators.py \
  tests/test_challenger_replacement_v070_release.py README.md \
  docs/adr/0070-decision-opportunity-event-runtime.md \
  docs/implementation-status-v0.70.0.md
git commit -m "chore: prepare v0.70.0 release candidate"
```

---

### Task 7: Final verification, independent review and public release

**Files:**
- Modify only for findings: files named by a Critical/Important review or verification failure.
- Modify after verified facts: `docs/implementation-status-v0.70.0.md`, `config/evaluator-build-manifest-v1.json`.

**Interfaces:**
- Consumes: immutable candidate HEAD from Tasks 1–6.
- Produces: reviewed PR candidate and, only after all gates pass, public main/tag identity.

- [ ] **Step 1: Run the milestone local full suite exactly once**

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
python3 -m compileall -q src tests
make validate
git diff --check
git status --short
```

Expected: all pass; worktree clean. Do not rerun the unchanged full suite.

- [ ] **Step 2: Request independent read-only review**

Reviewer compares `v0.69.0..HEAD` against the spec and plan, reporting Critical/Important/Minor with file/line evidence. It must explicitly inspect no-backfill, time authority, fixture-only evidence, terminal immutability, concurrency, no PnL and forbidden runtime authority.

- [ ] **Step 3: Fix findings with targeted RED/GREEN only**

For each Critical/Important finding: reproduce with one focused failing test, minimally fix, run affected/adjacent tests, and request targeted rereview. Do not repeat the entire review or full suite when code state is unchanged.

- [ ] **Step 4: Refresh final manifest and exact candidate evidence**

After the final code/doc state, refresh the manifest, run release/manifest focused tests, record exact HEAD/tree/manifest hashes in status, and commit. If code changed after Step 1, run one final full suite for that new final code state; otherwise do not duplicate it.

- [ ] **Step 5: Verify GitHub write target before remote mutation**

```bash
git remote get-url origin
gh repo view cjl308868584-lang/crypto-quant-core \
  --json nameWithOwner,visibility,viewerPermission,defaultBranchRef
git fetch origin main --tags
git rev-parse origin/main
git rev-parse 'v0.69.0^{}'
```

Expected: exact public repository, `ADMIN`, default `main`, released v0.69 foundation unchanged.

- [ ] **Step 6: Create public Draft PR and wait for CI**

Push only `codex/v0.70-decision-opportunity-runtime`, create Draft PR, mark ready after final review, and require Python 3.9, Python 3.12 and macOS arm64 jobs to pass on the exact head. Any CI failure returns to focused root-cause/TDD; do not bypass it because public Actions minutes are available.

- [ ] **Step 7: Merge, verify main CI and create annotated tag**

Merge only the reviewed exact head, wait for main CI, then create annotated `v0.70.0`. Verify:

```bash
test "$(git rev-parse origin/main)" = "$(git rev-parse 'v0.70.0^{}')"
git cat-file -t v0.70.0
```

Expected: identities equal and tag object type is `tag`.

- [ ] **Step 8: Durable checkpoint**

Report PR, reviewed head, merged main, CI run IDs, annotated tag object/peeled commit, manifest identity, exact tests, authority counts, nonclaims and next design scope (`v0.71` Binance deterministic simulation). Do not claim Paper/start/operational/economic/Canary completion.
