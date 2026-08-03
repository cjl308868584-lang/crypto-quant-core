# System Paper Deployment Review Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every v0.58 independent-review finding while preserving a code-only, credential-free, non-running release.

**Architecture:** Replace RunAtLoad activation with calendar-only activation; isolate immutable publication and launchctl parsing into focused modules; make production loaders command-free; and make the permanent start-receipt loader reconstruct the first natural slot from append-only runtime evidence. Each safety boundary receives an independent red regression before implementation.

**Tech Stack:** Python 3.9 standard library, SQLite WAL, `jsonschema`, macOS launchd contracts, `unittest`, canonical JSON and SHA-256.

## Global Constraints

- Work only in `/Users/chenm4/Documents/虚拟货币/.worktrees/v0.58-system-paper-deployment` on `codex/v0.58-system-paper-deployment`.
- Base review finding set is frozen in `docs/superpowers/specs/2026-08-04-system-paper-deployment-review-hardening-design.md`.
- Use `/usr/bin/python3`, `PYTHONPATH=src`, `apply_patch`, TDD and one focused commit per task.
- Do not render a production contract, run real preflight/install/bootstrap/runtime, create a production receipt, perform a market request, read a secret value, invoke Broker/order, or write strategy state.
- `production_activation.enabled=false` remains unchanged.
- No PR, merge or tag until focused, adjacent, full, compileall, build-manifest, `make validate`, ranged diff check and independent re-review all pass.

---

### Task 1: Owner-only no-overwrite publisher

**Files:**
- Create: `src/crypto_quant/system_paper_evidence.py`
- Create: `tests/test_system_paper_evidence.py`
- Modify: `src/crypto_quant/system_paper_launchd.py`
- Modify: `src/crypto_quant/system_paper_preflight.py`
- Modify: `src/crypto_quant/system_paper_install.py`
- Modify: `src/crypto_quant/system_paper_start_receipt.py`

**Interfaces:**
- Produces: `publish_owner_exact(path: Path, data: bytes) -> None` and `SystemPaperEvidenceError(reason_code)`.
- Contract: target parent already exists, is current-owner exact `0700`; target is current-owner exact `0600`, regular, one-link, exact bytes or is created without replacement.

- [ ] **Step 1: Write red race and unsafe-existing tests**

Add tests that inject a before-link hook which creates different destination bytes, then assert `SYSTEM_PAPER_EVIDENCE_PUBLISH_CONFLICT` and unchanged concurrent bytes. Add exact existing idempotency plus symlink, hardlink, wrong mode, wrong owner-probe and parent-replacement cases.

- [ ] **Step 2: Run red tests**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_system_paper_evidence -v
```

Expected: import/function failures or the raced target is overwritten.

- [ ] **Step 3: Implement the fail-sticky dirfd publisher**

Use retained `O_DIRECTORY|O_NOFOLLOW` parent fd and create the final name directly with `O_CREAT|O_EXCL|O_NOFOLLOW`. Fully write/fsync/close, fsync the directory, then replay pathname attachment and exact bytes. Never create a temporary pathname and never unlink or replace any public or private name. A failed write is deliberately fail-sticky: retain partial bytes as forensic evidence and reject all non-exact retries. On `FileExistsError`, open the final name through the retained fd and compare stat plus exact bytes; never chmod or replace an existing target. This replaces the initially planned temp/link/unlink protocol after independent review proved its source and cleanup pathname TOCTOU.

- [ ] **Step 4: Replace all four v0.58 call-site imports**

Contract/plist, preflight receipt, install receipt and start receipt must call `publish_owner_exact`; translate `SystemPaperEvidenceError` into their frozen component conflict reason.

- [ ] **Step 5: Run focused and call-site tests**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_system_paper_evidence tests.test_system_paper_launchd \
  tests.test_system_paper_preflight tests.test_system_paper_install \
  tests.test_system_paper_start_receipt -q
```

- [ ] **Step 6: Commit**

```bash
git add src/crypto_quant/system_paper_evidence.py tests/test_system_paper_evidence.py \
  src/crypto_quant/system_paper_launchd.py src/crypto_quant/system_paper_preflight.py \
  src/crypto_quant/system_paper_install.py src/crypto_quant/system_paper_start_receipt.py
git commit -m "fix: publish system paper evidence without overwrite"
```

