# System Paper Deployment Trust Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 发布 v0.58.0 的完整、无凭据、失败关闭 System Paper runtime/deployment/preflight/install/observer/start-receipt 信任链代码，但不执行生产安装或启动。

**Architecture:** 先修正并封存真实公共行情 source evidence，再由固定 runtime CLI 驱动 v0.57 WAL scheduler；独立 contract、preflight、installer、observer 和 start receipt modules 通过 exact bytes、mirrored schemas 和 production loaders 串联。所有真实 launchctl、network、bootstrap、Runner、Broker 和 order 边界在本版本测试及发布中保持零调用。

**Tech Stack:** Python 3.9+、标准库、`jsonschema>=4.25,<5`、SQLite WAL、macOS launchd、`unittest`、Git/GitHub Actions。

## Global Constraints

- Base is annotated `v0.57.0` peeled to `6b103a5d962ca53c470f08573418be73929b63a7`.
- Work only in `/Users/chenm4/Documents/虚拟货币/.worktrees/v0.58-system-paper-deployment` on `codex/v0.58-system-paper-deployment`.
- `production_activation.enabled=false`; credentials, account requests, Broker requests and real order writes remain zero.
- Do not render a production contract, run preflight, install/bootstrap/kickstart a service, invoke the runtime CLI, or create a start receipt during v0.58 development/release.
- Paper service label is exactly `local.crypto-quant.system-paper-v1`; no Challenger path, label, state, log, bundle, receipt or evidence root may be reused.
- All artifact JSON is strict, canonical, float-free, unknown-field rejecting, owner-only, single-link, no-overwrite and replayed by production loaders.
- Every Schema under `config/` is byte-identical to its packaged mirror under `src/crypto_quant/schemas/`.
- Real production boundaries use exactly four frozen public market GETs per fresh slot and zero on prepared-input/result recovery; tests inject all transports.
- TDD is mandatory: prove each red test fails for the intended missing behavior before implementation.
- Use `/usr/bin/python3` for the Python 3.9 local release baseline; the workspace `.venv` lacks pip and is not the v0.57 full-suite verifier.
- Each completed task gets its own commit and reviewer gate; do not combine unrelated refactors.

---

## File Structure

### Public input and runtime

- `src/crypto_quant/system_paper_public_input.py`: four-GET capture adapter, market bundle builder/loader and offline source replay.
- `src/crypto_quant/system_paper_runtime_cli.py`: fixed one-due-slot CLI; no source/time/fill/credential authority.
- `src/crypto_quant/offline_paper.py`: expose one verified normalized public market view from an issued capture; do not widen requests.
- `src/crypto_quant/system_paper_runtime.py`: verify `scheduled_for`, real `captured_at`, complete source receipts and Kline time continuity.
- `src/crypto_quant/system_paper_scheduler.py`: require scheduler envelope capture time to equal bundle capture time.
- `tests/system_paper_fixtures.py`: shared exact four-response fixture and valid bundle constructor.
- `config/system-paper-market-bundle-v1.schema.json` and packaged mirror: exact source-evidence contract.

### Deployment trust chain

- `src/crypto_quant/system_paper_launchd.py` / `_cli.py`: release snapshot, contract/plist renderer and loader; never installs.
- `src/crypto_quant/system_paper_preflight.py` / `_cli.py`: separate machine readiness receipt and loader.
- `src/crypto_quant/system_paper_install.py` / `_cli.py`: preflight-gated atomic user-domain installation and install receipt loader.
- `src/crypto_quant/system_paper_observer.py` / `_cli.py`: read-only first-natural-slot state/log/result/service observation.
- `src/crypto_quant/system_paper_start_receipt.py` / `_cli.py`: unique start receipt publisher/loader.
- Five mirrored deployment/start Schemas and focused test modules with matching names.

### Release integration

- `src/crypto_quant/build.py`, `scripts/refresh_evaluator_build_manifest.py`, `config/evaluator-build-manifest-v1.json`, `tests/test_estimators.py`: v0.58 complete build identity.
- `pyproject.toml`, `setup.py`, `src/crypto_quant/__init__.py`: package `0.58.0`.
- `docs/adr/0058-system-paper-deployment-trust-chain.md`, `docs/implementation-status-v0.58.0.md`, `README.md`: truthful release state.

