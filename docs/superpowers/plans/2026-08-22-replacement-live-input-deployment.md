# Replacement Challenger Live Input and Deployment Candidate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 v0.66 fixture-only 三阶段 runtime 升级为能生成真实公开行情 cohort-qualified event 的最小运行链，并发布固定、尚未安装的 deployment/preflight candidate。

**Architecture:** replacement-specific live adapter 通过固定 Binance public GET 产生 exact capture capability；source/decision v2 把 capture bytes 纳入 v0.66 append-only event authority；无参数 live CLI 只做自然槽派生和三阶段恢复。独立 deployment artifact、plist 与只读 preflight 定义未来 v0.68 安装边界，但 v0.67 不创建 production root、plist、service、receipt 或自然槽。

**Tech Stack:** Python 3.9+ stdlib (`urllib`, `ssl`, `datetime`, descriptor I/O)、`jsonschema`、`unittest`、launchd plist、Git/GitHub Actions Python 3.9/3.12 + macOS 15 arm64。

**Spec:** `docs/superpowers/specs/2026-08-22-replacement-live-input-deployment-design.md`

## Global Constraints

- Base is annotated `v0.66.0`: tag object `3b7ee80d0b6eb5e57934bd5b6cecf837e0a562d6`, peeled commit `12d835807580fb118f17942cd6a568e6b37818e3`.
- Exact v2 plan path is `artifacts/challenger-replacement/challenger-replacement-plan-v0.64.0.json`; file SHA-256 is `5f1774fd912451d79c9efe13401e80f312fee3c707d9faa252933ef3e8810a8f`.
- Sole cohort state authority remains `state/challenger-replacement-events-v1`; exports and standalone capture files are non-authoritative and not required.
- Successful state remains exactly `INPUT_PREPARED -> RESULT_PREPARED -> SLOT_SUCCEEDED`; do not add a network or deployment event type.
- v1 source/decision loaders remain fixture-only; production live CLI only accepts v2 cohort documents.
- Fixed network surface is `https://data-api.binance.vision`: exactly 3 `/api/v3/time` requests and 1..3 identical `/api/v3/klines` attempts, at most 6 public GETs per new slot.
- No production URL/transport/retry/clock/sleep/fault callback, enum, environment override, CLI override or generic exchange interface.
- The constructor token is an API-boundary guard, not cryptographic provenance and not a claim against a malicious same-UID Python process; release/service/start-receipt provenance remains a separate governance boundary.
- No credentials, environment proxies, account, balance, Broker, order, money, archive, PnL, evaluator, UI or third-party runtime dependency.
- No production root/plist/service creation, `launchctl bootstrap/kickstart/start`, natural Runner, install receipt, observer or start receipt in v0.67.
- `production_activation=false`, `runtime_install_authorized=false`, `replacement_start_authorized=false`, `real_orders_allowed=false` remain unchanged.
- New or net-added Python production code is strictly `<1800` physical lines. Stop and delete duplication before crossing the gate.
- Every implementation task is exact RED -> minimal GREEN -> refactor -> focused verification -> commit. The final unchanged code state gets one local full suite only.
- Public release gate remains Draft PR, Python 3.9/3.12 and macOS arm64 PR CI, merged-main CI, then annotated tag identity.

---

## File Map

**Create production modules**

- `src/crypto_quant/challenger_replacement_live_input.py`: capture capability, strict codec, fixed public HTTP acquisition and slot-window derivation.
- `src/crypto_quant/challenger_replacement_live_runtime_cli.py`: zero-business-argument natural invocation and bounded stdout/stderr/exit mapping.
- `src/crypto_quant/challenger_replacement_deployment.py`: deterministic deployment artifact, plist renderer and production loaders.
- `src/crypto_quant/challenger_replacement_preflight.py`: read-only machine/release/network readiness observation; no publication or install.

**Create schemas and committed candidates**

- `config/challenger-replacement-live-capture-v1.schema.json`
- `src/crypto_quant/schemas/challenger-replacement-live-capture-v1.schema.json`
- `config/challenger-replacement-source-bundle-v2.schema.json`
- `src/crypto_quant/schemas/challenger-replacement-source-bundle-v2.schema.json`
- `config/challenger-replacement-decision-v2.schema.json`
- `src/crypto_quant/schemas/challenger-replacement-decision-v2.schema.json`
- `config/challenger-replacement-deployment-v1.schema.json`
- `src/crypto_quant/schemas/challenger-replacement-deployment-v1.schema.json`
- `config/challenger-replacement-preflight-v1.schema.json`
- `src/crypto_quant/schemas/challenger-replacement-preflight-v1.schema.json`
- `artifacts/challenger-replacement/challenger-replacement-deployment-v0.67.0.json`
- `artifacts/challenger-replacement/local.crypto-quant.challenger-replacement-v1.plist`

**Modify production modules**

