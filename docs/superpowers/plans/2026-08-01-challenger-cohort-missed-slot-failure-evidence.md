# Challenger Cohort Missed-Slot Failure Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 只读证明原 Challenger cohort 的永久漏槽，发布可重放的 exact failure receipt，并在 receipt 验证后受控停用旧 LaunchAgent，同时保留全部现场证据。

**Architecture:** `challenger_cohort_failure.py` 复用 v0.48 的冻结 plan/state/partition/bundle/launchd 语义，但使用 failure-specific stderr 验证并只执行一次 `launchctl print`。`challenger_cohort_decommission.py` 只接受 loader-verified failure receipt，固定调用一次无 shell 的 `launchctl bootout`，验证服务卸载与所有现场哈希不变，再发布 decommission receipt。两个 runtime receipts 由独立 release helper 逐字节复制到 Git。

**Tech Stack:** Python 3.9+、标准库、SQLite immutable read、`jsonschema>=4.25,<5`、macOS launchd、`unittest`、现有 canonical JSON/no-overwrite publisher。

## Global Constraints

- 冻结设计：`docs/superpowers/specs/2026-08-01-challenger-cohort-missed-slot-failure-evidence-design.md`。
- 代码基线：`v0.53.0` / `d0a7f2e31c469c6983a205906d25e7b6f9d7e433`。
- v0.48 evaluator identity：`09b81b9f3a670a20301d4b1090bb4293afc5bc7c`。
- 旧 cohort 的 state、WAL、SHM、stdout、stderr、source bundles、plans、receipts、archives、results、contract、plist 和 install receipt 不得修改或删除。
- Failure observer 不得触发 Runner、maintenance、市场/Kline、Broker、凭据或订单；`launchctl print` 固定一次。
- Decommission 前必须 loader-verify exact failure receipt；唯一允许的运行状态变化是固定 argv 的 `launchctl bootout gui/501/local.crypto-quant.challenger-forward`。
- 不创建、不安装、不启动 replacement cohort 或 System Paper。
- Runtime output root 固定为 `/Users/chenm4/Library/Application Support/CryptoQuant/challenger-forward-v1/cohort-failures`，目录 0700、文件 0600。
- Git artifacts 固定为 `artifacts/challenger-forward/challenger-cohort-missed-slot-failure-receipt-v0.54.0.json` 与 `artifacts/challenger-forward/challenger-cohort-decommission-receipt-v0.54.0.json`。
- 每个代码任务使用 TDD；失败测试必须先于实现；每个任务独立提交。
- `production_activation.enabled=false` 保持不变。

---

## File Structure

- `src/crypto_quant/challenger_cohort_failure.py`：只读 failure observer、receipt builder/publisher、semantic loader。
- `src/crypto_quant/challenger_cohort_failure_cli.py`：只接受冻结输入路径和 owner-only output root。
- `src/crypto_quant/challenger_cohort_failure_release.py`：runtime failure/decommission receipts 到 Git 固定文件名的 exact-byte publisher。
- `src/crypto_quant/challenger_cohort_failure_release_cli.py`：固定 release kind 与路径边界。
- `src/crypto_quant/challenger_cohort_decommission.py`：preflight、固定 bootout、后验和 decommission receipt loader。
- `src/crypto_quant/challenger_cohort_decommission_cli.py`：不暴露 command/service override 的操作入口。
- `config/challenger-cohort-failure-receipt-v1.schema.json` 与 packaged mirror：failure receipt Schema。
- `config/challenger-cohort-decommission-receipt-v1.schema.json` 与 packaged mirror：decommission receipt Schema。
- `tests/test_challenger_cohort_failure.py`：观察、发布、loader、CLI 边界。
- `tests/test_challenger_cohort_failure_release.py`：exact Git release 与 committed artifact 回归。
- `tests/test_challenger_cohort_decommission.py`：bootout 前置、固定 argv、后验和 loader。
- `docs/adr/0054-challenger-cohort-missed-slot-failure-evidence.md`：工程裁决。
- `docs/implementation-status-v0.54.0.md`：真实证据和验证结果。

---