---

### Task 1: Freeze replayable public market evidence and correct source time

**Files:**
- Create: `src/crypto_quant/system_paper_public_input.py`
- Create: `config/system-paper-market-bundle-v1.schema.json`
- Create: `src/crypto_quant/schemas/system-paper-market-bundle-v1.schema.json`
- Create: `tests/system_paper_fixtures.py`
- Create: `tests/test_system_paper_public_input.py`
- Modify: `src/crypto_quant/offline_paper.py`
- Modify: `src/crypto_quant/system_paper_runtime.py`
- Modify: `src/crypto_quant/system_paper_scheduler.py`
- Modify: `tests/test_offline_paper.py`
- Modify: `tests/test_system_paper_runtime.py`
- Modify: `tests/test_system_paper_scheduler.py`

**Interfaces:**
- Consumes: `VerifiedOfflinePaperCapture`, `SystemPaperInputRequest`, `SystemPaperInputCapture`, frozen plan and injected transport/clock.
- Produces: `verified_offline_paper_market(capture) -> Mapping[str, Any]`, `build_system_paper_market_bundle(...) -> Mapping[str, Any]`, `capture_system_paper_input(...) -> SystemPaperInputCapture`, `load_system_paper_market_bundle_bytes(body) -> Mapping[str, Any]`.

- [ ] **Step 1: Add the exact four-response shared fixture**

Move no production logic into tests. Build fixture responses whose last closed Kline ends exactly one millisecond before `scheduled_for`, whose exchange metadata becomes effective at the real decision time, and whose BBO/agg-trade responses occur inside the scheduler capture window.

```python
def valid_public_capture(*, scheduled_for="2026-08-02T12:00:00.000Z"):
    return capture_offline_paper(
        OfflinePaperPlan.create("ETHUSDT"),
        FixtureTransport(four_exact_responses(scheduled_for)),
        recorded_at=fixture_clock(scheduled_for),
    )
```

- [ ] **Step 2: Write red source-evidence tests**

Add tests proving:

```python
bundle = build_system_paper_market_bundle(
    plan=build_system_paper_plan(),
    scheduled_for="2026-08-02T12:00:00.000Z",
    capture=valid_public_capture(),
)
self.assertEqual(set(bundle), EXPECTED_MARKET_BUNDLE_KEYS)
self.assertEqual(len(bundle["source_receipts"]), 4)
self.assertGreater(bundle["captured_at"], bundle["scheduled_for"])
self.assertEqual(load_system_paper_market_bundle_bytes(canonical_json(bundle).encode()), bundle)
```

Also rehash each mutation and require failure for changed raw response, receipt time/hash, noncontiguous Kline, final close not `scheduled_for - 1ms`, metadata effective after `captured_at`, duplicate family, binary float, unknown field and old `observed_at/source_receipt_hashes` shape.

- [ ] **Step 3: Run the red tests**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_system_paper_public_input -v
```

Expected: import failure for `crypto_quant.system_paper_public_input`.

- [ ] **Step 4: Expose the verified offline market view**

Add to `offline_paper.py`:

```python
def verified_offline_paper_market(
    capture: VerifiedOfflinePaperCapture,
) -> Mapping[str, Any]:
    replayed = capture.replay_with_receipts(capture.receipts)
    decision_dt, decision_text = _utc(replayed.decision_time)
    return {
        "decision_time": decision_text,
        "closed_4h_klines": list(_parse_klines(_raw_body(replayed, 0), decision_dt)),
        "instrument_metadata": _parse_exchange_info(_raw_body(replayed, 1), decision_dt).business_payload(),
        "bbo": _parse_bbo(_raw_body(replayed, 2)),
        "agg_trade_window": _parse_agg_trades(_raw_body(replayed, 3)),
        "source_receipts": [dict(item) for item in replayed.receipts],
    }
