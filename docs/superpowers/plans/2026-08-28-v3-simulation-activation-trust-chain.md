# Replacement v3 Minimal Simulation Activation Trust Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make v0.78 the final code release needed to install the credential-free replacement public simulation and start its real 72-hour clock from a natural observed opportunity.

**Architecture:** Thin v3 wrappers reuse v0.68 secure deployment primitives and v0.76 runtime/observer/start logic. No System Paper dependency, no v0.79 split, no private Binance path, and no generic infrastructure.

**Tech Stack:** Python 3.9+, standard library, jsonschema, launchd, canonical JSON, retained dirfd/no-follow I/O, unittest.

**Spec:** `docs/superpowers/specs/2026-08-28-v3-simulation-activation-trust-chain-design.md`

## Global Constraints

- Base: annotated `v0.77.0`, peeled `39a973d51bdc8fc957a65052f4bb5f310a1f72c3`.
- v0.78 contains all render/preflight/install/natural-start/start-receipt code; no v0.79 split.
- Release phase performs zero production writes, network, launchctl mutation, runtime invocation, credentials, accounts, private requests, orders or funds.
- System Paper/540-slot/90-day activation is independent and cannot block replacement 72 hours.
- Reuse existing private safety primitives; do not copy or generalize them.
- Production Python `<1500` lines, target `<=1200`; five tasks total.
- TDD per task; one final full suite on unchanged final code state.

---

### Task 1: Contract, minimal snapshot and installed adapter

**Files:**
- Create: `src/crypto_quant/challenger_replacement_v3_activation_trust.py`
- Create: `src/crypto_quant/challenger_replacement_v3_activation_trust_cli.py`
- Create: `src/crypto_quant/challenger_replacement_v3_installed_runtime.py`
- Create: `src/crypto_quant/schemas/challenger-replacement-v3-install-contract-v1.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-v3-activation-preflight-v1.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-v3-activation-install-receipt-v1.schema.json`
- Create: the same three basenames as exact `config/` mirrors
- Create: `tests/test_challenger_replacement_v3_activation_trust.py`
- Create: `tests/test_challenger_replacement_v3_installed_runtime.py`

**Produces:** `render_fixed_v3_activation_candidate()`, `load_fixed_v3_activation_candidate()`, `run_installed_v3_opportunity()`.

- [ ] Write RED tests for exact v0.77/v0.76 identity, schema closure, snapshot inventory `<=256`, private-module exclusion, missing receipt zero authority, and RESULT_PREPARED fresh-process recovery with zero second request.
- [ ] Run:

```bash
PYTHONPATH=src python3 -m unittest -v \
  tests.test_challenger_replacement_v3_activation_trust \
  tests.test_challenger_replacement_v3_installed_runtime
```

Expected: missing-module/schema failures.

- [ ] Implement thin wrappers using `_publish_snapshot_from_inventory`, `_read_published_exact`, `_publish_contract_exact`, `_run_fixed_command`, `replay_replacement_snapshot` and existing event-root capabilities. Do not duplicate write/fsync/no-replace. Candidate plist targets `crypto_quant.challenger_replacement_v3_installed_runtime`.
- [ ] Add subprocess/import tests proving no v0.77 private module is copied/imported and descriptor closes preserve the primary error.
- [ ] Run focused tests plus `tests.test_challenger_replacement_v3_runtime` and `tests.test_challenger_replacement_v3_deployment`; require PASS.
- [ ] Commit all Task 1 files with `git commit -m "feat: bind v3 simulation activation runtime"`.

### Task 2: Minimal fixed preflight

**Files:**
- Create: `src/crypto_quant/challenger_replacement_v3_activation_preflight.py`
- Create: `src/crypto_quant/challenger_replacement_v3_activation_preflight_cli.py`
- Create: `tests/test_challenger_replacement_v3_activation_preflight.py`

**Produces:** `collect_fixed_v3_activation_preflight()` and strict loader.

- [ ] Write RED tests for release/snapshot replay; platform/uid/timezone/disk/inode/pmset; absent service/plist/root; old Challenger stopped; `[10m,30m]`; exactly three public time GET; proxy/redirect disabled; 30-minute expiry; private/account/order/fund zero. Assert no System Paper input.
- [ ] Run focused test; expect missing module.
- [ ] Implement v3 binding around existing command, clock, credential and publication primitives. No retry and no URL/path/time override.
- [ ] Run focused plus historical replacement preflight and public HTTP tests; require PASS.
- [ ] Commit module, CLI and test with `git commit -m "feat: preflight v3 public simulation"`.

