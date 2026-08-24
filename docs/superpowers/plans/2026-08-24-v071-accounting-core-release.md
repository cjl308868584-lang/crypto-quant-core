# v0.71 Accounting Core Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the reviewed fixture-only Binance accounting/risk core as v0.71 without representing lifecycle, event integration, Paper, or trading authority as complete.

**Architecture:** Preserve the exact Task 1–4 code checkpoint and add only its canonical contract artifact, release regressions, and honest metadata. Lifecycle and canonical event-log integration move to a separately preregistered v0.72.

**Tech Stack:** Python 3.9/3.12, canonical JSON, `unittest`, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-24-v071-accounting-core-version-split-design.md`

## Global Constraints

- Fixture-only, credential-free, deterministic, and no I/O in the simulation core.
- No install, start, production root, network, account, Broker, order, or funds.
- Candidate status is exactly `CANDIDATE_ACCOUNTING_CORE_LOCAL_VERIFICATION_PENDING`; only the post-verification status is `FIXTURE_ACCOUNTING_CORE_VERIFIED_LIFECYCLE_NOT_IMPLEMENTED`.
- Six-module budget is `(current physical lines - 843) <= 1200`; each module is at most 700 lines.
- No Task 5/6 lifecycle or v2 event work is permitted in v0.71.
- Use one local full suite for the final unchanged code state; do not mechanically repeat it.

---

### Task 1: Freeze the exact contract artifact

**Files:**
- Create: `artifacts/challenger-replacement/challenger-replacement-binance-simulation-contract-v0.71.0.json`
- Create: `tests/test_challenger_replacement_v071_artifacts.py`

**Interfaces:**
- Consumes: `build_challenger_replacement_simulation_contract(*, plan)` and the exact committed v0.69 plan loader.
- Produces: one canonical, self-hashed, strict-loader-replayable contract artifact.

- [ ] **Step 1: Add the absent-artifact RED test**

Require the exact path, canonical bytes, exact plan binding, contract stable ID,
self hash, strict loader replay, and the exact negative authority block whose
counts are zero and activation/install/start/real-orders booleans are false.
Assert there are no authority-granting fields or commit, tag, CI, runtime,
account, credential, or order identities.

- [ ] **Step 2: Run the focused test and observe RED**

Run: `PYTHONPATH=src:tests python3 -m unittest tests.test_challenger_replacement_v071_artifacts -v`

Expected: fail because the exact formal artifact is absent.

- [ ] **Step 3: Generate and add only reviewed canonical bytes**

Use a fixed repository invocation of the Task 1 builder with the exact v0.69
plan. Print bytes to stdout, independently compare them with a second builder
call, add the exact JSON through `apply_patch`, then replay it with the strict
loader. Do not accept an arbitrary output path or caller-provided ID/hash.

- [ ] **Step 4: Run focused and adjacent artifact tests**

Run:

```bash
PYTHONPATH=src:tests python3 -m unittest tests.test_challenger_replacement_v071_artifacts tests.test_challenger_replacement_simulation_contract tests.test_challenger_replacement_plan_v3 -v
git diff --check
```

Expected: all pass; only the test and exact artifact are changed.

- [ ] **Step 5: Commit**

```bash
git add artifacts/challenger-replacement/challenger-replacement-binance-simulation-contract-v0.71.0.json tests/test_challenger_replacement_v071_artifacts.py
git commit -m "test: freeze v0.71 simulation contract"
```

### Task 2: Close release metadata and static gates

**Files:**
- Create: `docs/adr/0071-binance-accounting-core.md`
- Create: `docs/implementation-status-v0.71.0.md`
- Create: `tests/test_challenger_replacement_v071_release.py`
- Modify: `README.md`
- Modify: `src/crypto_quant/__init__.py`
- Modify: `src/crypto_quant/build.py`
- Modify: `src/crypto_quant/challenger_replacement_deployment.py` only for exact current-manifest loader literals; no deployment behavior change.
- Modify: `pyproject.toml`
- Modify: `setup.py`
- Modify: `scripts/refresh_evaluator_build_manifest.py`
- Modify: `config/evaluator-build-manifest-v1.json`
- Modify: `tests/test_estimators.py`
- Modify: `tests/test_challenger_replacement_v066_release.py`
- Modify: `tests/test_challenger_replacement_v067_release.py`
- Modify: `tests/test_challenger_replacement_v068_release.py`
- Modify: `tests/test_challenger_replacement_v069_release.py`
- Modify: `tests/test_challenger_replacement_v070_release.py`
- Modify: `tests/test_nautilus_v065_release.py`
- Modify: `tests/test_nautilus_v0651_hardening.py`
- Modify: `tests/test_v064_public_ci_bundle.py`

**Interfaces:**
- Consumes: final Task 1–4 code and Task 1 contract artifact.
- Produces: package `0.71.0`, manifest `1.65.0`, ADR/status/README truth, and exact release regressions.

- [ ] **Step 1: Add release RED tests**

Require exact package/build version `0.71.0`, manifest version `1.65.0`, inventory hashes, immutable
v0.69/v0.70 ancestry, contract file SHA and semantic replay, exact status, the
six-module line formula, per-module limit, and absence of lifecycle/v2-result,
runtime authority, credentials, Broker, order, network, install, and start APIs.
Require the split spec and plan to be included in the manifest. In this task,
the single-valued status regression accepts only
`CANDIDATE_ACCOUNTING_CORE_LOCAL_VERIFICATION_PENDING`.

- [ ] **Step 2: Run release tests and observe RED**

Run: `PYTHONPATH=src:tests python3 -m unittest tests.test_challenger_replacement_v071_release -v`

Expected: fail while metadata remains v0.70 and release documents are absent.

- [ ] **Step 3: Write truthful candidate docs and metadata**

Document the exact equations, passed Task 4 tests/review, 1,199-line net budget,
fixture-only provenance, no-authority boundary, and v0.72 deferrals. Before full
verification, label local status
`CANDIDATE_ACCOUNTING_CORE_LOCAL_VERIFICATION_PENDING`; do not claim future CI.
Update versions and regenerate manifest `1.65.0` using the repository's
deterministic refresh process. Historical release assertions remain unchanged;
only exact current-manifest literals in the enumerated consumers may change.

- [ ] **Step 4: Run focused release validation**

Run:

```bash
PYTHONPATH=src:tests python3 -m unittest tests.test_challenger_replacement_simulation_contract tests.test_challenger_replacement_binance_simulation_input tests.test_challenger_replacement_simulation tests.test_challenger_replacement_v071_artifacts tests.test_challenger_replacement_v071_release -v
PYTHONPATH=src python3 -m compileall -q src/crypto_quant
git diff --check
```

Expected: all pass and no production module or scope grows.

- [ ] **Step 5: Commit candidate metadata**

```bash
git add README.md docs/adr/0071-binance-accounting-core.md docs/implementation-status-v0.71.0.md src/crypto_quant/__init__.py src/crypto_quant/build.py src/crypto_quant/challenger_replacement_deployment.py pyproject.toml setup.py scripts/refresh_evaluator_build_manifest.py config/evaluator-build-manifest-v1.json tests/test_estimators.py tests/test_challenger_replacement_v066_release.py tests/test_challenger_replacement_v067_release.py tests/test_challenger_replacement_v068_release.py tests/test_challenger_replacement_v069_release.py tests/test_challenger_replacement_v070_release.py tests/test_nautilus_v065_release.py tests/test_nautilus_v0651_hardening.py tests/test_v064_public_ci_bundle.py tests/test_challenger_replacement_v071_release.py
git commit -m "chore: prepare v0.71.0 accounting core release"
```

### Task 3: Verify, review, and publish

**Files:**
- Modify: `docs/implementation-status-v0.71.0.md`
- Modify: `config/evaluator-build-manifest-v1.json`
- Modify: `tests/test_challenger_replacement_v071_release.py`

**Interfaces:**
- Consumes: unchanged final candidate code and artifacts.
- Produces: reviewed local candidate, public PR/main CI evidence, and exact annotated tag identity.

- [ ] **Step 1: Run the final local verification once**

Run the focused and adjacent suites, the complete `unittest discover` suite,
compileall, `make validate`, release validation, diff check, status check, line
budget, and formal artifact replay. Record exact commands, counts, and hashes.

- [ ] **Step 2: Request one independent complete review**

Give the reviewer both specs/plans, the full `v0.70.0^{}` diff, test evidence,
artifact hashes, and safety boundary. Critical/Important must be zero; after any
fix, run only affected tests and targeted re-review unless code state changes
materially.

- [ ] **Step 3: Finalize truthful verified status**

After local gates and review actually pass, change the single-valued release
regression from candidate-only to accepting only
`FIXTURE_ACCOUNTING_CORE_VERIFIED_LIFECYCLE_NOT_IMPLEMENTED`; update the status,
refresh/replay manifest `1.65.0`, run affected release tests, and commit the
final candidate. A two-value status assertion is forbidden.

```bash
git add docs/implementation-status-v0.71.0.md config/evaluator-build-manifest-v1.json tests/test_challenger_replacement_v071_release.py
git commit -m "docs: finalize v0.71 verification status"
```

- [ ] **Step 4: Publish through the approved public release ceremony**

Revalidate the public target repository, origin/main, write permission, and
clean candidate. Create Draft PR, require Python 3.9/3.12 and macOS arm64 PR CI,
merge exact reviewed head, require main CI, then create annotated `v0.71.0` only
when tag peeled commit equals origin/main. Any failure stops publication; do not
rewrite evidence or claim success.

- [ ] **Step 5: Leave the v0.72 durable handoff**

Record v0.71 commit/tag/CI/artifact identities and the exact deferred scope.
Start no v0.72 code until its independent design and implementation plan are
reviewed. Do not install or start any service.