### Task 1: Failure observer, receipt and production loader

**Files:**
- Create: `src/crypto_quant/challenger_cohort_failure.py`
- Create: `config/challenger-cohort-failure-receipt-v1.schema.json`
- Create: `src/crypto_quant/schemas/challenger-cohort-failure-receipt-v1.schema.json`
- Create: `tests/test_challenger_cohort_failure.py`

**Interfaces:**
- Consumes: exact v0.43 plan, v0.44 evaluation plan, v0.35 install receipt/contract/plist and injected `clock`/`_launchctl_runner` in tests.
- Produces: `observe_challenger_cohort_missed_slot_failure` and `load_challenger_cohort_failure_receipt`, each returning `Mapping[str, Any]`; `challenger_cohort_failure_receipt_hash(receipt) -> str`.

- [ ] **Step 1: Write the failing verified-failure test**

```python
def test_exact_missed_slot_publishes_loadable_failure_receipt(self):
    summary = observe_challenger_cohort_missed_slot_failure(
        cohort_plan_path=self.cohort_plan,
        evaluation_plan_path=self.evaluation_plan,
        install_receipt_path=self.install_receipt,
        contract_path=self.contract,
        plist_path=self.plist,
        failure_output_root=self.failure_root,
        clock=lambda: "2026-08-01T08:27:01.000Z",
        _launchctl_runner=self.failed_launchctl,
    )
    self.assertEqual(summary["status"], "COHORT_MISSED_SLOT_FAILURE_VERIFIED")
    self.assertEqual(summary["next_required_slot"], "2026-08-01T04:00:00.000Z")
    self.assertEqual(summary["market_request_count"], 0)
    self.assertEqual(summary["runner_invocation_count"], 0)
    receipt = load_challenger_cohort_failure_receipt(
        receipt_path=Path(summary["receipt_path"]),
        cohort_plan_path=self.cohort_plan,
        evaluation_plan_path=self.evaluation_plan,
        install_receipt_path=self.install_receipt,
        contract_path=self.contract,
        plist_path=self.plist,
    )
    self.assertEqual(receipt["eligibility"]["old_cohort"],
                     "PERMANENTLY_INELIGIBLE_CONTINUITY_GAP")
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_challenger_cohort_failure -v`

Expected: FAIL with `ModuleNotFoundError: crypto_quant.challenger_cohort_failure`.

- [ ] **Step 3: Implement strict source and time primitives**

Implement `ChallengerCohortFailureError(reason_code)`, strict UTC parsing,
owner-only absolute regular-file reads with read-race detection, and an immutable
snapshot helper.  The concrete public behavior is fixed by the tests in Steps 1
and 7 rather than by incomplete pseudo-code.

`_secure_file` rejects relative paths, symlinks, non-regular files, wrong owner, hardlinks, group/world writes, size changes and read races. `_snapshot` covers state/WAL/SHM/stdout/stderr plus canonical source-bundle inventory.

- [ ] **Step 4: Implement the failure-specific observation**

Use `_read_exact_plan`, `_read_exact_evaluation_plan`, `_trusted_sources`, `_read_state`, `_partition`, `_bundle_evidence`, `_slot_summary` and `_launchctl_evidence` from the unchanged production modules. Construct stdout evidence field-by-field from `_log_lines`; require one matching `RECORDED` record per verified decision. Require stderr exact bytes:

```python
_MISSED_SLOT_STDERR = b'{"error":"CHALLENGER_RUNNER_MISSED_SLOT"}\n'
```

Derive `next_required_slot` from the last trusted decision, require `current_slot > next_required_slot`, require `state="not running"`, `runs >= 1`, `last_exit_code == 1`, and compare complete before/after snapshots.

- [ ] **Step 5: Implement canonical receipt identity and publication**

