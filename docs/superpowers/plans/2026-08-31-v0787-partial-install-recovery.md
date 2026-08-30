# v0.78.7 Partial-Install Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a fail-closed v0.78.7 recovery protocol that preserves the exact v0.78.5 partial-install evidence and gates any later install behind a strictly replayable recovery receipt and a new target plist path.

**Architecture:** A checked-in canonical recovery plan freezes the v0.78.5 incident and v0.78.6 release identity.  A replacement-specific read-only verifier replays that plan, observes two disabled/unloaded services and a paused automation, and publishes one immutable receipt through the existing exact publisher.  The existing v3 installer accepts only a fully revalidated receipt and writes only the new release-scoped target during a separately authorized future ceremony.

**Tech Stack:** Python 3.9, `unittest`, JSON Schema 2020-12, canonical JSON, descriptor-relative POSIX I/O, macOS `launchctl`, GitHub Actions Python 3.9/3.12/macOS arm64.

**Spec:** `docs/superpowers/specs/2026-08-31-v0787-partial-install-recovery-design.md`

## Global Constraints

- Never write, chmod, rename, unlink, move or replace the v0.78.5 target, receipts, contract, candidate, snapshot, event/start/log roots or predecessor plist.
- Never run renderer, preflight, installer, bootstrap, enable, kickstart, start, runtime or automation resume while implementing or releasing v0.78.7.
- Never read credentials or private accounts and never call a Broker, submit/cancel an order or move funds.
- Recovery paths and OS commands are fixed; production APIs accept no arbitrary path, command or fault callback.
- The new target is `/Users/chenm4/Library/LaunchAgents/local.crypto-quant.challenger-replacement-v1-v0.78.7.plist`.
- The service label stays `local.crypto-quant.challenger-replacement-v1`; both it and `local.crypto-quant.challenger-forward` must be disabled and unloaded.
- Filesystem device, inode, `mtime_ns` and `ctime_ns` are strict unsigned decimal strings where stored in canonical JSON.
- One final local full suite only.  Fix review findings with focused tests and targeted re-review.
- v0.78.7 is the only recovery release; do not create or defer required behavior to v0.78.8.

---

### Task 1: Frozen incident plan and strict loader

**Files:**
- Create: `src/crypto_quant/schemas/challenger-replacement-v3-partial-install-recovery-plan-v1.schema.json`
- Create: `config/challenger-replacement-v3-partial-install-recovery-v0.78.7.json`
- Create: `src/crypto_quant/challenger_replacement_v3_partial_install_recovery.py`
- Create: `tests/test_challenger_replacement_v3_partial_install_recovery.py`

**Interfaces:**
- Produces: `load_fixed_v3_partial_install_recovery_plan_bytes(data: bytes) -> Mapping[str, Any]` and `load_fixed_v3_partial_install_recovery_plan() -> tuple[Mapping[str, Any], bytes]`.
- The plan binds exact v0.78.5 file/directory records, service/automation requirements, new target path and exact v0.78.6 release identity.

- [ ] **Step 1: Write the plan RED tests**

  Assert closed-schema validation, canonical bytes, plan self-hash/business ID,
  exact v0.78.6 foundation, exact old SHA-256 values, decimal identity fields,
  required empty-root inventories, fixed labels/automation path and literal new
  target.  Mutate one field at a time and assert
  `CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_PLAN_INVALID`.

- [ ] **Step 2: Run RED and record the expected missing-interface failure**

  Run `python -m unittest tests.test_challenger_replacement_v3_partial_install_recovery.PartialInstallRecoveryPlanTests -v`.
  It must fail because the schema, artifact and loader do not exist.

- [ ] **Step 3: Add the minimal schema, artifact and strict loader**

  Implement exact-key JSON Schema validation, canonical-byte equality,
  `stable_id("challenger_replacement_v3_partial_install_recovery_plan", ...)`,
  `artifact_self_hash(..., "plan_hash")`, semantic reconstruction and a fixed
  package-resource schema load.  Keep filesystem records data-only; do not add
  I/O or generic storage abstractions in this task.

