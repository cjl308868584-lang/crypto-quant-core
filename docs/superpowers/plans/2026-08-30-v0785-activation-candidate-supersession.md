# v0.78.5 Activation Candidate Supersession Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a v0.78.5 activation candidate beside immutable v0.78.3 evidence so the credential-free replacement simulation can be installed without deleting or overwriting history.

**Architecture:** Derive release-scoped candidate and receipt paths from the frozen semantic release tag while retaining shared content-addressed snapshots and the fixed runtime/service identities. Reuse the existing secure directory and exact-publish primitives; do not introduce migration, fallback lookup or generic deployment infrastructure.

**Tech Stack:** Python 3.9, `unittest`, canonical JSON, owner-only descriptor-relative filesystem primitives, GitHub Actions Python 3.9/3.12/macOS arm64.

**Spec:** `docs/superpowers/specs/2026-08-30-v0785-activation-candidate-supersession-design.md`

## Global Constraints

- Old v0.78.3 candidate, snapshot and failed receipt bytes are immutable.
- No renderer/preflight/installer/service/runtime action occurs during the code release.
- No credential, account, Broker, order or fund access.
- No strategy, runtime state machine, scheduler, UI or private adapter change.
- One final local full suite only; no duplicate whole-branch review without code changes.

---

### Task 1: Release-scoped activation candidate paths

**Files:**
- Modify: `src/crypto_quant/challenger_replacement_v3_activation_trust.py`
- Modify: `src/crypto_quant/challenger_replacement_install_trust.py`
- Modify: `tests/test_challenger_replacement_v3_activation_trust.py`
- Modify: `tests/test_challenger_replacement_v3_activation_preflight.py`
- Modify: `tests/test_challenger_replacement_v3_activation_install.py`

**Interfaces:**
- Consumes: `activation_paths()`, `_ensure_fixed_snapshot_directories(paths)`, `_publish_contract_exact(...)`.
- Produces: deterministic release-scoped contract/plist/preflight/install paths; unchanged event/start/target/service paths.

- [ ] **Step 1: Write the failing historical-collision test**

  Build a temporary production-root fixture with trusted v0.78.3 candidate
  files at their old fixed names.  Run the real v0.78.5 renderer against the
  fixture and assert it publishes to the four literal v0.78.5 paths while the
  complete stat tuple and bytes of every v0.78.3 sentinel remain identical.

- [ ] **Step 2: Run the test and verify RED**

  Run `python -m unittest tests.test_challenger_replacement_v3_activation_trust -v`.
  The new test must fail because current `activation_paths()` still returns the
  unversioned conflicting names.

- [ ] **Step 3: Implement the minimal path derivation and directory creation**

  Validate the frozen release tag as a semantic tag, use it only as a fixed
  basename suffix, and make `_ensure_fixed_snapshot_directories` create the
  exact direct-child receipt directory basenames supplied in `paths`.  Keep
  snapshot/event/log/start/target paths unchanged.

- [ ] **Step 4: Add conflict and isolation RED/GREEN cases**

  Cover exact rerender, different bytes at a current candidate filename,
  symlink/hardlink/wrong-mode receipt directories, and old failed receipts not
  being scanned as current candidates.  Assert zero target plist, service,
  event and credential side effects.

- [ ] **Step 5: Run focused and adjacent tests**

  Run the activation trust, preflight, install, start, observer, install-trust,
  filesystem-identity and operational-qualification modules.  Commit only when
  all pass and `git diff --check` is clean.

### Task 2: Freeze and release v0.78.5

**Files:**
- Modify: `pyproject.toml`
- Modify: `setup.py`
- Modify: `src/crypto_quant/__init__.py`
- Modify: `src/crypto_quant/build.py`
- Modify: `src/crypto_quant/challenger_replacement_v3_activation_trust.py`
- Modify: `src/crypto_quant/challenger_replacement_v3_activation_preflight.py`
- Modify: activation contract/receipt schemas under `src/crypto_quant/schemas/` and `config/`
- Modify: `config/evaluator-build-manifest-v1.json`
- Modify: `scripts/refresh_evaluator_build_manifest.py`
- Create: `tests/test_challenger_replacement_v0785_release.py`
- Create: `docs/adr/0083-v0785-activation-candidate-supersession.md`
- Create: `docs/implementation-status-v0.78.5.md`
- Modify: `README.md`
- Modify: `docs/runbooks/challenger-replacement-v3-simulation-activation.md`
- Modify: existing release assertions that intentionally track the current package/manifest.

**Interfaces:**
- Consumes: green Task 1 behavior and repository release validation.
- Produces: package `0.78.5`, manifest `1.77.0`, exact release/tag/runbook identity.

- [ ] **Step 1: Write v0.78.5 release RED tests**

  Assert package `0.78.5`, manifest `1.77.0`, matching schema constants,
  release-scoped path literals, required ADR/status/runbook files and build
  inventory coverage.  Run the new test and verify it fails on v0.78.4.

- [ ] **Step 2: Apply the smallest release metadata update**

  Update exact release constants and existing current-version assertions.  Add
  ADR/status text that records the observed v0.78.4 conflict and explicitly
  forbids deleting old evidence.  Refresh the manifest through the existing
  deterministic script.

- [ ] **Step 3: Verify the final local candidate once**

  Run focused/adjacent tests, the complete suite once, `python -m compileall -q
  src tests`, `make validate`, `git diff --check`, and scans for placeholders
  and unintended credential/private execution changes.

- [ ] **Step 4: Independent review and release**

  Obtain one independent complete review; clear all Critical/Important
  findings with targeted re-review.  Push a public branch, create a PR, verify
  Python 3.9/3.12/macOS arm64 PR CI, merge, verify merged-main CI, create an
  annotated `v0.78.5` tag at exact main, and verify peeled commit and tag object.

- [ ] **Step 5: Execute the already-authorized external ceremony**

  From a clean detached exact-tag worktree, run renderer, wait for the frozen
  preflight window, run no-argument preflight and strict replay, then the
  bootstrap-only installer.  Never kickstart or directly invoke runtime.  Wait
  for the first natural opportunity, run read-only observer/start publication,
  and report exact receipt hashes and zero private authority counts.