### Task 2: Calendar-only activation and pure contract loader

**Files:**
- Modify: `src/crypto_quant/system_paper_launchd.py`
- Modify: `src/crypto_quant/system_paper_install.py`
- Modify: `config/system-paper-launchd-contract-v1.schema.json`
- Modify: `src/crypto_quant/schemas/system-paper-launchd-contract-v1.schema.json`
- Modify: `tests/test_system_paper_launchd.py`
- Modify: `tests/test_system_paper_install.py`

**Interfaces:**
- Contract cadence: `run_at_load == false` and plist `RunAtLoad == false`.
- Contract `python_identity`: exact `path`, `device`, `inode`, `mode`, `owner_uid`, `link_count`, `size_bytes`, `sha256`, `sys_version`, `package_version`, `requirements_lock_sha256`.
- `load_system_paper_launchd_contract(...)` performs zero commands; renderer remains the only render-time import runner.
- Installer activation is allowed only from UTC-cycle `+00:30:00` through `+03:30:00`, rechecked before any command and immediately before target/bootstrap mutation; outside it fails with zero launchctl/write.

- [ ] **Step 1: Write red activation and command-free loader tests**

Assert `RunAtLoad=false`; a bootstrap fake only records load and cannot invoke runtime; next eligible slot is strictly after install. Add the HH:02→HH:05 regression and both frozen safe-window edges, requiring unsafe cases to stop before launchctl/write. Render a contract with an injected command runner, then load it with a runner that raises on any call and require success. Mutate every Python identity field separately and require rejection.

- [ ] **Step 2: Run red tests**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_system_paper_launchd -v
```

Expected: old `RunAtLoad=true`, missing `python_identity`, or hidden loader import fails.

- [ ] **Step 3: Implement activation and Python identity binding**

Change plist/contract constants to false. Capture executable bytes and stat before/after render-time `python -c`; run `python -c` once for JSON containing `sys.version` and imported package version; bind `requirements.lock` SHA-256. Remove `_verify_snapshot_import` from the loader and leave `_verify_snapshot` plus exact Python file stat/hash verification.

Implement the frozen UTC activation-window predicate in the installer. Validate it once after source loading but before the first launchctl print and again immediately before target/bootstrap mutation; bind `installed_at` to the second check and replay the predicate in the receipt loader. Do not sleep, reschedule, bootstrap, write, or publish failure evidence for an unsafe attempt.

- [ ] **Step 4: Mirror and validate Schema**

```bash
cmp config/system-paper-launchd-contract-v1.schema.json \
  src/crypto_quant/schemas/system-paper-launchd-contract-v1.schema.json
```

- [ ] **Step 5: Run launchd tests and commit**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_system_paper_launchd -q
git add src/crypto_quant/system_paper_launchd.py \
  src/crypto_quant/system_paper_install.py tests/test_system_paper_install.py \
  config/system-paper-launchd-contract-v1.schema.json \
  src/crypto_quant/schemas/system-paper-launchd-contract-v1.schema.json \
  tests/test_system_paper_launchd.py
git commit -m "fix: order system paper activation after install evidence"
```

### Task 3: Stable preflight and measured credential absence

**Files:**
- Modify: `src/crypto_quant/system_paper_preflight.py`
- Modify: `config/system-paper-preflight-receipt-v1.schema.json`
- Modify: `src/crypto_quant/schemas/system-paper-preflight-receipt-v1.schema.json`
- Modify: `tests/test_system_paper_preflight.py`

**Interfaces:**
- New injectable `credential_probe(home: Path, runtime_root: Path) -> Mapping[str, Sequence[str]]` returns `environment_names` and `file_paths`, never values.
- Preflight command runner explicitly performs one snapshot import/version check; receipt loader performs zero commands.
- Loader filesystem rule compares device/filesystem/is_local and current free space threshold, not exact `free_bytes`.

- [ ] **Step 1: Add red drift, credential and command-count tests**