- [ ] **Step 4: Run GREEN and commit**

  Run the plan test class, `git diff --check`, and commit the four files as one
  independently reviewable frozen-plan slice.

### Task 2: Read-only preserved-evidence and safety-state verifier

**Files:**
- Modify: `src/crypto_quant/challenger_replacement_v3_partial_install_recovery.py`
- Modify: `tests/test_challenger_replacement_v3_partial_install_recovery.py`

**Interfaces:**
- Produces: `_verify_preserved_partial_install(plan) -> Mapping[str, Any]`, returning only normalized observations for receipt construction.
- Consumes: `_open_directory`, `_read_published_exact`, retained-descriptor attachment checks, bounded no-follow/nonblocking reads and fixed `/bin/launchctl` commands.

- [ ] **Step 1: Add exact-file and no-side-effect RED tests**

  Build owner-only fixture roots with the exact topology.  Prove rejection for
  missing old evidence, same bytes on a new inode, byte/mode/link/size drift,
  `mtime_ns` or `ctime_ns` drift, symlink, hardlink, FIFO, socket and directory
  substitution.  Snapshot every external sentinel's bytes, mode, size, inode,
  link count, mtime and ctime and assert no rejection path changes it.

- [ ] **Step 2: Add directory/state RED tests**

  Prove exact event/start/log empty inventories pass and any file, orphan
  staging, extra directory, replaced root or identity drift fails.  Prove the
  state parent contains only the fixed event directory.  Verify snapshot root
  identity plus the manifest-derived 101-file/3,248,480-byte tree replay.

- [ ] **Step 3: Add fixed-observation RED tests**

  Patch only the existing low-level process boundary.  Require `print-disabled
  gui/501` to contain both exact labels as disabled, and each exact `launchctl
  print gui/501/<label>` to return the fixed absent-service result.  Require the
  fixed automation TOML to contain exactly one `status = "PAUSED"`.  Ambiguous,
  malformed, duplicate, loaded or enabled results must fail with
  `CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_STATE_CONFLICT`.

- [ ] **Step 4: Implement the minimal verifier GREEN**

  Open preserved files read-only with required `O_NOFOLLOW|O_NONBLOCK`, fstat
  before bounded read, compare attachment and the complete frozen record, and
  close every successfully opened descriptor exactly once.  Use retained
  directory descriptors for inventories.  Map all expected I/O to fixed
  evidence/state codes; preserve unexpected primary exceptions over close
  failures.

- [ ] **Step 5: Run focused GREEN and commit**

  Run all verifier and special-object subprocess timeout tests.  Confirm the
  module has no `chmod`, `unlink`, `remove`, `replace`, `rename`, `bootstrap`,
  `kickstart`, credential or Broker operation.  Commit the verifier slice.

### Task 3: Recovery receipt, crash-safe publication and CLI

**Files:**
- Create: `src/crypto_quant/schemas/challenger-replacement-v3-partial-install-recovery-receipt-v1.schema.json`
- Create: `src/crypto_quant/challenger_replacement_v3_partial_install_recovery_cli.py`
- Modify: `src/crypto_quant/challenger_replacement_v3_partial_install_recovery.py`
- Modify: `tests/test_challenger_replacement_v3_partial_install_recovery.py`

**Interfaces:**
- Produces: `build_fixed_v3_partial_install_recovery_receipt(...)`, `load_fixed_v3_partial_install_recovery_receipt_bytes(...)`, `publish_fixed_v3_partial_install_recovery_receipt()`, and a no-argument CLI.
- Consumes: exact plan, verified observations, `load_fixed_published_v3_install_contract()`, and `_publish_contract_exact(...)`.