```

Test that arbitrary mappings cannot bypass the issued capture token and that the existing offline paper run is unchanged.

- [ ] **Step 5: Implement market bundle Schema, builder and loader**

Use strict JSON and a Draft 2020-12 Schema. `captured_at` is the maximum receipt `recorded_at`; Kline rows retain only `open_time`, `close_time`, `close`, `source_row_hash`; BBO retains only bid/ask. Rebuild the normalized view from the full receipts during every load and compare canonical bytes.

- [ ] **Step 6: Implement the injected four-GET provider**

```python
def capture_system_paper_input(
    request: SystemPaperInputRequest,
    *,
    transport=None,
    clock=None,
) -> SystemPaperInputCapture:
    capture = capture_offline_paper(
        OfflinePaperPlan.create("ETHUSDT"),
        transport or BinanceOfflinePaperTransport(clock=clock),
        recorded_at=clock or _utc_now,
    )
    bundle = build_system_paper_market_bundle(
        plan=build_system_paper_plan(),
        scheduled_for=request.scheduled_for,
        capture=capture,
    )
    return SystemPaperInputCapture(
        public_market_bundle=bundle,
        capture_attempt_id=stable_id("system_paper_capture", {...}),
        captured_at=bundle["captured_at"],
        request_families=request.request_families,
        network_request_count=4,
    )
```

Production has one attempt per request because `_HTTP_ATTEMPTS == 1`. Assert no proxy, no credential, no private endpoint and no URL override surfaces.

- [ ] **Step 7: Correct runtime and scheduler verification**

Replace `observed_at/source_receipt_hashes` with the new Schema-backed loader. Validate metadata at `captured_at`, Kline close boundary at `scheduled_for`, and scheduler `capture.captured_at == bundle.captured_at`. Do not change strategy/cost/fill calculations.

- [ ] **Step 8: Run focused and adjacent suites**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_offline_paper \
  tests.test_system_paper_public_input \
  tests.test_system_paper_runtime \
  tests.test_system_paper_scheduler \
  tests.test_system_paper_fault_injection -v
```

Expected: PASS, with existing economic/golden assertions unchanged.

- [ ] **Step 9: Commit Task 1**

```bash
git add src/crypto_quant/offline_paper.py \
  src/crypto_quant/system_paper_public_input.py \
  src/crypto_quant/system_paper_runtime.py \
  src/crypto_quant/system_paper_scheduler.py \
  config/system-paper-market-bundle-v1.schema.json \
  src/crypto_quant/schemas/system-paper-market-bundle-v1.schema.json \
  tests/system_paper_fixtures.py tests/test_offline_paper.py \
  tests/test_system_paper_public_input.py tests/test_system_paper_runtime.py \
  tests/test_system_paper_scheduler.py
git commit -m "feat: bind replayable system paper market evidence"
```

---

### Task 2: Add the fixed one-slot runtime CLI

**Files:**
- Create: `src/crypto_quant/system_paper_runtime_cli.py`
- Create: `tests/test_system_paper_runtime_cli.py`

**Interfaces:**
- Consumes: `run_due_system_paper_slot`, `capture_system_paper_input`, fixed plan, fixed partial-then-full fill scenario.
- Produces: `main(argv=None, *, transport=None, clock=None, worker_identity=None) -> int`.

- [ ] **Step 1: Write red authority and lifecycle tests**

Require `--help` to expose only `--state-path` and `--output-root`. Reject relative/symlink/non-owner roots before transport. Assert there are no `url`, `symbol`, `time`, `plan`, `price`, `fee`, `fill`, `credential`, `account`, `broker`, `order` or `date` options.

Test a fresh due slot uses exactly four injected GETs and publishes one loadable result; a second invocation returns `ALREADY_SUCCEEDED` with zero GETs; prepared input/result recovery also uses zero new GETs.

- [ ] **Step 2: Run the red test**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_system_paper_runtime_cli -v
```

Expected: missing CLI module.

- [ ] **Step 3: Implement the bounded CLI**

```python
result = run_due_system_paper_slot(
    state_path=state_path,
    output_root=output_root,
    plan=build_system_paper_plan(),
    worker_id=derived_worker_id(worker_identity),
    public_input_provider=lambda request: capture_system_paper_input(
        request, transport=transport, clock=clock
    ),
    fill_scenario=FillScenario.partial_then_full("0.40"),
    clock=clock or _utc_now,
)
```

Print one canonical JSON line; errors print one canonical JSON object to stderr and return 1. Never print raw source bodies or economic aggregates.

- [ ] **Step 4: Run focused and recovery tests**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_system_paper_runtime_cli \
  tests.test_system_paper_scheduler \
  tests.test_system_paper_fault_injection -v
```