```python
def challenger_cohort_failure_receipt_hash(receipt: Mapping[str, Any]) -> str:
    return artifact_self_hash(receipt, "receipt_hash")

def _identity(receipt: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "cohort_plan_hash": receipt["sources"]["cohort_plan"]["plan_hash"],
        "evaluation_plan_hash": receipt["sources"]["evaluation_plan"]["plan_hash"],
        "state_file_sha256": receipt["evidence_after"]["state"]["sha256"],
        "stderr_sha256": receipt["evidence_after"]["stderr"]["sha256"],
        "next_required_slot": receipt["failure"]["next_required_slot"],
        "current_slot": receipt["failure"]["current_slot"],
        "observed_at": receipt["observed_at"],
    }
```

Set `receipt_id = stable_id("challenger_cohort_failure_receipt", _identity(receipt))`; publish with `_publish_exact` below `challenger-cohort-failure-receipts/<receipt-id>.json`.

- [ ] **Step 6: Implement semantic loader and mirrored Schema**

The loader re-reads plans/install chain, validates canonical bytes, Schema, self-hash, fixed v0.48 identity, derived service/paths, one-or-more identical exact missed-slot stderr lines and their count, slot ordering, prefix counts, before/after equality, eligibility and every zero safety counter. It does not call launchctl or require the service to remain loaded after decommission.

- [ ] **Step 7: Add negative and idempotency tests**

Add explicit tests for current slot not late, empty/multiple/wrong stderr, running service, exit code 0, missing/duplicate bundle, missing stdout record, internal decision gap, state/log mutation during observation, symlink/hardlink, CLI-ineligible output root, same receipt retry preserving inode/mtime, conflict bytes and 100 deterministic builds.

- [ ] **Step 8: Run focused and adjacent tests**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_cohort_failure -v
PYTHONPATH=src python3 -m unittest tests.test_challenger_cohort_cumulative_evaluation tests.test_challenger_cohort_episode_receipt tests.test_challenger_forward_runner -v
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/crypto_quant/challenger_cohort_failure.py src/crypto_quant/schemas/challenger-cohort-failure-receipt-v1.schema.json config/challenger-cohort-failure-receipt-v1.schema.json tests/test_challenger_cohort_failure.py
git commit -m "feat: verify challenger missed-slot failure"
```

### Task 2: Failure CLI and exact runtime-to-Git release

**Files:**
- Create: `src/crypto_quant/challenger_cohort_failure_cli.py`
- Create: `src/crypto_quant/challenger_cohort_failure_release.py`
- Create: `src/crypto_quant/challenger_cohort_failure_release_cli.py`
- Create: `tests/test_challenger_cohort_failure_release.py`
- Modify: `tests/test_challenger_cohort_failure.py`

**Interfaces:**
- Consumes: Task 1 observer/loader and absolute trusted paths.
- Produces: CLI JSON summary; `release_challenger_cohort_failure_receipt` returning `Mapping[str, Any]`; later `release_challenger_cohort_decommission_receipt` using the same fixed publisher.

- [ ] **Step 1: Write failing CLI authority tests**

```python
def test_cli_exposes_only_frozen_paths(self):
    destinations = {action.dest for action in _parser()._actions}
    self.assertEqual(destinations - {"help"}, {
        "cohort_plan_path", "evaluation_plan_path", "install_receipt_path",
        "contract_path", "plist_path", "failure_output_root",
    })
    for forbidden in ("clock", "service", "state", "stderr", "slot", "command"):
        self.assertNotIn(forbidden, destinations)
```

- [ ] **Step 2: Implement CLI path boundary and structured errors**

Allow input files only as absolute paths. Require `failure_output_root` to be under `~/Library/Application Support/CryptoQuant`, owner-only 0700 if it exists, and neither a symlink nor an ancestor/equal of state/bundle roots. On error print compact JSON with `status="FAILED_CLOSED_EVIDENCE_UNTRUSTED"` and return 1.

- [ ] **Step 3: Write failing exact-release tests**

Test source mode 0600, single link, canonical loader pass, fixed Git filename, no-overwrite, identical retry, conflict, symlink, rollback on post-publish loader failure and committed artifact regression when the artifact exists.

- [ ] **Step 4: Implement the fixed release publisher**

```python
_FAILURE_ARTIFACT = "challenger-cohort-missed-slot-failure-receipt-v0.54.0.json"
_DECOMMISSION_ARTIFACT = "challenger-cohort-decommission-receipt-v0.54.0.json"