- [ ] **Step 1: Add receipt codec RED tests**

  Assert the exact status, canonical `.000Z` timestamp, plan/evidence/candidate
  bindings, v0.78.5-to-v0.78.7 supersession relation, all-zero private/runtime
  authority, schema, self-hash, business ID and deterministic rebuild.  Reject
  extra keys, wrong release, altered transcript hash, altered old binding and
  noncanonical bytes.

- [ ] **Step 2: Add publication and retry RED tests**

  Use the real exact publisher in fixture directories.  Cover first publish,
  exact repeat, conflicting final, partial staging, file-fsync failure,
  rename-before-dir-fsync failure, exact retry durability confirmation and two
  real-process same/different receipt races.  Assert one canonical inode and no
  mutation of preserved sentinels.

- [ ] **Step 3: Implement codec and fixed publisher GREEN**

  Revalidate the complete current state immediately before publish and after
  exact replay.  Publish only inside the contract-bound v0.78.7 recovery root.
  Do not expose an arbitrary output path or adopt a different existing file.

- [ ] **Step 4: Implement the no-argument CLI GREEN**

  The CLI prints only canonical receipt/result JSON to stdout, maps fixed
  failures to a nonzero exit, and accepts no flags, environment override or
  production path.  Tests invoke its main function with patched fixed command
  results; they never call real launchctl mutation or installation.

- [ ] **Step 5: Run focused/adjacent GREEN and commit**

  Run recovery tests plus install-trust publisher and filesystem-identity
  tests, `compileall` for the two new modules and `git diff --check`.  Commit.

### Task 4: Release-scoped target and installer recovery gate

**Files:**
- Modify: `src/crypto_quant/challenger_replacement_v3_activation_trust.py`
- Modify: `src/crypto_quant/challenger_replacement_v3_activation_install.py`
- Modify: `src/crypto_quant/challenger_replacement_v3_activation_start.py`
- Modify: activation contract/install/start schemas under `src/crypto_quant/schemas/`
- Modify: `tests/test_challenger_replacement_v3_activation_trust.py`
- Modify: `tests/test_challenger_replacement_v3_activation_preflight.py`
- Modify: `tests/test_challenger_replacement_v3_activation_install.py`
- Modify: `tests/test_challenger_replacement_v3_activation_start.py`

**Interfaces:**
- Produces: v0.78.7 release-scoped contract/candidate/preflight/install/recovery roots and new target path; `_load_fixed_recovery_inputs()` as a mandatory installer prerequisite.
- Consumes: Task 3 strict receipt loader and Task 2 full revalidation.

- [ ] **Step 1: Add path and historical-preservation RED tests**

  Assert all v0.78.7 release-scoped paths and the literal new target.  Seed the
  old target/receipts/candidate/contract/snapshot identities and prove renderer
  fixture behavior never chooses an old path as output and leaves every old
  stat field and byte unchanged.

- [ ] **Step 2: Add mandatory gate RED tests**

  Call the installer with valid contract/preflight fixtures but no recovery
  receipt and assert failure before `_publish_plist` or any launchctl mutation.
  Repeat for malformed, conflicting, stale-state and candidate-mismatched
  receipts.  Prove a valid receipt allows execution to reach the existing
  target-absent check, without executing bootstrap in the test.

- [ ] **Step 3: Add replay/revalidation RED tests**

  After loading a valid receipt, replace one old file with identical bytes on a
  new inode, alter one root timestamp, load either service, unpause automation,
  add an event/log/start file or create the new target.  Each case must fail
  before target publication.  Exact repeated input must select the same
  recovery receipt by its binding, never by "only file in directory" history.

- [ ] **Step 4: Implement the smallest path and gate changes GREEN**

  Add recovery root/plan/new-target keys to `activation_paths()` and the closed
  contract schema.  Load exactly one strict recovery receipt, bind it into the
  v0.78.7 install receipt, and revalidate it before any plist publication and
  during installed-state replay.  Preserve all existing bootstrap-only and
  natural-start semantics.