- [ ] **Step 5: Commit Task 2**

```bash
git add src/crypto_quant/system_paper_runtime_cli.py tests/test_system_paper_runtime_cli.py
git commit -m "feat: add fixed system paper runtime cli"
```

---

### Task 3: Render the independent release snapshot and LaunchAgent contract

**Files:**
- Create: `src/crypto_quant/system_paper_launchd.py`
- Create: `src/crypto_quant/system_paper_launchd_cli.py`
- Create: `config/system-paper-launchd-contract-v1.schema.json`
- Create: `src/crypto_quant/schemas/system-paper-launchd-contract-v1.schema.json`
- Create: `tests/test_system_paper_launchd.py`

**Interfaces:**
- Consumes: exact v0.57 foundation, clean annotated v0.58 checkout, build manifest, repository/runtime/python/output roots.
- Produces: `publish_system_paper_launchd_contract(...) -> Mapping`, `load_system_paper_launchd_contract(...) -> Mapping` and exact plist bytes.

- [ ] **Step 1: Write red separation, schedule and release tests**

Assert exact label, minute 5, six local hours, `RunAtLoad=true`, mode `0600`, child roots `0700`, only `PYTHONPATH`, and argv:

```python
(
    snapshot_python, "-m", "crypto_quant.system_paper_runtime_cli",
    "--state-path", runtime_root / "state/system-paper.sqlite",
    "--output-root", runtime_root / "artifacts",
)
```

Reject Challenger strings, shell/loop, API-key-like env names, dirty checkout, lightweight/missing tag, wrong v0.57 ancestor, wrong manifest/package/origin/main, source mutation, timezone mismatch, path overlap and symlink ancestor.

- [ ] **Step 2: Run red tests**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_system_paper_launchd -v
```

- [ ] **Step 3: Implement release inspection and private snapshot**

Use an injected command runner in tests and fixed `git` argv in production. Copy only manifest-enumerated files plus package metadata into an owner-only snapshot, fsync each file/directory, record relative path/SHA-256/size, then verify imports using snapshot Python/PYTHONPATH. Any source change during copy fails and removes only the newly created temporary snapshot.

- [ ] **Step 4: Implement contract/plist build, publish and loader**

Contract identity binds foundation, v0.58 release, plan/schedule hashes, snapshot inventory, fixed paths and plist hash. Loader replays exact plist bytes and snapshot inventory; self-hash alone is insufficient. Renderer result always reports `GENERATED_NOT_INSTALLED`, `launchctl_invoked=false`.

- [ ] **Step 5: Implement render-only CLI**

CLI accepts only `--repository-root`, `--runtime-root`, `--python-executable`, `--output-root`; it has no install/start/preflight/command selector.

- [ ] **Step 6: Run focused and Challenger separation tests**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_system_paper_launchd \
  tests.test_challenger_launchd \
  tests.test_challenger_cohort_evidence_maintenance_launchd -v
```

- [ ] **Step 7: Commit Task 3**

```bash
git add src/crypto_quant/system_paper_launchd.py \
  src/crypto_quant/system_paper_launchd_cli.py \
  config/system-paper-launchd-contract-v1.schema.json \
  src/crypto_quant/schemas/system-paper-launchd-contract-v1.schema.json \
  tests/test_system_paper_launchd.py
git commit -m "feat: render system paper deployment contract"
```

---

### Task 4: Build separate fail-closed machine preflight evidence

**Files:**
- Create: `src/crypto_quant/system_paper_preflight.py`
- Create: `src/crypto_quant/system_paper_preflight_cli.py`
- Create: `config/system-paper-preflight-receipt-v1.schema.json`
- Create: `src/crypto_quant/schemas/system-paper-preflight-receipt-v1.schema.json`
- Create: `tests/test_system_paper_preflight.py`

**Interfaces:**
- Consumes: production-loaded contract/plist, injected system command runner, stat/statvfs probes and exact public clock/ping transports.
- Produces: `run_system_paper_preflight(...) -> Mapping`, `load_system_paper_preflight_receipt(...) -> Mapping`.

- [ ] **Step 1: Write red verified/failed receipt tests**

Create fixture probes for exact commands only:

```text
/bin/launchctl print gui/<uid>
/bin/launchctl print gui/<uid>/local.crypto-quant.system-paper-v1
/usr/bin/pmset -g custom
```

Network fixtures permit three `/api/v3/time` samples and one `/api/v3/ping` GET. Assert verified receipt has `network_request_count=4`, zero credential/Broker/order counts, at least 5 GiB free, AC sleep safe, login domain present, service absent, target absent and all roots isolated.

For each failed probe, publish `PREFLIGHT_FAILED_CLOSED` only after contract load. Invalid contract/plist must create zero files. Rehashed mutation, expiry, machine identity drift, root replacement and duplicated receipt fail loader replay.

- [ ] **Step 2: Run red tests**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_system_paper_preflight -v
```

- [ ] **Step 3: Implement fixed probes and canonical result**

Do not use a shell. Bound stdout/stderr sizes, command count and response bytes. Parse `pmset` conservatively; unknown/missing AC sleep evidence fails. Use `os.statvfs` for disk; reject network filesystems and path identity changes.

- [ ] **Step 4: Implement exact publication and loader**

Verified receipts expire 30 minutes after `verified_at`. Failed receipts never authorize installation. Filename derives from stable receipt id; identical bytes are idempotent and conflicts are preserved.

- [ ] **Step 5: Implement the contract-derived CLI**

Expose only `--contract-path` and `--plist-path`; derive output root from contract. Tests call injected probes and make zero real command/network calls.

- [ ] **Step 6: Run focused and runtime-health tests**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_system_paper_preflight tests.test_runtime_health -v
```

- [ ] **Step 7: Commit Task 4**

```bash
git add src/crypto_quant/system_paper_preflight.py \
  src/crypto_quant/system_paper_preflight_cli.py \
  config/system-paper-preflight-receipt-v1.schema.json \
  src/crypto_quant/schemas/system-paper-preflight-receipt-v1.schema.json \
  tests/test_system_paper_preflight.py
git commit -m "feat: add system paper machine preflight"
```

---

### Task 5: Gate atomic installation on exact preflight

**Files:**
- Create: `src/crypto_quant/system_paper_install.py`
- Create: `src/crypto_quant/system_paper_install_cli.py`
- Create: `config/system-paper-install-receipt-v1.schema.json`
- Create: `src/crypto_quant/schemas/system-paper-install-receipt-v1.schema.json`
- Create: `tests/test_system_paper_install.py`

**Interfaces:**
- Consumes: contract/plist/preflight production loaders and fixed user-domain launchctl runner.
- Produces: `install_system_paper_launchd(...) -> Mapping`, `load_system_paper_install_receipt(...) -> Mapping`.

- [ ] **Step 1: Write red command-authority tests**

Without a current verified preflight, assert zero launchctl calls and zero writes. With one, the only allowed sequence is `print service`, optional `bootstrap domain target`, `print service`. Reject `kickstart`, `start`, `enable`, `submit`, `bootout`, shell or runtime CLI calls.

Test target mode `0600`, parent `0700`, exact bytes, inode-safe rollback only for a newly created target, existing exact service idempotency, service/file conflict, bootstrap failure, post-bootstrap print failure preservation and source/preflight mutation between checks.

- [ ] **Step 2: Run red tests**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_system_paper_install -v
```

- [ ] **Step 3: Implement source and preflight replay**

Load contract/plist and verified preflight, verify `now <= expires_at`, and compare current uid/home/path/device/release/snapshot identities before any launchctl call.

- [ ] **Step 4: Implement atomic install and receipt**

Use directory FDs, `O_NOFOLLOW`, exclusive temporary file, fsync, no-overwrite link/rename discipline and final inode comparison. Receipt records every fixed command argv/returncode/bounded stdout/stderr hash, target stat/hash and zero runtime/Broker/order counts.

- [ ] **Step 5: Implement CLI and production loader**

CLI exposes only `--contract-path`, `--plist-path`, `--preflight-receipt-path`; install receipt root comes from contract.

- [ ] **Step 6: Run focused and Challenger non-interference tests**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_system_paper_install \
  tests.test_challenger_launchd_install \
  tests.test_challenger_cohort_evidence_maintenance_install -v
```

- [ ] **Step 7: Commit Task 5**