def release_challenger_cohort_failure_receipt(
    *,
    runtime_receipt_path: Path,
    artifact_output_path: Path,
    cohort_plan_path: Path,
    evaluation_plan_path: Path,
    install_receipt_path: Path,
    contract_path: Path,
    plist_path: Path,
) -> Mapping[str, Any]:
    """Loader-verify and publish the fixed exact-byte Git artifact."""
```

Read source before/after stat, loader-verify runtime, atomically hardlink a mode-0600 temporary inode to the fixed Git target, loader-verify target, compare bytes and SHA-256, and rollback only the exact newly created target on failure.

- [ ] **Step 5: Run tests and commit**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_cohort_failure tests.test_challenger_cohort_failure_release -v
git add src/crypto_quant/challenger_cohort_failure_cli.py src/crypto_quant/challenger_cohort_failure_release.py src/crypto_quant/challenger_cohort_failure_release_cli.py tests/test_challenger_cohort_failure.py tests/test_challenger_cohort_failure_release.py
git commit -m "feat: release exact challenger failure receipt"
```

### Task 3: Controlled decommission and receipt

**Files:**
- Create: `src/crypto_quant/challenger_cohort_decommission.py`
- Create: `src/crypto_quant/challenger_cohort_decommission_cli.py`
- Create: `config/challenger-cohort-decommission-receipt-v1.schema.json`
- Create: `src/crypto_quant/schemas/challenger-cohort-decommission-receipt-v1.schema.json`
- Create: `tests/test_challenger_cohort_decommission.py`
- Modify: `src/crypto_quant/challenger_cohort_failure_release.py`
- Modify: `src/crypto_quant/challenger_cohort_failure_release_cli.py`

**Interfaces:**
- Consumes: loader-verified failure receipt and the same plans/install chain.
- Produces: `decommission_failed_challenger_cohort` and `load_challenger_cohort_decommission_receipt`, each returning `Mapping[str, Any]`; exact Git release support.

- [ ] **Step 1: Write failing preflight and fixed-command tests**

```python
def test_verified_failure_runs_one_fixed_bootout_and_preserves_files(self):
    runner = RecordingCommandRunner(
        before=self.failed_print,
        bootout=CommandResult(returncode=0, stdout=b"", stderr=b""),
        after=CommandResult(
            returncode=113,
            stdout=b"",
            stderr=(
                b'Bad request.\nCould not find service '
                b'"local.crypto-quant.challenger-forward" '
                b'in domain for user gui: 501\n'
            ),
        ),
    )
    summary = decommission_failed_challenger_cohort(
        failure_receipt_path=self.failure_receipt,
        cohort_plan_path=self.cohort_plan,
        evaluation_plan_path=self.evaluation_plan,
        install_receipt_path=self.install_receipt,
        contract_path=self.contract,
        plist_path=self.plist,
        failure_output_root=self.failure_root,
        _command_runner=runner,
    )
    self.assertEqual(runner.argv[1], (
        "/bin/launchctl", "bootout",
        "gui/501/local.crypto-quant.challenger-forward",
    ))
    self.assertEqual(summary["status"], "FAILED_COHORT_DECOMMISSIONED_VERIFIED")
```

- [ ] **Step 2: Define command result and fixed state machine**

```python
@dataclass(frozen=True)
class DecommissionCommandResult:
    returncode: int
    stdout: bytes
    stderr: bytes

_PRINT_ARGV = ("/bin/launchctl", "print", "gui/501/local.crypto-quant.challenger-forward")
_BOOTOUT_ARGV = ("/bin/launchctl", "bootout", "gui/501/local.crypto-quant.challenger-forward")
```

Default runner uses `subprocess.run(argv, shell=False, env={"PATH":"/usr/bin:/bin:/usr/sbin:/sbin"}, capture_output=True, timeout=10, check=False)`.

- [ ] **Step 3: Implement decommission preflight**

Load the failure receipt; derive all runtime paths; require current snapshot equals its `evidence_after`; execute fixed print and require not running/last exit 1; require replacement/System Paper service labels absent from the frozen plist and current launchd domain; record a second immediate snapshot before bootout and compare.