- `src/crypto_quant/challenger_replacement_evidence.py`: retain v1 fixture loader; add cohort source v2 builder/loader.
- `src/crypto_quant/challenger_replacement_decision.py`: retain v1 fixture loader; add source-v2-bound decision v2 builder/loader.
- `src/crypto_quant/challenger_replacement_runtime.py`: reuse one projection/append engine for v2 capability and zero-network resume.
- `src/crypto_quant/build.py`: manifest version `1.61.0` and v0.67 build inputs.
- `src/crypto_quant/__init__.py`, `pyproject.toml`, `setup.py`: package `0.67.0`.

**Create or modify tests**

- `tests/test_challenger_replacement_live_input.py`
- `tests/test_challenger_replacement_live_documents.py`
- `tests/test_challenger_replacement_live_runtime.py`
- `tests/test_challenger_replacement_deployment.py`
- `tests/test_challenger_replacement_preflight.py`
- `tests/test_challenger_replacement_v067_safety.py`
- `tests/test_challenger_replacement_v067_release.py`
- `tests/challenger_replacement_v2_fixtures.py`
- adjacent existing v0.66 replacement tests only where public signatures intentionally evolve.

**Release documentation**

- `docs/adr/0067-replacement-live-input-deployment-candidate.md`
- `docs/implementation-status-v0.67.0.md`
- `README.md`
- `config/evaluator-build-manifest-v1.json`
- `scripts/refresh_evaluator_build_manifest.py`
- `tests/test_estimators.py`
- `tests/test_v064_public_ci_bundle.py`
- `tests/test_nautilus_v065_release.py`
- `tests/test_challenger_replacement_v066_release.py`

---

### Task 1: Freeze the live-capture canonical codec and capability

**Files:**
- Create: `config/challenger-replacement-live-capture-v1.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-live-capture-v1.schema.json`
- Create: `src/crypto_quant/challenger_replacement_live_input.py`
- Create: `tests/test_challenger_replacement_live_input.py`

**Interfaces:**
- Produces: `ChallengerReplacementLiveInputError(reason_code)`, `ChallengerReplacementLiveCapture` with read-only `document` and `canonical_bytes`, `load_challenger_replacement_live_capture_bytes(data, *, plan, build_identity, previous_source_bundle) -> Mapping[str, Any]`.
- Internal only: `_build_live_capture_document(*, plan, build_identity, slot, clock_records, kline_request, attempts, selected_attempt_index, rows)`, `_grant_live_capture(*, document, canonical_bytes, token)`; direct public construction must raise `TypeError`.
- Consumes: `challenger_replacement_plan_v2_reasons`, canonical JSON/time/decimal/hash helpers, exact v0.67 build tuple fixtures.

- [ ] **Step 1: Add mirrored schema and capability RED tests**

Add tests with exact behavior:

```python
def test_live_capture_capability_cannot_be_constructed_directly(self):
    with self.assertRaises(TypeError):
        ChallengerReplacementLiveCapture(document={}, canonical_bytes=b"{}")

def test_live_capture_schema_mirrors_and_rejects_unknown_fields(self):
    self.assertEqual(CONFIG_SCHEMA.read_bytes(), PACKAGE_SCHEMA.read_bytes())
    Draft202012Validator.check_schema(json.loads(CONFIG_SCHEMA.read_text()))
```

Schema exact top-level keys must cover schema/version/id/hash, plan, build identity, qualification,
slot, clock evidence, kline request, attempts, selected index, rows and zero-authority counters.
Use `additionalProperties: false`; all prices are canonical decimal strings and times are canonical UTC
milliseconds.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_live_input.LiveCaptureCodecTests
```

Expected: import/schema failure because the v1 live-capture module and schema do not exist.

- [ ] **Step 3: Implement strict bytes loader and adapter-derived capability**

Implement constants and constructor exactly:

```python
_CAPTURE_SCHEMA = "./challenger-replacement-live-capture-v1.schema.json"
_QUALIFICATION = "REPLACEMENT_CONFIRMATORY_COHORT_INPUT"
_MAX_RESPONSE_BYTES = 256 * 1024
_MAX_CAPTURE_BYTES = 2 * 1024 * 1024
_CAPABILITY_TOKEN = object()

@dataclass(frozen=True, init=False)
class ChallengerReplacementLiveCapture:
    _document: Mapping[str, Any]
    _canonical_bytes: bytes

    def __init__(self, *, _token, document, canonical_bytes):
        if _token is not _CAPABILITY_TOKEN:
            raise TypeError("live capture capability is adapter-derived")
        object.__setattr__(self, "_document", deepcopy(dict(document)))
        object.__setattr__(self, "_canonical_bytes", bytes(canonical_bytes))

    @property
    def document(self):
        return deepcopy(dict(self._document))

    @property
    def canonical_bytes(self):
        return bytes(self._canonical_bytes)