```bash
git add src/crypto_quant/system_paper_install.py \
  src/crypto_quant/system_paper_install_cli.py \
  config/system-paper-install-receipt-v1.schema.json \
  src/crypto_quant/schemas/system-paper-install-receipt-v1.schema.json \
  tests/test_system_paper_install.py
git commit -m "feat: gate system paper launchd installation"
```

---

### Task 6: Observe the first natural slot without writes

**Files:**
- Create: `src/crypto_quant/system_paper_observer.py`
- Create: `src/crypto_quant/system_paper_observer_cli.py`
- Create: `tests/test_system_paper_observer.py`

**Interfaces:**
- Consumes: contract/preflight/install loaders, immutable SQLite state/WAL, stdout/stderr, slot result loader and one fixed launchctl print.
- Produces: `observe_system_paper_first_slot(...) -> Mapping[str, Any]`; never publishes a receipt.

- [ ] **Step 1: Write red state-machine tests**

Test all states:

```python
self.assertEqual(observe(empty_runtime)["status"], "WAITING_FOR_FIRST_NATURAL_SLOT")
self.assertEqual(observe(one_exact_success)["status"], "FIRST_NATURAL_SLOT_VERIFIED")
with self.assertRaisesRegex(..., "FIRST_SLOT_OBSERVATION_WINDOW_MISSED"):
    observe(two_successes_without_receipt)
```

Also fail on `MISSED/EXPIRED/FAILED`, non-zero exit evidence, unexpected stderr, missing/extra/hardlinked result, broken parent/event hash, prepared bytes mismatch, contract/install/service mismatch, path replacement during print and state/log/WAL changes between before/after snapshots.

Assert command count is one `launchctl print`; network, runtime, scheduler, state write, Broker and order counts are zero.

- [ ] **Step 2: Run red tests**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_system_paper_observer -v
```

- [ ] **Step 3: Implement descriptor-retained read-only snapshots**

Open owner-only regular files with no-follow semantics, read SQLite through immutable read-only URI or copied exact bytes without checkpointing WAL, hash all bytes, and compare `(st_dev, st_ino, mode, uid, nlink, size, mtime_ns, sha256)` before/after the fixed print.

- [ ] **Step 4: Implement exact event/result/log replay**

The sole verified slot must be the first scheduler slot after install, have one terminal `SUCCEEDED`, exact prepared input/result and a loadable slot artifact. Stdout must contain exactly the canonical success summary for that slot; stderr must be empty. More than one terminal slot before a start receipt is a permanent observation miss.

- [ ] **Step 5: Implement read-only CLI**

Expose only `--contract-path`, `--plist-path`, `--preflight-receipt-path`, `--install-receipt-path`. Print the summary; do not accept output root or publish anything.

- [ ] **Step 6: Run focused and first-slot adjacent tests**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_system_paper_observer \
  tests.test_challenger_first_slot_receipt \
  tests.test_system_paper_scheduler -v
```

- [ ] **Step 7: Commit Task 6**

```bash
git add src/crypto_quant/system_paper_observer.py \
  src/crypto_quant/system_paper_observer_cli.py \
  tests/test_system_paper_observer.py
git commit -m "feat: observe first natural system paper slot"
```

---

### Task 7: Publish and replay the immutable start receipt

**Files:**
- Create: `src/crypto_quant/system_paper_start_receipt.py`
- Create: `src/crypto_quant/system_paper_start_receipt_cli.py`
- Create: `config/system-paper-start-receipt-v1.schema.json`
- Create: `src/crypto_quant/schemas/system-paper-start-receipt-v1.schema.json`
- Create: `tests/test_system_paper_start_receipt.py`

**Interfaces:**
- Consumes: exact observer result plus contract/preflight/install/slot sources.
- Produces: `publish_system_paper_start_receipt(...) -> Mapping`, `load_system_paper_start_receipt(...) -> Mapping`.

- [ ] **Step 1: Write red publication and derivation tests**

Pending observation creates no directory/file. Verified first slot creates exactly one mode `0600` receipt under contract start root. Derive:

```python
self.assertEqual(receipt["cohort_started_at"], first_slot["scheduled_for"])
self.assertEqual(receipt["cohort_tail_end"], utc_plus_days(first_slot["scheduled_for"], 90))
self.assertEqual(receipt["expected_slot_count"], 540)
```