Publish with 10 GiB and load with 9 GiB: must pass. Load with less than 5 GiB: must fail. Inject each frozen credential environment/file name: verified status must be impossible and installer-facing writes/launchctl remain zero. Count preflight import commands and loader commands separately.

- [ ] **Step 2: Run red tests**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_system_paper_preflight -v
```

- [ ] **Step 3: Implement stable disk and credential probes**

Default probe checks only the names/paths frozen in the hardening design, records names not values, and does not open credential files. Update receipt security evidence and reasons. Forward the explicit command runner into preflight import verification and keep the production loader command-free.

- [ ] **Step 4: Mirror Schema, run adjacent tests and commit**

```bash
cmp config/system-paper-preflight-receipt-v1.schema.json \
  src/crypto_quant/schemas/system-paper-preflight-receipt-v1.schema.json
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_system_paper_launchd tests.test_system_paper_preflight \
  tests.test_system_paper_install -q
git add src/crypto_quant/system_paper_preflight.py \
  config/system-paper-preflight-receipt-v1.schema.json \
  src/crypto_quant/schemas/system-paper-preflight-receipt-v1.schema.json \
  tests/test_system_paper_preflight.py
git commit -m "fix: make system paper preflight replay stable"
```

### Task 4: Structured launchctl authority and installer forensics

**Files:**
- Create: `src/crypto_quant/system_paper_launchctl.py`
- Create: `tests/fixtures/launchctl/system-paper-not-running.txt`
- Create: `tests/fixtures/launchctl/system-paper-first-success.txt`
- Create: `tests/test_system_paper_launchctl.py`
- Modify: `src/crypto_quant/system_paper_install.py`
- Modify: `config/system-paper-install-receipt-v1.schema.json`
- Modify: `src/crypto_quant/schemas/system-paper-install-receipt-v1.schema.json`
- Modify: `tests/test_system_paper_install.py`

**Interfaces:**
- `parse_system_paper_launchctl_print(data: bytes) -> Mapping[str, Any]` returns exact label/path/program/arguments/working_directory/environment/runs/state/last_exit_status.
- Install receipts have `installation_status` in `INSTALLED_AND_LOADED` or `LOADED_VERIFICATION_FAILED`; only the first is valid authority for downstream loaders.

- [ ] **Step 1: Capture bounded realistic fixtures and red parser tests**

Use sanitized macOS `launchctl print` grammar. Tests must reject displaced values, duplicate named fields, reordered/missing arguments, extra environment, invalid integer fields, oversized/non-UTF-8 output and comment-like substring injection.

- [ ] **Step 2: Write red target mutation and forensic tests**

Have bootstrap mutate/replace the target before post-print and assert failure with no success receipt. For successful bootstrap plus failed post-print, assert one immutable forensic receipt with all three command evidence records and preserved loaded target.

- [ ] **Step 3: Run red tests**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_system_paper_launchctl tests.test_system_paper_install -v
```

- [ ] **Step 4: Implement parser, retained identity and failure receipt**

Retain target/parent descriptors through bootstrap; compare device/inode/mode/owner/link/size/hash and exact source bytes after post-print. Replace substring checks with parsed-field equality. On post-print failure publish `LOADED_VERIFICATION_FAILED` before raising. Compare every target field, including device, in receipt replay.

- [ ] **Step 5: Mirror Schema, run focused tests and commit**

```bash
cmp config/system-paper-install-receipt-v1.schema.json \
  src/crypto_quant/schemas/system-paper-install-receipt-v1.schema.json
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_system_paper_launchctl tests.test_system_paper_install -q
git add src/crypto_quant/system_paper_launchctl.py tests/fixtures/launchctl \
  tests/test_system_paper_launchctl.py src/crypto_quant/system_paper_install.py \
  config/system-paper-install-receipt-v1.schema.json \
  src/crypto_quant/schemas/system-paper-install-receipt-v1.schema.json \
  tests/test_system_paper_install.py
git commit -m "fix: bind system paper install to launchd authority"
```

### Task 5: Exactly-one-command first-slot observer

**Files:**
- Modify: `src/crypto_quant/system_paper_observer.py`
- Modify: `tests/test_system_paper_observer.py`