```

The loader rejects duplicate keys, floats/constants, UTF-8 errors, oversized/noncanonical bytes,
schema errors, self-hash mismatch, wrong plan/build tuple, request count outside `4..6`, nonzero
credential/account/Broker/order counters, invalid attempts, selected-index mismatch, row/hash/time/window
errors and previous-source overlap revision. Loader returns a deep-copied mapping; only the private adapter
grants the capability.

- [ ] **Step 4: Run GREEN and mutation matrix**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_live_input.LiveCaptureCodecTests
```

Expected: all codec/schema/capability tests pass.

- [ ] **Step 5: Commit**

```bash
git add config/challenger-replacement-live-capture-v1.schema.json \
  src/crypto_quant/schemas/challenger-replacement-live-capture-v1.schema.json \
  src/crypto_quant/challenger_replacement_live_input.py \
  tests/test_challenger_replacement_live_input.py
git commit -m "feat: freeze replacement live capture codec"
```

---

### Task 2: Implement the bounded public acquisition adapter

**Files:**
- Modify: `src/crypto_quant/challenger_replacement_live_input.py`
- Modify: `tests/test_challenger_replacement_live_input.py`

**Interfaces:**
- Produces: `acquire_challenger_replacement_live_capture(*, state: ChallengerReplacementRuntimeState) -> ChallengerReplacementLiveCapture`.
- Consumes: strict state projection; private `_open_public_request(request)`, `_wall_now()`, `_monotonic()`, `_sleep(seconds)` are the only test-patched boundaries.
- No public function accepts URL, scheduled time, slot ID, sequence, transport, retry policy, clock or sleep callback.

- [ ] **Step 1: Add exact request/window/retry RED tests**

Tests patch only private module functions and implement these concrete cases:

```python
def test_exact_three_time_and_one_kline_happy_path(self):
    capture = self.acquire_with(self.three_times + [self.valid_kline])
    self.assertEqual(capture.document["network_request_count"], 4)
    self.assertEqual(len(self.requests), 4)

def test_two_transient_klines_then_success_records_six_requests(self):
    capture = self.acquire_with(
        self.three_times + [self.http_503, self.http_429, self.valid_kline]
    )
    self.assertEqual(capture.document["network_request_count"], 6)
    self.assertEqual(self.sleeps, [1, 2])

def test_malformed_http_200_is_not_retried(self):
    with self.assertRaisesRegex(ValueError, "LIVE_INPUT_JSON_INVALID"):
        self.acquire_with(self.three_times + [self.malformed_200])
    self.assertEqual(len(self.requests), 4)

def test_credential_environment_fails_before_request(self):
    with patch.dict(os.environ, {"BINANCE_API_KEY": "sentinel"}, clear=True):
        with self.assertRaisesRegex(ValueError, "LIVE_INPUT_ENVIRONMENT_FORBIDDEN"):
            acquire_challenger_replacement_live_capture(state=self.state)
    self.assertEqual(self.requests, [])
```

Each test body must use a fixed fake response object with status, final URL, selected headers, body,
request-start and response-received times; record every private request and sleep. Expected retry sleeps
are exactly `(1, 2)` seconds. Add separate concrete assertions for redirect rejection, proxy absence,
active/terminal/failed/pre-window/post-window/gap zero-network behavior, and byte-sorted kline query.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_live_input.LiveAcquisitionTests
```

Expected: `acquire_challenger_replacement_live_capture` missing.

- [ ] **Step 3: Implement fixed HTTP and clock contract**

Use exact constants:

```python
_BASE = "https://data-api.binance.vision"
_TIME_PATH = "/api/v3/time"
_KLINE_PATH = "/api/v3/klines"
_TRANSIENT_STATUS = {408, 425, 429, 500, 502, 503, 504}
_CAPTURE_OPEN = timedelta(minutes=2)
_CAPTURE_CLOSE = timedelta(minutes=10)
```

Use `ProxyHandler({})` and a redirect handler that always raises. Enforce HTTPS/final host/path/query,
GET/no body, content type, maximum bytes and 15-second timeout. Reject case-insensitive environment
names containing `proxy`, `credential`, `api_key`, `secret`, `token`, `authorization`, `cookie`,
`binance_key` or `binance_secret`, excluding the fixed launchd environment whitelist.

Replay state before any request. Derive genesis from verified three-sample Binance time; derive later
slots only from `next_required_slot`. Never fetch a missed completed-cohort slot. Build and reload the
canonical receipt before granting the capability.

- [ ] **Step 4: Run GREEN and static boundary scan**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_live_input
rg -n "requests|aiohttp|ccxt|API_KEY|SECRET_KEY|Authorization|Cookie" \
  src/crypto_quant/challenger_replacement_live_input.py
```