- [ ] **Step 4: Implement bootout, postcondition and receipt**

Call `_BOOTOUT_ARGV` exactly once. Then call `_PRINT_ARGV`; accept only return
code 113, empty stdout, and the exact two-line fixed-service not-found stderr
confirmed by the read-only sentinel probe on this host; reject any other result
or still-loaded output. Re-snapshot every preserved file/inventory and require
equality. Build a canonical receipt binding failure receipt file SHA-256,
before/bootout/after command evidence, preserved snapshot and:

```python
"eligibility": {
    "old_cohort": "PERMANENTLY_INELIGIBLE_CONTINUITY_GAP",
    "service": "DECOMMISSIONED",
    "replacement_cohort": "NOT_STARTED",
    "system_paper": "NOT_STARTED",
    "canary": "NOT_AUTHORIZED",
}
```

- [ ] **Step 5: Implement semantic loader and CLI**

Loader validates Schema, canonical bytes, self-hash, fixed service/argv, failure receipt binding, before/after file equality, successful bootout evidence and no replacement start. CLI exposes only failure receipt, plans/install chain and output root paths; no command/service/force/delete override.

- [ ] **Step 6: Add fail-closed tests**

Test invalid/mutated receipt, changed source hash, service running, wrong last exit, replacement service present, wrong bootout argv, bootout nonzero, service still loaded, file mutation after bootout, extra command, shell usage, delete attempt, output conflict and loader tamper. Every preflight failure asserts bootout call count 0.

- [ ] **Step 7: Extend exact release tests for decommission receipt**

Require fixed filename `challenger-cohort-decommission-receipt-v0.54.0.json`, runtime/Git byte equality, loader replay, idempotency, conflict and rollback.