### Task 3: Fixed installer and install receipt

**Files:**
- Create: `src/crypto_quant/challenger_replacement_v3_activation_install.py`
- Create: `src/crypto_quant/challenger_replacement_v3_activation_install_cli.py`
- Create: `tests/test_challenger_replacement_v3_activation_install.py`

**Produces:** `install_fixed_v3_simulation_launch_agent()` and strict install receipt loader.

- [ ] Write RED tests for exact `print → plist no-replace → bootstrap → print`, `runs=0`, auto-derived next natural opportunity, expired preflight rejection, and zero kickstart/start/enable/submit/bootout/runtime calls.
- [ ] Add crash tests: before plist means zero mutation/no target; after plist/bootstrap ambiguity preserves target and returns `INSTALL_STATE_UNKNOWN_FAILED_CLOSED`; no unlink/chmod rollback; sentinel unchanged.
- [ ] Run focused test; expect missing module.
- [ ] Implement using existing plist publisher, command wrapper, transcript, preflight loader and receipt publisher; add only v3 identity/status mapping.
- [ ] Run focused plus historical install tests; require PASS.
- [ ] Commit module, CLI and test with `git commit -m "feat: install fixed v3 simulation agent"`.

### Task 4: Natural observer and durable start receipt

**Files:**
- Create: `src/crypto_quant/challenger_replacement_v3_activation_start.py`
- Create: `src/crypto_quant/challenger_replacement_v3_activation_start_cli.py`
- Create: `tests/test_challenger_replacement_v3_activation_start.py`

**Produces:** `observe_fixed_v3_first_opportunity()` and `publish_fixed_v3_start_receipt()`.

- [ ] Write RED tests for waiting, flat first MISSED then later OBSERVED, exposed miss/hard failure, exact dual clocks, no caller time/slot/path, idempotent replay, fsync failure, source replacement, no pre-tail economics.
- [ ] Run focused test; expect missing composition module.
- [ ] Implement by calling fixed v0.76 observer and v3 start builder, adding only install-receipt binding and exact publication. Reuse existing publisher; do not create another observer engine.
- [ ] Run focused plus v3 observer/start/qualifier/evaluator tests; require PASS.
- [ ] Commit module, CLI and test with `git commit -m "feat: start v3 simulation from natural evidence"`.

### Task 5: Static authority, release and immutable publication

**Files:**
- Create: `tests/test_challenger_replacement_v078_architecture.py`
- Create: `tests/test_challenger_replacement_v078_release.py`
- Create: `docs/runbooks/challenger-replacement-v3-simulation-activation.md`
- Create: `docs/adr/0078-v3-simulation-activation-trust-chain.md`
- Create: `docs/implementation-status-v0.78.0.md`
- Modify: `README.md`, `pyproject.toml`, `src/crypto_quant/__init__.py`, `config/evaluator-build-manifest-v1.json`

- [ ] Write RED tests for exact production-file inventory/line budget, no forbidden imports/override parameters, schemas packaged/mirrored, v0.77 tag identity, version `0.78.0`, manifest `1.72.0`, production absence.
- [ ] Write one future external ceremony runbook: fixed renderer, preflight, installer, no kickstart, natural windows, observer/start receipt, incident preservation. State System Paper non-blocking and no v0.79.
- [ ] Bump package/status/ADR and refresh manifest once. Run all v0.78 focused/adjacent tests, compileall and diff-check.
- [ ] Run one independent complete review; clear Critical/Important with targeted RED→GREEN only.
- [ ] Run the one final full suite and `make validate`; do not repeat on unchanged code.
- [ ] Commit release candidate; Draft PR; require Python 3.9/3.12/macOS arm64 PR CI; merge; require main CI; create annotated `v0.78.0` at exact main and verify tag object/peel.
- [ ] Report exact identities/test totals/production absence. Next is the single external no-credential installation/start ceremony, at most one natural four-hour wait, then real 72 hours; do not create v0.79.