Expected: tests pass; scan finds no third-party client or credential surface. Independently assert the
module contains `ProxyHandler({})` and no zero-argument `ProxyHandler()`.

- [ ] **Step 5: Commit**

```bash
git add src/crypto_quant/challenger_replacement_live_input.py \
  tests/test_challenger_replacement_live_input.py
git commit -m "feat: acquire bounded replacement public input"
```

---

### Task 3: Add cohort source/decision v2 documents

**Files:**
- Create: `config/challenger-replacement-source-bundle-v2.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-source-bundle-v2.schema.json`
- Create: `config/challenger-replacement-decision-v2.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-decision-v2.schema.json`
- Modify: `src/crypto_quant/challenger_replacement_evidence.py`
- Modify: `src/crypto_quant/challenger_replacement_decision.py`
- Create: `tests/test_challenger_replacement_live_documents.py`
- Modify: `tests/challenger_replacement_v2_fixtures.py`

**Interfaces:**
- Produces: `build_challenger_replacement_cohort_source_bundle(*, plan, build_identity, live_capture, previous_source_bundle, previous_decision) -> dict`, `load_challenger_replacement_cohort_source_bundle_bytes(data, *, plan, build_identity, previous_source_bundle, previous_decision) -> dict`, `build_challenger_replacement_cohort_decision(*, plan, source_bundle, recorded_at, previous_decision) -> dict`, `load_challenger_replacement_cohort_decision_bytes(data, *, plan, source_bundle, previous_decision) -> dict`.
- Consumes: `ChallengerReplacementLiveCapture`; v1 builder/loaders remain unchanged and fixture-qualified.

- [ ] **Step 1: Add schema and qualification RED tests**

Build a granted fixture capture through the test's patched private HTTP boundary, then assert:

```python
source = build_challenger_replacement_cohort_source_bundle(
    plan=plan,
    build_identity=build_identity,
    live_capture=live_capture,
    previous_source_bundle=None,
    previous_decision=None,
)
self.assertEqual(
    source["evidence_qualification"],
    "REPLACEMENT_CONFIRMATORY_COHORT_EVIDENCE",
)
self.assertEqual(source["live_capture_receipt"], live_capture.document)
self.assertEqual(source["network_request_count_observed_by_core_runtime"], 0)
self.assertNotEqual(source["$schema"], fixture_v1_source["$schema"])
```

Add concrete genesis and second-slot tests requiring exact `+4h` and identical 20-bar overlap. Mutation
subtests pass a plain mapping, v1 bytes to the v2 loader, mismatched receipt/source rows, wrong build,
wrong plan, wrong parent and source-v1-bound decision; assert the corresponding fixed v2 reason code.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_live_documents
```

Expected: v2 schemas/functions missing.

- [ ] **Step 3: Implement v2 builders by extracting shared pure validators**

Keep v1 names and exact bytes stable. Extract only private shared functions for UTC, hashes, 21-bar
normalization and frozen decision math. v2 source requires `ChallengerReplacementLiveCapture`, reloads
its canonical bytes with the strict capture loader, copies the exact receipt object, and recomputes source
self-hash. v2 decision preserves the v0.64 plan policy exactly and changes only source/build/schema binding.

Do not add a generic `qualification=` argument, source schema selector, arbitrary builder registry or
network I/O to evidence/decision modules.

- [ ] **Step 4: Run GREEN and v1 compatibility tests**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_live_documents \
  tests.test_challenger_replacement_evidence \
  tests.test_challenger_replacement_decision
```

Expected: v2 tests pass and all v1 fixture tests retain exact fixture qualification.

- [ ] **Step 5: Commit**

```bash
git add config/challenger-replacement-source-bundle-v2.schema.json \
  config/challenger-replacement-decision-v2.schema.json \
  src/crypto_quant/schemas/challenger-replacement-source-bundle-v2.schema.json \
  src/crypto_quant/schemas/challenger-replacement-decision-v2.schema.json \
  src/crypto_quant/challenger_replacement_evidence.py \
  src/crypto_quant/challenger_replacement_decision.py \
  tests/test_challenger_replacement_live_documents.py \
  tests/challenger_replacement_v2_fixtures.py
git commit -m "feat: bind replacement cohort documents to live capture"
```

---

### Task 4: Advance and resume live slots without duplicate network

**Files:**
- Modify: `src/crypto_quant/challenger_replacement_runtime.py`
- Create: `src/crypto_quant/challenger_replacement_live_runtime_cli.py`
- Create: `tests/test_challenger_replacement_live_runtime.py`
- Modify: `tests/test_challenger_replacement_runtime.py`

**Interfaces:**
- Produces: `run_challenger_replacement_cohort_slot(*, state, live_capture, worker_id) -> Mapping[str, Any]`, `resume_challenger_replacement_slot(*, state, worker_id) -> Mapping[str, Any]`, private `_run_live_invocation() -> Mapping[str, Any]`, CLI `main(argv=None) -> int`.
- Consumes: live capability, v2 source/decision builders, v0.66 event/projection APIs.