**Interfaces:**
- Observer uses validated contract returned by a pure loader, never raw-reloads the path.
- Exactly one injected/default launchctl print is allowed; all other command/network/runtime/state-write counts remain zero.
- Observation includes bounded base64 launchctl stdout/stderr for permanent pure replay.

- [ ] **Step 1: Add red raw-read race, hidden-command and raw-output tests**

Make a contract pathname swap possible only at the old raw read and require the observer to remain bound to the validated object. Install a command runner that fails on any Python/Git call and count exactly one launchctl call. Require raw bytes to round-trip and semantic parser fields to match.

- [ ] **Step 2: Run red observer tests**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_system_paper_observer -v
```

- [ ] **Step 3: Implement single-source contract and launchctl evidence**

Load contract once through the pure loader, retain its source descriptor, parse launchctl through Task 4, and store bounded base64 bytes plus SHA-256 in the observation. Update exact observation key checks used by start receipt.

- [ ] **Step 4: Run adjacent tests and commit**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_system_paper_install tests.test_system_paper_observer -q
git add src/crypto_quant/system_paper_observer.py tests/test_system_paper_observer.py
git commit -m "fix: keep system paper observation command bounded"
```

### Task 6: Persistent semantic start-receipt replay

**Files:**
- Modify: `src/crypto_quant/system_paper_observer.py`
- Modify: `src/crypto_quant/system_paper_start_receipt.py`
- Modify: `config/system-paper-start-receipt-v1.schema.json`
- Modify: `src/crypto_quant/schemas/system-paper-start-receipt-v1.schema.json`
- Modify: `tests/test_system_paper_start_receipt.py`

**Interfaces:**
- New pure `replay_system_paper_first_slot_evidence(...) -> Mapping[str, Any]` reconstructs the immutable first-slot projection from current append-only state/WAL, JSONL log prefix, first artifact/source bundle and stored launchctl bytes.
- Start loader accepts later append-only slot/log growth but rejects source identity replacement, first-prefix mutation or any coordinated receipt rehash.
- Receipt size is `1..4 MiB` before read/JSON parse.

- [ ] **Step 1: Add red coordinated-forgery and append-growth tests**

Publish a valid receipt, mutate each of event-chain hash, prepared hashes, runner summary, first eligible slot, terminal count and launchd semantics in both embedded copies, recompute self-hash, and require loader rejection. Then append a valid second scheduler slot and stdout JSONL line and require the original receipt to load. Add sparse file above 4 MiB and require pre-parse rejection.

- [ ] **Step 2: Run red tests**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_system_paper_start_receipt -v
```

- [ ] **Step 3: Factor pure prefix replay**

Copy current SQLite/WAL to a temporary owner-only directory, use scheduler replay, locate the first `SUCCEEDED`, compute chain hash at its exact terminal event, bind prepared input/result and artifact bytes, parse the first matching stdout JSONL summary, require empty stderr, and parse stored launchctl raw bytes. Compare reconstructed immutable fields exactly with the receipt; current trailing events/log lines must not alter the first prefix.

- [ ] **Step 4: Harden evolving-file identity**

For state/WAL/stdout require original device/inode/owner/mode/link identity and append-only semantic prefix, not frozen size/mtime/hash. Continue exact stat/hash checks for contract/plist/preflight/install target/source bundle/first artifact. Reject missing/replaced files.

- [ ] **Step 5: Mirror Schema, run System Paper suite and commit**

```bash
cmp config/system-paper-start-receipt-v1.schema.json \
  src/crypto_quant/schemas/system-paper-start-receipt-v1.schema.json
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -p 'test_system_paper*.py' -q
git add src/crypto_quant/system_paper_observer.py \
  src/crypto_quant/system_paper_start_receipt.py \
  config/system-paper-start-receipt-v1.schema.json \
  src/crypto_quant/schemas/system-paper-start-receipt-v1.schema.json \
  tests/test_system_paper_start_receipt.py