- [ ] **Step 8: Run tests and commit**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_cohort_decommission tests.test_challenger_cohort_failure_release -v
PYTHONPATH=src python3 -m unittest tests.test_challenger_launchd_install tests.test_challenger_cohort_evidence_maintenance_install -v
git add src/crypto_quant/challenger_cohort_decommission.py src/crypto_quant/challenger_cohort_decommission_cli.py src/crypto_quant/challenger_cohort_failure_release.py src/crypto_quant/challenger_cohort_failure_release_cli.py src/crypto_quant/schemas/challenger-cohort-decommission-receipt-v1.schema.json config/challenger-cohort-decommission-receipt-v1.schema.json tests/test_challenger_cohort_decommission.py tests/test_challenger_cohort_failure_release.py
git commit -m "feat: decommission failed challenger cohort"
```

### Task 4: Real failure receipt and controlled runtime decommission

**Files:**
- Create at runtime: owner-only failure and decommission receipts under the fixed runtime root.
- Create in Git: the two fixed v0.54 artifact paths.

**Interfaces:**
- Consumes: Tasks 1–3 production CLIs/loaders and exact current runtime evidence.
- Produces: exact runtime/Git failure and decommission receipts; old service unloaded; all evidence bytes preserved.

- [ ] **Step 1: Read-only preflight and before hashes**

Record system UTC/local time, branch/HEAD, `main/origin/main/v0.53.0`, GitHub private repo/ADMIN permission, service print, state/WAL/SHM/log/bundle stat and SHA-256. Assert the state hash is `0052d799b4ab0cd31edf48fc1ba5d4f414c68998b78a31f9a66b46c2d94e35c7` and stderr hash is `5ded25390b412835a98a1d25adda4a6ab97af3486d405199710e12a6d0bb67a5` before publishing.

- [ ] **Step 2: Run the failure observer exactly once**

Use the production CLI with only the five frozen source paths and fixed failure output root. Require `COHORT_MISSED_SLOT_FAILURE_VERIFIED`, one launchctl print, one-or-more byte-identical canonical missed-slot stderr lines with exact count, all network/Broker/order/state-write/Runner/maintenance counters zero, and no runtime file changes.

- [ ] **Step 3: Replay runtime failure receipt and publish exact Git bytes**

Use the production loader, record size/stat/SHA-256, then use release CLI to create the fixed Git artifact. Require `cmp` success and identical SHA-256; repeat loader on Git artifact.

- [ ] **Step 4: Run decommission preflight and operation**

Immediately before bootout, verify the runtime failure receipt again and compare all source hashes. Run the decommission CLI once. Require `FAILED_COHORT_DECOMMISSIONED_VERIFIED`, fixed bootout count 1, service absent, source hashes unchanged and no replacement service.

- [ ] **Step 5: Replay and release decommission receipt**

Production-load runtime receipt, exact-release to the fixed Git artifact, require `cmp` and SHA-256 equality, then load the Git artifact. Never rerun bootout to obtain a different receipt.

- [ ] **Step 6: Commit exact runtime evidence**

```bash
git add artifacts/challenger-forward/challenger-cohort-missed-slot-failure-receipt-v0.54.0.json artifacts/challenger-forward/challenger-cohort-decommission-receipt-v0.54.0.json
git commit -m "feat: seal challenger cohort failure evidence"
```

### Task 5: v0.54 release metadata, full verification and GitHub delivery

**Files:**
- Create: `docs/adr/0054-challenger-cohort-missed-slot-failure-evidence.md`
- Create: `docs/implementation-status-v0.54.0.md`
- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `src/crypto_quant_core.egg-info/PKG-INFO`
- Modify: `src/crypto_quant/build.py`
- Modify: `config/evaluator-build-v1.json`

**Interfaces:**
- Consumes: implementation, exact runtime artifacts and all focused test evidence.
- Produces: package `0.54.0`, deterministic build, Draft PR, merged main and annotated `v0.54.0`.

- [ ] **Step 1: Add committed-artifact regression tests**

Tests load both Git artifacts with production loaders, validate exact canonical bytes/Schemas/self-hashes, assert failure/decommission identities and verify the source snapshots match the committed hashes. Tests must not depend on current launchd state.

- [ ] **Step 2: Write ADR and implementation status**

ADR records the permanent missed slot, rejection of backfill, receipt-first decommission, preserved evidence and deferred replacement. Status records exact runtime paths, receipt ids/hashes/file SHA-256/sizes, fixed bootout evidence, service absent, runtime/Git `cmp`, focused/full tests and explicit non-profitability/non-Paper warnings.

- [ ] **Step 3: Update README and versions**

Set package version to `0.54.0`; document that the old cohort failed and is decommissioned, System Paper remains not started, replacement is separately gated, and `production_activation.enabled=false`. Add both schemas/modules/artifacts to deterministic evaluator build inputs and regenerate the manifest.

- [ ] **Step 4: Run focused, adjacent and full verification**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_cohort_failure tests.test_challenger_cohort_decommission tests.test_challenger_cohort_failure_release -v
PYTHONPATH=src python3 -m unittest tests.test_challenger_cohort_cumulative_evaluation tests.test_challenger_cohort_episode_receipt tests.test_challenger_forward_runner tests.test_challenger_launchd_install -v
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m compileall -q src tests scripts
make validate
```

Expected: all tests and technical validators pass; release policy remains deliberately disabled.

- [ ] **Step 5: Commit release metadata**

```bash
git add README.md docs/adr/0054-challenger-cohort-missed-slot-failure-evidence.md docs/implementation-status-v0.54.0.md pyproject.toml src/crypto_quant_core.egg-info/PKG-INFO src/crypto_quant/build.py config/evaluator-build-v1.json tests
git commit -m "feat: prepare v0.54 failure evidence release"
```

- [ ] **Step 6: Review before publish**

Use `superpowers:requesting-code-review`; resolve all findings. Then use `superpowers:verification-before-completion` and rerun the full verification commands from Step 4 from a clean worktree.

- [ ] **Step 7: Publish through GitHub**

Use `github:yeet`: verify target private repository, origin, ADMIN permission and clean intended scope; push `codex/v0.54-readiness-and-failure-evidence`; create a Draft PR to `main`; wait for PR CI. Merge only after green CI, wait for main CI, then create annotated tag `v0.54.0` exactly at merged main and push the tag. Re-read remote main and tag identities after publication.