- [ ] **Step 1: Add stage/recovery/CLI RED tests**

Write separate tests that create an owner-only fixture event root and assert:

```python
result = run_challenger_replacement_cohort_slot(
    state=state,
    live_capture=live_capture,
    worker_id="replacement-live-fixture-worker",
)
self.assertEqual(result["stage"], "SLOT_SUCCEEDED")
self.assertEqual(
    [event.event_type for event in state.replay()["events"]],
    ["INPUT_PREPARED", "RESULT_PREPARED", "SLOT_SUCCEEDED"],
)
```

At each committed stage, reopen a fresh event-root capability/state, patch the lowest private HTTP,
source-build, decision-build and event-append functions, and assert the exact zero side-effect counts
specified by the spec. Pass a plain mapping and a v1 fixture document and assert fixed capability errors.
Call `main(["--slot", "x"])` and each forbidden argument name; assert exit `2` and zero state/network.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_live_runtime
```

Expected: cohort/resume APIs and CLI missing.

- [ ] **Step 3: Refactor one private three-stage engine and add named entry points**

Extract a private `_append_prepared_result_and_success(*, state, slot_id, worker_id, source, source_bytes, decision, decision_bytes)` that only publishes already-built canonical result/success boundaries. The existing fixture entry and the new cohort entry each invoke their named source/decision builder before this shared append helper. `run_challenger_replacement_cohort_slot` is the only public v2 new-slot
entry and requires `ChallengerReplacementLiveCapture`. `resume_challenger_replacement_slot` accepts no
capture and only continues the current embedded INPUT/RESULT or returns exact SUCCESS.

Do not add a public builder callback, mode flag, schema name, fault injector or generic pipeline object.
Every append continues to use the projection's `expected_last_event_hash`; conflicts surface unchanged.

- [ ] **Step 4: Implement zero-business-argument CLI mapping**

`main()` rejects every `argv` item, loads only the fixed future contract path, replays before network,
and emits one canonical summary line without source rows, HTTP body, path inventory or economic values.
Map exact success/already-success to exit `0`, transient acquisition to `75`, permanent errors to `1`.

Because v0.67 is not installed, tests patch the private fixed-contract loader. There is no production
`--contract`, environment path or fixture option.

- [ ] **Step 5: Run GREEN and adjacent v0.66 recovery tests**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_live_runtime \
  tests.test_challenger_replacement_runtime \
  tests.test_challenger_replacement_events
```

Expected: all pass; event codec/stages remain unchanged.

- [ ] **Step 6: Commit**

```bash
git add src/crypto_quant/challenger_replacement_runtime.py \
  src/crypto_quant/challenger_replacement_live_runtime_cli.py \
  tests/test_challenger_replacement_runtime.py \
  tests/test_challenger_replacement_live_runtime.py
git commit -m "feat: run replacement cohort slots from live capability"
```

---

### Task 5: Freeze the deployment artifact and LaunchAgent candidate

**Files:**
- Create: `config/challenger-replacement-deployment-v1.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-deployment-v1.schema.json`
- Create: `src/crypto_quant/challenger_replacement_deployment.py`
- Create: `artifacts/challenger-replacement/challenger-replacement-deployment-v0.67.0.json`
- Create: `artifacts/challenger-replacement/local.crypto-quant.challenger-replacement-v1.plist`
- Create: `tests/test_challenger_replacement_deployment.py`

**Interfaces:**
- Produces: `build_challenger_replacement_deployment() -> Mapping[str, Any]`, `challenger_replacement_deployment_bytes() -> bytes`, `render_challenger_replacement_plist(deployment) -> bytes`, `load_challenger_replacement_deployment(path, *, manifest_path) -> Mapping[str, Any]`.
- Consumes: exact v0.64 plan, exact v0.66 foundation, candidate tuple `v0.67.0/0.67.0/1.61.0`.

- [ ] **Step 1: Add exact path/schedule/no-cycle RED tests**

Tests assert:

```python
self.assertEqual(deployment["candidate_release"], {
    "release_tag": "v0.67.0",
    "package_version": "0.67.0",
    "manifest_version": "1.61.0",
})
self.assertNotIn("manifest_hash", deployment["candidate_release"])
self.assertNotIn("peeled_commit", deployment["candidate_release"])
self.assertEqual(plist["RunAtLoad"], False)
self.assertEqual(plist["KeepAlive"], False)
```