git commit -m "fix: replay system paper start evidence semantically"
```

### Task 7: Build identity and truthful review record

**Files:**
- Modify: `src/crypto_quant/build.py`
- Modify: `tests/test_estimators.py`
- Modify: `config/evaluator-build-manifest-v1.json`
- Modify: `docs/superpowers/specs/2026-08-03-system-paper-deployment-trust-chain-design.md`
- Modify: `docs/superpowers/plans/2026-08-03-system-paper-deployment-trust-chain.md`
- Modify: `docs/adr/0058-system-paper-deployment-trust-chain.md`
- Modify: `docs/implementation-status-v0.58.0.md`
- Modify: `README.md`

**Interfaces:**
- Manifest remains package `0.58.0`, manifest `1.52.0`, and includes every new source/test/fixture/hardening spec/plan.

- [ ] **Step 1: Write red build-input assertions**

Require the new evidence module, launchctl parser, tests, both fixtures, hardening design and this plan in `EvaluatorBuild.expected_file_paths`.

- [ ] **Step 2: Run red estimator tests**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_estimators -q
```

- [ ] **Step 3: Update frozen docs and manifest selection**

Mark the old RunAtLoad requirement superseded; record the 4 Critical/6 Important/2 Minor review result and exact closures without claiming install/start. Remove all trailing whitespace in the ranged v0.57 diff. Refresh once after docs settle.

```bash
PYTHONPATH=src /usr/bin/python3 scripts/refresh_evaluator_build_manifest.py
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_estimators -q
```

- [ ] **Step 4: Commit**

```bash
git add src/crypto_quant/build.py tests/test_estimators.py \
  config/evaluator-build-manifest-v1.json \
  docs/superpowers/specs/2026-08-03-system-paper-deployment-trust-chain-design.md \
  docs/superpowers/plans/2026-08-03-system-paper-deployment-trust-chain.md \
  docs/adr/0058-system-paper-deployment-trust-chain.md \
  docs/implementation-status-v0.58.0.md README.md
git commit -m "release: close system paper deployment review"
```

### Task 8: Independent re-review and complete release verification

**Files:**
- Review: every file in `git diff v0.57.0...HEAD`.
- Modify only for a reproduced defect with a new red regression.

**Interfaces:**
- Produces: zero remaining Critical/Important findings, clean local release evidence, then Draft PR/CI/main/annotated tag flow from the original v0.58 plan.

- [ ] **Step 1: Request independent re-review**

Reviewer must explicitly retest C1–C4, I1–I6 and M1–M2 from the first report and compare implementation to the hardening design.

- [ ] **Step 2: Run complete verification**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -q
PYTHONPYCACHEPREFIX=/private/tmp/crypto-quant-v058-pycache \
  PYTHONPATH=src /usr/bin/python3 -m compileall -q src tests scripts
PYTHONPATH=src /usr/bin/python3 scripts/validate_evaluator_build.py
make validate
git diff --check v0.57.0...HEAD
git status --short
```

- [ ] **Step 3: Prove forbidden effects remained zero**

Read-only checks must show `/Users/chenm4/Library/Application Support/CryptoQuant/system-paper-v1` absent, target plist absent and `gui/<uid>/local.crypto-quant.system-paper-v1` not loaded due to this release.

- [ ] **Step 4: Continue Task 10 of the original plan**

Only after re-review and local verification pass: verify private target/origin/ADMIN/main/tag authority, push branch, create Draft PR, wait for Python 3.9/3.12 PR CI, merge exact reviewed head, wait for main CI, create annotated `v0.58.0` at exact remote main and verify the peeled commit.

## Plan Self-Review Record

- Spec coverage: Tasks 1–6 map to all C1–C4, I1–I6 and M1; Task 7 closes M2, frozen docs and build identity; Task 8 repeats the full release gates.
- Placeholder scan: no unresolved marker, unnamed validation or deferred implementation remains.
- Type consistency: `publish_owner_exact`, `parse_system_paper_launchctl_print` and `replay_system_paper_first_slot_evidence` are defined before downstream use.
- Scope: no evaluator, projection, Web, replacement Challenger, install or runtime execution is added.

## Execution Choice

The user has already delegated implementation without further questions. Execute inline in this thread with `superpowers:executing-plans`, using a review checkpoint after every task and no production side effects.