CLI must have no output root, clock/date/slot/filename/PnL/fee/price/label override. Identical exact bytes are idempotent; different bytes at the same stable identity conflict. Rehashed source/result/log/service mutation fails production replay.

- [ ] **Step 2: Run red tests**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_system_paper_start_receipt -v
```

- [ ] **Step 3: Implement receipt builder and exact publisher**

Bind full observation evidence, contract/plist, current verified preflight, install receipt, first slot exact SHA-256/loader identity, event-chain end hash, stdout/stderr stats and fixed safety counts. Use stable id and `artifact_self_hash`, but rederive external trust in loader.

- [ ] **Step 4: Implement production loader**

Loader enforces absolute canonical contract-derived path, owner/mode/single-link/size/canonical JSON/Schema/hash, then re-runs all source loaders and receipt semantic replay without launchctl or network.

- [ ] **Step 5: Implement CLI**

Expose only contract/plist/preflight/install receipt paths. Internally call the observer with one fixed launchctl print; publish only on verified state.

- [ ] **Step 6: Run all System Paper and non-interference suites**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -p 'test_system_paper_*' -v
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_challenger_forward_runner \
  tests.test_challenger_launchd \
  tests.test_challenger_launchd_install \
  tests.test_challenger_first_slot_receipt \
  tests.test_challenger_cohort_evidence_maintenance -v
```

- [ ] **Step 7: Commit Task 7**

```bash
git add src/crypto_quant/system_paper_start_receipt.py \
  src/crypto_quant/system_paper_start_receipt_cli.py \
  config/system-paper-start-receipt-v1.schema.json \
  src/crypto_quant/schemas/system-paper-start-receipt-v1.schema.json \
  tests/test_system_paper_start_receipt.py
git commit -m "feat: seal system paper start receipt"
```

---

### Task 8: Bind build identity, documentation and v0.58 version

**Files:**
- Modify: `src/crypto_quant/build.py`
- Modify: `scripts/refresh_evaluator_build_manifest.py`
- Modify: `config/evaluator-build-manifest-v1.json`
- Modify: `tests/test_estimators.py`
- Modify: `pyproject.toml`
- Modify: `setup.py`
- Modify: `src/crypto_quant/__init__.py`
- Create: `docs/adr/0058-system-paper-deployment-trust-chain.md`
- Create: `docs/implementation-status-v0.58.0.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: all reviewed v0.58 source/tests/schemas and frozen design/plan.
- Produces: package `0.58.0`, manifest `1.52.0`, complete file inventory and truthful code-only release status.

- [ ] **Step 1: Write red version/build tests**

Require package `0.58.0`, manifest `1.52.0`, and exact inclusion of every new source, test, Schema, spec, plan, ADR and implementation-status file. Require all Schema mirrors byte-identical.

- [ ] **Step 2: Run red tests**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_estimators -v
```

Expected: old `0.57.0/1.51.0` assertions fail.

- [ ] **Step 3: Update versions and deterministic build selection**

Set `0.58.0` in package files, `1.52.0` in refresh script, include all required paths in `EvaluatorBuild.expected_file_paths`, then refresh once:

```bash
PYTHONPATH=src /usr/bin/python3 scripts/refresh_evaluator_build_manifest.py
```

- [ ] **Step 4: Write truthful ADR/status/README**

Record code and test facts only. Explicitly state no production contract was rendered, no preflight/install/bootstrap/runtime occurred, no start receipt exists and 90-day timing remains not started. Do not claim profitability, AI advantage, Paper completion or Canary eligibility.

- [ ] **Step 5: Run focused build validation**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_estimators -v
PYTHONPATH=src /usr/bin/python3 -m compileall -q src tests
make validate
git diff --check
```

- [ ] **Step 6: Commit Task 8**

```bash
git add src/crypto_quant/build.py scripts/refresh_evaluator_build_manifest.py \
  config/evaluator-build-manifest-v1.json tests/test_estimators.py \
  pyproject.toml setup.py src/crypto_quant/__init__.py \
  docs/adr/0058-system-paper-deployment-trust-chain.md \
  docs/implementation-status-v0.58.0.md README.md