Assert six schedule entries `(0,2),(4,2),(8,2),(12,2),(16,2),(20,2)`, no shell/arbitrary args,
no old/System Paper path, exact stdout/stderr, umask `077`, and exact module name.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_deployment
```

Expected: module/schema/artifacts missing.

- [ ] **Step 3: Implement deterministic builder, plist renderer and strict loader**

Use `plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=True)` and canonical JSON. Builder accepts no
parameters. Loader opens bounded regular files with no-follow/nonblocking descriptor checks, rebuilds
expected contract/plist, loads final build manifest separately, verifies candidate tuple and requires the
deployment/plist/module/schema files in manifest inputs. It does not expect the deployment object to
contain final manifest/tree/commit hashes.

- [ ] **Step 4: Generate candidates and prove 100-run determinism**

Render both candidates to stdout, capture their reviewed exact bytes, and add those two repository files
with `apply_patch`; do not add a production artifact publisher. Then run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_deployment
for i in $(seq 1 100); do
  PYTHONPATH=src python3 -c 'from crypto_quant.challenger_replacement_deployment import challenger_replacement_deployment_bytes; import sys; sys.stdout.buffer.write(challenger_replacement_deployment_bytes())' | shasum -a 256
done | sort -u
```

Expected: one unique hash; committed JSON and plist equal builder/renderer exact bytes.

- [ ] **Step 5: Commit**

```bash
git add config/challenger-replacement-deployment-v1.schema.json \
  src/crypto_quant/schemas/challenger-replacement-deployment-v1.schema.json \
  src/crypto_quant/challenger_replacement_deployment.py \
  artifacts/challenger-replacement/challenger-replacement-deployment-v0.67.0.json \
  artifacts/challenger-replacement/local.crypto-quant.challenger-replacement-v1.plist \
  tests/test_challenger_replacement_deployment.py
git commit -m "feat: freeze replacement deployment candidate"
```

---

### Task 6: Implement read-only preflight observation

**Files:**
- Create: `config/challenger-replacement-preflight-v1.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-preflight-v1.schema.json`
- Create: `src/crypto_quant/challenger_replacement_preflight.py`
- Create: `tests/test_challenger_replacement_preflight.py`

**Interfaces:**
- Produces: `observe_challenger_replacement_preflight(*, repository: Path, deployment_path: Path, manifest_path: Path) -> Mapping[str, Any]`, `load_challenger_replacement_preflight_bytes(data, *, deployment, plist_bytes) -> Mapping[str, Any]`.
- Consumes: deployment production loader, fixed private command/network functions, temporary fixture repository in tests.
- Does not publish a receipt and has no CLI in v0.67.

- [ ] **Step 1: Add machine-fact and zero-write RED tests**

Tests snapshot fixture tree and external sentinels with bytes, mode, size, mtime_ns, ctime_ns, inode,
device and nlink. Cover Darwin arm64/UID501/home/timezone/clock/release/tag/manifest, old service
decommission, replacement absence, ancestor security, disk/inodes/power/network and zero authority
counters.

Add a test in which runtime root/plist are absent and launchctl returns service-not-found; assert the only
historical wording is `NO_OBSERVABLE_REPLACEMENT_INSTALLATION_AT_COLLECTION`. Patch private subprocess
and network boundaries; verify exact argv/request counts and zero calls after an earlier identity failure.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_preflight
```

Expected: preflight module/schema missing.

- [ ] **Step 3: Implement retained read-only observation**

Use a fixed command allowlist for `git`, `launchctl print`, `pmset`, filesystem/disk and timezone
inspection. Map return codes/stdout/stderr to bounded hashes and parsed facts; do not expose a generic
command runner in public signatures. Reuse the live adapter's fixed three-sample time probe for network
offset evidence without a kline request. Never create a root, temp file, log, plist or receipt.

The preflight result status is exactly one of:

```text
PREFLIGHT_CANDIDATE_VERIFIED_NOT_PUBLISHED
PREFLIGHT_CANDIDATE_INELIGIBLE
PREFLIGHT_PLATFORM_UNSUPPORTED
```

Only the first is v0.68 design-eligible; none authorizes install or start.

- [ ] **Step 4: Run GREEN and mutation tests**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_preflight \
  tests.test_challenger_replacement_deployment
```

Expected: all pass and fixture/sentinels remain unchanged.

- [ ] **Step 5: Commit**

```bash
git add config/challenger-replacement-preflight-v1.schema.json \
  src/crypto_quant/schemas/challenger-replacement-preflight-v1.schema.json \
  src/crypto_quant/challenger_replacement_preflight.py \
  tests/test_challenger_replacement_preflight.py
git commit -m "feat: observe replacement deployment preflight"
```

---

### Task 7: Close crash, concurrency and no-side-effect safety gates

**Files:**
- Create: `tests/test_challenger_replacement_v067_safety.py`
- Modify only as failures require: the Task 1-6 production modules.

**Interfaces:**
- Consumes all v0.67 public APIs.
- Produces no new production abstraction; this task may delete or consolidate private helpers.

- [ ] **Step 1: Add end-to-end RED safety matrix**

Create separate subprocess/multiprocessing tests for every exact boundary:

```text
network success -> before INPUT append crash -> same-window reacquisition
INPUT visible -> dir fsync failure -> fresh replay with zero network
INPUT committed -> crash -> fresh RESULT/SUCCESS with zero network
RESULT committed -> crash -> fresh SUCCESS with zero network/compute
SUCCESS committed -> duplicate invocation -> zero network/compute/append
post-start missed next slot -> permanent continuity error and zero historical GET
event/deployment/manifest FIFO, socket, directory, symlink, hardlink, same-bytes-new-inode
close/fsync/read/write/HTTP/subprocess primary-vs-close exception preservation
```

For each external sentinel assert bytes, mode, size, mtime_ns, ctime_ns, inode, device and nlink exactly
match the before snapshot. Patch only existing private low-level boundaries; do not add production seams.

- [ ] **Step 2: Run RED and retain exact failure output**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_v067_safety
```

Expected: the first missing integration/failure mapping fails. Save the exact test name and reason in the
Task 7 commit body or durable checkpoint before implementing the fix.

- [ ] **Step 3: Make minimal fixes and enforce production surface/line budget**

Fix root causes without public seams. Run:

```bash
rg -n "fault_inject|callback|transport=|url=|sqlite3|PRAGMA|WAL|SHM|Broker|Order" \
  src/crypto_quant/challenger_replacement_{live_input,live_runtime_cli,deployment,preflight}.py
git diff --numstat 'v0.66.0^{}' -- src/crypto_quant | \
  awk '{add+=$1; del+=$2} END {print add, del, add-del}'
```

Review every scan hit in tests or descriptive strings; production injection/storage/order surfaces must
be absent. Net-added Python production lines must be `<1800`; otherwise delete duplication before moving.

- [ ] **Step 4: Run focused and adjacent GREEN**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_v067_safety \
  tests.test_challenger_replacement_live_input \
  tests.test_challenger_replacement_live_documents \
  tests.test_challenger_replacement_live_runtime \
  tests.test_challenger_replacement_deployment \
  tests.test_challenger_replacement_preflight \
  tests.test_challenger_replacement_events \
  tests.test_challenger_replacement_runtime
python3 -m compileall -q src tests
git diff --check
```

Expected: all tests pass; compileall and diff-check exit 0.

- [ ] **Step 5: Commit**

```bash
git add tests/test_challenger_replacement_v067_safety.py \
  src/crypto_quant/challenger_replacement_live_input.py \
  src/crypto_quant/challenger_replacement_live_runtime_cli.py \
  src/crypto_quant/challenger_replacement_deployment.py \
  src/crypto_quant/challenger_replacement_preflight.py \
  src/crypto_quant/challenger_replacement_evidence.py \
  src/crypto_quant/challenger_replacement_decision.py \
  src/crypto_quant/challenger_replacement_runtime.py
git commit -m "test: close replacement live deployment safety gates"
```

---

### Task 8: Freeze v0.67 release identity and documentation

**Files:**
- Create: `tests/test_challenger_replacement_v067_release.py`
- Create: `docs/adr/0067-replacement-live-input-deployment-candidate.md`
- Create: `docs/implementation-status-v0.67.0.md`
- Modify: `pyproject.toml`
- Modify: `setup.py`
- Modify: `src/crypto_quant/__init__.py`
- Modify: `src/crypto_quant/build.py`
- Modify: `scripts/refresh_evaluator_build_manifest.py`
- Modify: `config/evaluator-build-manifest-v1.json`
- Modify: `tests/test_estimators.py`
- Modify: `tests/test_v064_public_ci_bundle.py`
- Modify: `tests/test_nautilus_v065_release.py`
- Modify: `tests/test_challenger_replacement_v066_release.py`
- Modify: `README.md`

**Interfaces:**
- Produces package `0.67.0`, manifest `1.61.0`, status `DEPLOYMENT_CANDIDATE_RELEASED_NOT_INSTALLED`.
- Consumes all final v0.67 files and exact artifact bytes.

- [ ] **Step 1: Add release RED tests before metadata changes**

Tests assert exact version tuple, all schemas/artifacts/modules in the build manifest, deployment artifact
candidate tuple, v0.66 foundation, v2 plan SHA, no production roots/plist/service, no install/start receipt,
no live network in tests, and README/ADR/status wording. Status must include:

```text
production_activation=false
runtime_install_authorized=false
replacement_start_authorized=false
real_orders_allowed=false
no 90-day timer started
```

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_v067_release
```

Expected: version/manifest/docs failures.

- [ ] **Step 3: Update release metadata and docs**

Set package `0.67.0`, manifest `1.61.0`, add ADR/status/README, then refresh once:

```bash
PYTHONPATH=src python3 scripts/refresh_evaluator_build_manifest.py
```

Do not insert final merge commit or tag object into the deployment artifact. Record final manifest file
SHA/tree/hash in implementation status after refresh; v0.68 install receipt binds the future peeled commit.

- [ ] **Step 4: Run focused release GREEN**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_v067_release \
  tests.test_estimators
make validate
python3 -m compileall -q src tests
git diff --check
```