- [ ] **Step 5: Run activation adjacency GREEN and commit**

  Run trust, preflight, install, start, observer, installed-runtime,
  operational-qualification, events and filesystem-identity tests.  Static
  scan for forbidden old-target writes and mutation commands.  Commit.

### Task 5: Freeze v0.78.7 release identity and documentation

**Files:**
- Modify: `pyproject.toml`
- Modify: `setup.py`
- Modify: `src/crypto_quant/__init__.py`
- Modify: `src/crypto_quant/build.py`
- Modify: `config/evaluator-build-manifest-v1.json`
- Modify: `scripts/refresh_evaluator_build_manifest.py`
- Create: `tests/test_challenger_replacement_v0787_release.py`
- Create: `docs/adr/0085-v0787-partial-install-recovery.md`
- Create: `docs/implementation-status-v0.78.7.md`
- Modify: `README.md`
- Modify: `docs/runbooks/challenger-replacement-v3-simulation-activation.md`
- Modify: current-version assertions and closed schemas intentionally bound to the current release.

**Interfaces:**
- Produces: package `0.78.7`, manifest `1.79.0`, exact release inventory and a runbook that keeps code release separate from later recovery ceremony.

- [ ] **Step 1: Add release RED tests**

  Assert package/manifest versions, both new schemas, plan artifact, recovery
  module/CLI, ADR/status/runbook, v0.78.6 foundation, new target literal,
  preserved-old-evidence wording and zero install/start authority in this
  release.  Run and verify failure on v0.78.6 metadata.

- [ ] **Step 2: Apply minimal metadata and docs GREEN**

  Update only current-release constants and intentional schema bindings.  Add
  ADR/status/runbook sections stating that v0.78.7 is recovery code only and
  listing the exact later ceremony order: renderer, recovery qualification,
  preflight, bootstrap-only installer, natural opportunity, observer/start
  receipt.  Refresh the manifest with the existing deterministic script.

- [ ] **Step 3: Run focused release GREEN and commit**

  Run the v0.78.7 release test and adjacent release/manifest tests.  Ensure the
  manifest covers every new file and `git diff --check` is clean.  Commit.

### Task 6: Final verification, independent review and public release

**Files:**
- Modify only files needed to resolve verified Critical/Important review findings.

**Interfaces:**
- Produces: one reviewed exact v0.78.7 commit, public PR, merged main, green CI and annotated tag.

- [ ] **Step 1: Run the final local candidate once**

  Run focused and adjacent recovery/activation tests, then exactly one complete
  `python -m unittest discover -s tests -v`, `python -m compileall -q src tests`,
  `make validate`, `git diff --check`, placeholder scans and forbidden-operation
  scans.  Record exact counts and commit identity.

- [ ] **Step 2: Obtain one independent complete review**

  Give a read-only reviewer the spec, plan, base/final commits and explicit
  scope.  Clear all Critical/Important findings through TDD and run only
  affected tests plus targeted re-review.  Do not rerun the unchanged full
  suite.

- [ ] **Step 3: Verify old production evidence still matches the frozen plan**

  Perform read-only stat/hash/inventory checks of every preserved real object,
  both disabled/unloaded services and the paused automation.  Compare against
  the pre-work values.  Do not invoke any new recovery CLI or activation
  command.

- [ ] **Step 4: Publish the code release**

  Verify the public target repository, `origin`, exact branch head and write
  authority.  Push branch, open PR, wait for Python 3.9/3.12/macOS arm64 CI,
  merge exact reviewed head, wait for main CI, create annotated `v0.78.7` at
  exact main, and verify peeled commit plus tag object.  Never alter `v0.78.6`.

- [ ] **Step 5: Stop at the external-action boundary**

  Report commit/tag/CI/test evidence and unchanged old evidence.  Provide one
  copyable authorization text for the later exact v0.78.7 renderer → recovery
  receipt → preflight → bootstrap-only install → natural-start ceremony.  Do
  not execute that ceremony in this task.