git commit -m "release: document system paper deployment v0.58.0"
```

---

### Task 9: Independent review and complete local verification

**Files:**
- Review: every file changed since `v0.57.0`.
- Modify only if review produces a proven defect; fixes require red regression tests.

**Interfaces:**
- Consumes: complete v0.58 branch.
- Produces: independent spec-compliance and code-quality review, clean local verification evidence.

- [ ] **Step 1: Request independent review**

Use `superpowers:requesting-code-review`. Reviewer must compare every design requirement to code/tests and specifically inspect source receipt replay, time semantics, snapshot/path races, launchctl authority, preflight expiry, observer read-only behavior and exact publication.

- [ ] **Step 2: Process review rigorously**

Use `superpowers:receiving-code-review`. Reproduce every valid finding, add a red regression test, make the smallest fix, rerun focused/adjacent tests and commit. Do not accept stylistic suggestions that weaken frozen evidence semantics.

- [ ] **Step 3: Run complete verification**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -v
PYTHONPATH=src /usr/bin/python3 -m compileall -q src tests
make validate
git diff --check
git status --short
```

Expected: all tests pass, commands exit zero, worktree clean. Record exact counts/hashes in implementation status if they changed after review, refresh manifest, and repeat affected verification.

- [ ] **Step 4: Prove forbidden effects remained zero**

Check no production root or LaunchAgent target was created and no target service exists due to this release. Use only read-only filesystem/`launchctl print` inspection; do not run any module capable of installation or runtime execution.

---

### Task 10: Draft PR, CI, merge and annotated v0.58.0 tag

**Files:**
- No source edits unless CI reveals a proven defect, in which case return to TDD/review.

**Interfaces:**
- Consumes: reviewed clean branch and exact local verification evidence.
- Produces: merged private-repository main, green PR/main CI and annotated `v0.58.0` peeled to exact main.

- [ ] **Step 1: Verify GitHub authority before writes**

Confirm target is private `cjl308868584-lang/crypto-quant-core`, origin exact URL, authenticated account has ADMIN/push, remote main is the v0.57 base, branch contains that base and `v0.58.0` does not exist. Plugin 404 may fall back only to authenticated `gh`.

- [ ] **Step 2: Push branch and create Draft PR**

Title: `release: System Paper deployment trust chain v0.58.0`. Include design/plan commits, exact test count, review result, safety zero counts and explicit not-installed/not-started status.

- [ ] **Step 3: Wait for PR CI and merge only reviewed head**

Require Python 3.9 and 3.12 checks green. Mark ready only after CI and review; merge only the exact reviewed head SHA.

- [ ] **Step 4: Wait for main CI**

Fetch remote main and require its CI green. Any failure returns to an isolated red-test fix; never amend evidence after merge without a new reviewed commit.

- [ ] **Step 5: Create annotated tag**

Create annotated `v0.58.0` at exact remote main, push it, then verify both:

```bash
git ls-remote origin refs/heads/main refs/tags/v0.58.0 'refs/tags/v0.58.0^{}'
git cat-file -t v0.58.0
```

Expected: tag object type `tag`; peeled commit equals remote main.

- [ ] **Step 6: Update the existing daily automation**

Keep the same automation id, thread and 08:25 schedule. Replace authority with exact `main@v0.58.0` SHA and make v0.59 90-day evaluator the next code-only phase. Preserve no-install/no-start/no-credentials/no-real-trading/fail-closed constraints.

## Plan Self-Review Record

- Spec coverage: Tasks 1–7 cover every runtime/deployment/preflight/install/observer/start boundary; Tasks 8–10 cover build, docs, review and GitHub release.
- Placeholder scan: passed; no unresolved markers, vague error-handling or unnamed-test steps remain.
- Type consistency: runtime provider returns the scheduler's existing `SystemPaperInputCapture`; all downstream CLIs consume only the paths produced by previous production loaders; start output root is always contract-derived.
- Scope: v0.58 remains code-only and does not absorb v0.59 evaluator, v0.60 projection or v0.61 Web/alerts/runbooks.

## Execution Choice

The user has already delegated implementation without further questions. Execute inline in this same thread with `superpowers:executing-plans`, using review checkpoints after each task. Do not dispatch subagents unless a later explicit user instruction authorizes parallel agent work.