Expected: all commands exit 0. `make validate` may print intentionally frozen production-activation
ineligible reasons but the command itself must succeed.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml setup.py src/crypto_quant/__init__.py \
  src/crypto_quant/build.py scripts/refresh_evaluator_build_manifest.py \
  config/evaluator-build-manifest-v1.json \
  tests/test_challenger_replacement_v067_release.py \
  tests/test_estimators.py tests/test_v064_public_ci_bundle.py \
  tests/test_nautilus_v065_release.py \
  tests/test_challenger_replacement_v066_release.py \
  docs/adr/0067-replacement-live-input-deployment-candidate.md \
  docs/implementation-status-v0.67.0.md README.md
git commit -m "release: freeze replacement live deployment v0.67.0"
```

---

### Task 9: Final verification, review and public release

**Files:**
- Modify only files required to close verified review findings.

**Interfaces:**
- Produces a reviewed final candidate, Draft PR, green public PR/main CI and annotated `v0.67.0`.

- [ ] **Step 1: Run the final affected gate**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_live_input \
  tests.test_challenger_replacement_live_documents \
  tests.test_challenger_replacement_live_runtime \
  tests.test_challenger_replacement_deployment \
  tests.test_challenger_replacement_preflight \
  tests.test_challenger_replacement_v067_safety \
  tests.test_challenger_replacement_v067_release \
  tests.test_challenger_replacement_events \
  tests.test_challenger_replacement_runtime
make validate
python3 -m compileall -q src tests
git diff --check
```

- [ ] **Step 2: Request one independent complete review**

Review exact range `v0.66.0^{}..HEAD` against the spec and plan. The report must include
Critical/Important/Minor findings, live-provenance limitations, request-count correctness, state
authority, no-install boundary, line-budget calculation and test gaps. Critical and Important must be
zero before release.

- [ ] **Step 3: Fix findings with targeted RED/GREEN and targeted re-review**

For each accepted finding, add the smallest reproducer first, run it RED, apply the minimal fix, run
affected tests GREEN, and commit. Re-review only changed areas plus finding closure; do not repeat the
full review without new broad changes.

- [ ] **Step 4: Run one local full suite on the final unchanged commit**

```bash
make test
```

Expected: exit 0, no failures. Do not run a second local full suite on the same commit.

- [ ] **Step 5: Verify public remote identity and create Draft PR**

Create `/private/tmp/v067-pr-body.md` with a concise release summary that states no install/start,
no credentials/Broker/orders, the v0.66 fixture-only gap closed, fixed request limits, test/review
evidence and remaining v0.68 gate. Then run:

```bash
gh repo view cjl308868584-lang/crypto-quant-core \
  --json visibility,viewerPermission,nameWithOwner
git remote get-url origin
git fetch origin main --tags
git push -u origin codex/v0.67-replacement-live-input-deployment
gh pr create --draft --base main \
  --head codex/v0.67-replacement-live-input-deployment \
  --title "v0.67.0 replacement live input deployment candidate" \
  --body-file /private/tmp/v067-pr-body.md
```

- [ ] **Step 6: Require exact public PR CI before merge**

Verify PR head SHA and require successful jobs:

```text
deterministic-core (3.9)
deterministic-core (3.12)
nautilus-sandbox (3.12, macos-15 arm64)
```

Do not rerun successful jobs. If a job fails, diagnose exact logs, add a RED reproducer where applicable,
fix and push a new head.

- [ ] **Step 7: Merge, require main CI, and create annotated tag**

After PR CI is green, mark ready and merge normally. Verify origin/main exact merge commit, then require
the corresponding main CI run with all three jobs successful. Only then:

```bash
main_commit=$(git rev-parse refs/remotes/origin/main)
git tag -a v0.67.0 "$main_commit" \
  -m "v0.67.0: replacement live input deployment candidate"
git push origin refs/tags/v0.67.0
git ls-remote origin refs/heads/main refs/tags/v0.67.0 'refs/tags/v0.67.0^{}'
```

Require `main_commit` to be the freshly fetched 40-character origin/main commit, local object type `tag`,
and remote peeled commit exactly equal origin/main. Preserve the worktree through PR
feedback; cleanup is a separate non-destructive finishing step.

- [ ] **Step 8: Durable handoff to v0.68**

Record exact branch/head, PR, PR CI, main, main CI, tag object/peeled identity, test counts, review result,
manifest identities, line budget and status `DEPLOYMENT_CANDIDATE_RELEASED_NOT_INSTALLED`. The next design
is v0.68 installer/observer/start receipt; do not install as part of this plan.
