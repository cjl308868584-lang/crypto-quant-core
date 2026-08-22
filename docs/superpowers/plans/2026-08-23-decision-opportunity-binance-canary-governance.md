# DecisionOpportunity and Binance Canary Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish v0.69.0 as a plan-only, pre-start replacement v3 preregistration that replaces permanent 540-slot failure with auditable DecisionOpportunity outcomes, separates minimum seven-day operational qualification from independent 90-day economics, and freezes a Binance-only E0/E1/E2 Canary contract without enabling credentials, orders, installation or production activation.

**Architecture:** A parameterless v3 builder creates one canonical plan whose append-only opportunity log is the sole future authority for two independent evaluators. A second pre-start supersession ceremony binds the exact v0.64 plan, released v0.68 foundation, current no-observable-state machine evidence and a separately approved accountable owner declaration. Existing crash-safe fixed-path governance publication primitives are extended only for four v0.69 filenames; no runtime, scheduler, Broker or generic storage is added.

**Tech Stack:** Python 3.9+, standard-library `json`/`hashlib`/`pathlib`/`os`/`subprocess`, Draft 2020-12 JSON Schema, existing canonical JSON and strict owner-file loaders, `unittest`, Git/GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-23-decision-opportunity-binance-canary-governance-design.md`

## Global Constraints

- Work only in `.worktrees/v0.69-decision-opportunity-canary-governance` on branch `codex/v0.69-decision-opportunity-canary-governance` based on `b65481cce9c8955f73da5b78ef2bd3c981f3be3c`.
- v0.69 is governance/plan-only. Do not add or execute runtime events, scheduler, market/account network, Binance SDK, credential reads, Broker/order/fill, production root/plist, launchctl, UI changes, funds, seven-day timer or 90-day timer.
- Never modify or regenerate committed v0.64 plan, machine evidence, owner attestation, supersession record, v0.67 deployment artifact or v0.68 code history.
- Formal v3 artifacts require annotated `v0.68.0`, origin/main, PR/main CI and build-manifest identities to agree exactly on `b65481c...`; if they do not, stop before artifact generation.
- Treat this as a research and operational policy re-registration. Never assert that v0.64 research-bearing subtrees remain byte-equal.
- Preserve old-cohort failure, no-backfill, no-AI-authority, no-interim-profitability, owner-only roots, append-only event authority, no-overwrite and failure-closed guarantees.
- The v3 plan must freeze four-hour opportunities, `OBSERVED|MISSED`, 95% observed coverage gates, minimum seven-day operational qualification, independent minimum 90-day economics, Binance Spot-long/perpetual-short mutual exclusion, E0/E1/E2 amounts/exposure/durations/cycles and exact loss boundaries from the spec.
- v0.69 authority remains `credentials_allowed=false`, `account_requests_allowed=false`, `broker_requests_allowed=false`, `real_orders_allowed=false`, `production_activation=false`, `runtime_install_authorized=false`, `replacement_start_authorized=false`.
- Machine evidence proves only current `NO_OBSERVABLE_REPLACEMENT_STATE_AT_COLLECTION`; historical pre-start status additionally requires immutable Git/release facts and accountable owner attestation.
- Do not sign for the owner. Before the formal attestation command, show the exact declaration bytes, declaration SHA-256 and all binding hashes and obtain explicit approval.
- Extend the reviewed v0.64 governance publisher rather than copying OS primitives. New paths remain fixed and parameterless; direct canonical writes, `os.replace`, plain `os.rename`, pathname overwrite or arbitrary output arguments are forbidden.
- Every code task follows exact RED → minimal GREEN → refactor → focused/adjacent tests → commit. Do not run repeated full suites on unchanged code.
- Final code state runs one local full suite, compileall, `make validate`, diff-check and one independent complete review; fixes receive targeted re-review only.
- Push/PR/merge/annotated tag, production install/start, API key, funds and every Canary stage remain separate exact approval gates.

---

## File Map

### V3 plan

- Create `src/crypto_quant/challenger_replacement_plan_v3.py`: parameterless builder, semantic validator, plan hash/ID and strict loader.
- Create `config/challenger-replacement-plan-v3.schema.json`: canonical config Schema.
- Create `src/crypto_quant/schemas/challenger-replacement-plan-v3.schema.json`: byte-identical package Schema mirror.
- Create `tests/test_challenger_replacement_plan_v3.py`: frozen fields, semantic diff, hashes, Schema and immutable predecessor tests.

### V3 supersession ceremony

- Create `src/crypto_quant/challenger_replacement_plan_v3_supersession.py`: strict machine-evidence, attestation and record builders/loaders.
- Create `src/crypto_quant/challenger_replacement_plan_v3_supersession_cli.py`: fixed commands `collect-machine-evidence`, `record-owner-attestation`, `assemble-record`.
- Modify `src/crypto_quant/challenger_replacement_supersession_publish.py`: add only four fixed v0.69 final names, a distinct staging namespace and four typed wrappers over the existing reviewed primitive.
- Modify `.gitignore`: exact v0.69 staging basename pattern only.
- Create byte-identical config/package Schema pairs:
  - `challenger-replacement-v3-supersession-machine-evidence-v1.schema.json`
  - `challenger-replacement-v3-owner-attestation-v1.schema.json`
  - `challenger-replacement-plan-v3-supersession-v1.schema.json`
- Create `tests/test_challenger_replacement_plan_v3_supersession.py`: provenance, no-side-effect, fixed-path publication and ceremony state-machine tests.
- Modify `tests/test_challenger_replacement_plan_supersession.py`: prove v0.64 protocol bytes and behavior remain unchanged.

### Formal artifacts generated only after gates

- `artifacts/challenger-replacement/challenger-replacement-plan-v0.69.0.json`
- `artifacts/challenger-replacement/challenger-replacement-v3-supersession-machine-evidence-v0.69.0.json`
- `artifacts/challenger-replacement/challenger-replacement-v3-owner-attestation-v0.69.0.json`
- `artifacts/challenger-replacement/challenger-replacement-plan-v3-supersession-v0.69.0.json`

### Release

- Create `tests/test_challenger_replacement_v069_release.py`.
- Create `docs/adr/0069-decision-opportunity-binance-canary-preregistration.md`.
- Create `docs/implementation-status-v0.69.0.md`.
- Modify `README.md`, `pyproject.toml`, `setup.py`, `src/crypto_quant/__init__.py`, `src/crypto_quant/build.py`, `scripts/refresh_evaluator_build_manifest.py`, `config/evaluator-build-manifest-v1.json`, `tests/test_estimators.py`, `tests/test_nautilus_v065_release.py`, `tests/test_nautilus_v0651_hardening.py`, `tests/test_challenger_replacement_v066_release.py`, `tests/test_challenger_replacement_v067_release.py`, `tests/test_challenger_replacement_v068_release.py` and `tests/test_v064_public_ci_bundle.py`.

---

### Task 1: Freeze Predecessor and V3 Schema Contract

**Files:**

- Create: `tests/test_challenger_replacement_plan_v3.py`
- Create: `config/challenger-replacement-plan-v3.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-plan-v3.schema.json`

**Interfaces:**

- Consumes: committed v0.64 artifact bytes and `load_challenger_replacement_plan_v2(path: Path)`.
- Produces: strict mirrored plan v3 Schema and exact constants for later builder tests.

- [ ] **Step 1: Write immutable predecessor and initial missing-Schema tests**

Use exact constants:

```python
V064_PLAN = Path("artifacts/challenger-replacement/challenger-replacement-plan-v0.64.0.json")
V064_FILE_SHA = "5f1774fd912451d79c9efe13401e80f312fee3c707d9faa252933ef3e8810a8f"
V064_PLAN_ID = "challenger_replacement_plan_65d85d60a534a917f45a1ffa5fc9d3f74d6d24995b900d31b8c73cd26f0bd97b"
V064_PLAN_HASH = "c9a1e5f74c52fbf23be5a1d27fd23c25f3601ed58133178fc25480391ab65705"
```

Assert exact bytes before/after the class, v2 loader replay, missing v3 Schema mirrors, and that no formal v0.69 artifact exists at this task.

- [ ] **Step 2: Run the focused test and capture RED**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_plan_v3 -v
```

Expected: FAIL only because both v3 Schema mirrors are absent.

- [ ] **Step 3: Add strict Schema mirrors**

Freeze this top-level exact key set:

```text
$schema, schema_version, plan_id, plan_hash, foundation, predecessor,
scope, decision_policy, opportunity_policy, operational_qualification,
economic_evidence, canary_ladder, product_policy, risk_policy,
isolation_policy, evidence_policy, storage_authority, supersession,
authority, status, eligibility, warnings
```

Use `additionalProperties: false` recursively. Require safe integers, lowercase SHA-256, millisecond UTC strings, canonical decimal strings and exact enums from the spec. Schema mirrors must be byte-identical.

- [ ] **Step 4: Run focused tests and commit**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_plan_v3 -v
git diff --check
git add tests/test_challenger_replacement_plan_v3.py \
  config/challenger-replacement-plan-v3.schema.json \
  src/crypto_quant/schemas/challenger-replacement-plan-v3.schema.json
git commit -m "test: freeze replacement v3 plan schema"
```

Expected: tests PASS; v0.64 bytes unchanged.

### Task 2: Build and Strictly Replay the V3 Plan

**Files:**

- Create: `src/crypto_quant/challenger_replacement_plan_v3.py`
- Modify: `tests/test_challenger_replacement_plan_v3.py`

**Interfaces:**

- Produces:

```python
class ChallengerReplacementPlanV3Error(ValueError):
    reason_code: str

def build_challenger_replacement_plan_v3() -> dict[str, object]: ...
def challenger_replacement_plan_v3_hash(plan: Mapping[str, object]) -> str: ...
def challenger_replacement_plan_v3_reasons(plan: Mapping[str, object]) -> tuple[str, ...]: ...
def load_challenger_replacement_plan_v3(path: Path) -> dict[str, object]: ...
```

- [ ] **Step 1: Write failing builder/loader tests**

Assert the builder has no parameters and fixes:

```python
assert plan["opportunity_policy"] == {
    "cadence_seconds": 14400,
    "capture_open_offset_seconds": 120,
    "capture_close_offset_seconds": 600,
    "terminal_outcomes": ["OBSERVED", "MISSED"],
    "historical_decision_backfill_allowed": False,
    "missed_opportunity_recovery": "APPEND_MISSED_WITH_ACTUAL_DETECTION_TIME",
}
assert plan["operational_qualification"]["minimum_calendar_days"] == 7
assert plan["operational_qualification"]["minimum_observed_coverage"] == "0.95"
assert plan["economic_evidence"]["minimum_calendar_days"] == 90
assert plan["economic_evidence"]["interim_profitability_pass_allowed"] is False
```

Assert exact E0/E1/E2 tables, mutual exclusion, one-way isolated perpetual, hard 2× technical cap, E1 inheritance of E0 absolute loss limits, exact safety failure reasons and all authority booleans false. Mutating any field, unknown key, hash, ID, predecessor identity or unlisted semantic diff must produce a fixed reason code.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_plan_v3 -v
```

Expected: import failure for `challenger_replacement_plan_v3`.

- [ ] **Step 3: Implement the minimal parameterless builder and loader**

Reuse `canonical_json`, `stable_id`, `_read_owner_controlled_regular_file` and `Draft202012Validator` conventions. Compute every nested `policy_hash` after its non-self-referential object is final; compute `plan_hash` with `plan_id`/`plan_hash` excluded, then `plan_id = stable_id("challenger_replacement_plan_v3", identity)`.

The `/supersession/semantic_changes` array must be exact and ordered. The foundation object must be loaded from constants derived from the final v0.68 release gate; no caller override is accepted.

- [ ] **Step 4: Verify mutation matrix and commit**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_plan_v3 -v
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_plan_v2 \
  tests.test_challenger_replacement_plan_supersession -v
python3 -m compileall -q src/crypto_quant/challenger_replacement_plan_v3.py \
  tests/test_challenger_replacement_plan_v3.py
git diff --check
git add src/crypto_quant/challenger_replacement_plan_v3.py \
  tests/test_challenger_replacement_plan_v3.py
git commit -m "feat: freeze replacement v3 governance plan"
```

### Task 3: Define V3 Supersession Evidence and Attestation

**Files:**

- Create: `src/crypto_quant/challenger_replacement_plan_v3_supersession.py`
- Create: `config/challenger-replacement-v3-supersession-machine-evidence-v1.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-v3-supersession-machine-evidence-v1.schema.json`
- Create: `config/challenger-replacement-v3-owner-attestation-v1.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-v3-owner-attestation-v1.schema.json`
- Create: `config/challenger-replacement-plan-v3-supersession-v1.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-plan-v3-supersession-v1.schema.json`
- Create: `tests/test_challenger_replacement_plan_v3_supersession.py`

**Interfaces:**

- Produces:

```python
ACCOUNTABLE_OWNER_DECLARATION_V3: str
REAL_V3_EVIDENCE_QUALIFICATION = "REAL_PRE_START_V3_SUPERSESSION_EVIDENCE"

def load_challenger_replacement_v3_machine_evidence(path: Path) -> dict[str, object]: ...
def load_challenger_replacement_v3_owner_attestation(path: Path) -> dict[str, object]: ...
def build_challenger_replacement_v3_supersession_record(
    plan: Mapping[str, object],
    machine: Mapping[str, object],
    attestation: Mapping[str, object],
) -> dict[str, object]: ...
def load_challenger_replacement_v3_supersession_record(path: Path) -> dict[str, object]: ...
```

- [ ] **Step 1: Write failing Schema/loader tests**

Require machine evidence to bind fixed repo root, HEAD, v0.64/v0.68 tags and artifacts, raw argv/exit/stdout/stderr byte hashes, runtime root/plist/service observations, and collector side-effect counters. Runtime absence derives only current counts.

Require the declaration to state exactly:

```text
I attest that before the bound machine-evidence collection time the
replacement-v3 service had never been installed or started, no replacement
start receipt or canonical production opportunity event had been created,
and no real order had been submitted by this replacement path. I understand
this is an accountable governance statement, not a fact that code or an OS
snapshot can prove, and that supersession is forbidden after the first v3
start receipt or canonical production opportunity event.
```

The Schema/loader validates structure, hashes, qualification and binding; tests must explicitly state it cannot prove the declaration true or prove an unpatched process.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_plan_v3_supersession -v
```

Expected: missing module and Schema failures.

- [ ] **Step 3: Implement strict models and mirrors**

Reuse canonical/hashing conventions but do not modify v0.64 loaders. Record reason is exact:

```text
SUPERSEDED_PRE_START_RESEARCH_AND_OPERATIONAL_POLICY_CHANGE
```

Record binds file SHA/ID/hash for both plans, v0.68 release identity, machine evidence, owner attestation and an ordered semantic-diff hash. It contains no self file SHA; status/build manifest binds that externally.

- [ ] **Step 4: Verify and commit**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_plan_v3 \
  tests.test_challenger_replacement_plan_v3_supersession -v
python3 -m compileall -q \
  src/crypto_quant/challenger_replacement_plan_v3_supersession.py
git diff --check
git add src/crypto_quant/challenger_replacement_plan_v3_supersession.py \
  config/challenger-replacement-v3-*.schema.json \
  config/challenger-replacement-plan-v3-supersession-v1.schema.json \
  src/crypto_quant/schemas/challenger-replacement-v3-*.schema.json \
  src/crypto_quant/schemas/challenger-replacement-plan-v3-supersession-v1.schema.json \
  tests/test_challenger_replacement_plan_v3_supersession.py
git commit -m "feat: bind replacement v3 supersession evidence"
```

### Task 4: Extend Fixed-Path Crash-Safe Governance Publication

**Files:**

- Modify: `src/crypto_quant/challenger_replacement_supersession_publish.py`
- Create: `src/crypto_quant/challenger_replacement_plan_v3_supersession_cli.py`
- Modify: `.gitignore`
- Modify: `tests/test_challenger_replacement_plan_v3_supersession.py`
- Modify: `tests/test_challenger_replacement_plan_supersession.py`

**Interfaces:**

- Produces four typed wrappers with no path argument:

```python
publish_challenger_replacement_plan_v3_bytes(data: bytes) -> dict[str, object]
publish_challenger_replacement_v3_machine_evidence_bytes(data: bytes) -> dict[str, object]
publish_challenger_replacement_v3_owner_attestation_bytes(data: bytes) -> dict[str, object]
publish_challenger_replacement_v3_supersession_record_bytes(data: bytes) -> dict[str, object]
```

- [ ] **Step 1: Add RED tests for fixed paths and crash boundaries**

Cover exact/idempotent/different existing final; FIFO/socket/directory/symlink/hardlink/wrong owner/mode; short write/EINTR/readback/file fsync/no-replace/dir fsync; rename-before-dir-fsync retry; parent rename; close-failure primary preservation; orphan staging inventory; two-process same/different byte races. Snapshot external sentinel bytes/mode/size/mtime/ctime/inode/nlink before/after every rejection.

Assert v0.64 staging regex/final names/functions and committed artifacts remain exact.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_plan_supersession \
  tests.test_challenger_replacement_plan_v3_supersession -v
```

Expected: missing v0.69 fixed wrappers/CLI behavior only.

- [ ] **Step 3: Add the minimal v0.69 namespace**

Extend `_FIXED_FINAL_NAMES` with only the four File Map basenames and accept a distinct protocol regex:

```text
.v069-opportunity-governance-(plan|machine-evidence|owner-attestation|supersession-record)-<sha256>-<nonce>.staging
```

All I/O continues through retained parent dirfd, O_NOFOLLOW/O_NONBLOCK validation, same-fd staging readback, file fsync, atomic platform-specific no-replace, directory fsync and attachment revalidation. Never delete or chmod untrusted objects.

CLI has only the fixed commands and no path/date/identity/declaration override. It uses `/usr/bin/git` and `/bin/launchctl print-disabled/print` through exact argv; no shell.

- [ ] **Step 4: Verify Linux/Darwin primitive boundaries and commit**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_plan_supersession \
  tests.test_challenger_replacement_plan_v3_supersession -v
python3 -m compileall -q \
  src/crypto_quant/challenger_replacement_supersession_publish.py \
  src/crypto_quant/challenger_replacement_plan_v3_supersession_cli.py
git diff --check
git add .gitignore \
  src/crypto_quant/challenger_replacement_supersession_publish.py \
  src/crypto_quant/challenger_replacement_plan_v3_supersession_cli.py \
  tests/test_challenger_replacement_plan_supersession.py \
  tests/test_challenger_replacement_plan_v3_supersession.py
git commit -m "feat: publish replacement v3 governance evidence"
```

### Task 5: Freeze and Commit the Formal V3 Plan

**Files:**

- Create: `artifacts/challenger-replacement/challenger-replacement-plan-v0.69.0.json`
- Modify: `tests/test_challenger_replacement_plan_v3.py`

**Interfaces:**

- Consumes: released v0.68 exact tag/commit/manifest identity and passing Tasks 1-4.
- Produces: the first immutable v3 plan artifact; no machine evidence yet.

- [ ] **Step 1: Verify the release foundation and clean candidate**

Run fixed read-only GitHub/`git` checks and require:

```text
v0.68.0 annotated tag
v0.68.0^{} == origin/main == b65481cce9c8955f73da5b78ef2bd3c981f3be3c
PR Python 3.9/3.12 and macOS arm64 CI success
merged-main CI success
manifest_version 1.62.0, package_version 0.68.0
```

If any value differs, do not generate the plan.

- [ ] **Step 2: Add committed-artifact test and confirm RED**

The test loads the fixed path, compares exact builder canonical bytes, checks file SHA/ID/hash, and verifies no other v0.69 governance artifacts exist yet.

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_plan_v3 -v
```

Expected: FAIL only because the formal plan file is absent.

- [ ] **Step 3: Publish through the fixed wrapper**

Invoke a parameterless reviewed CLI/build command that obtains builder canonical bytes and calls `publish_challenger_replacement_plan_v3_bytes`. Capture stdout/stderr/exit code and verify exact bytes through the production loader and SHA-256.

- [ ] **Step 4: Run tests and commit only the plan plus precommitted test**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_plan_v3 \
  tests.test_challenger_replacement_plan_v3_supersession -v
git diff --check
git add tests/test_challenger_replacement_plan_v3.py \
  artifacts/challenger-replacement/challenger-replacement-plan-v0.69.0.json
git commit -m "plan: preregister decision opportunity governance"
```

Freeze resulting `HEAD=H`. No code/test/doc changes are allowed during the Task 6 ceremony.

### Task 6: Execute the Pre-Start Supersession Ceremony

**Files:**

- Create the remaining three formal JSON artifacts from the File Map.
- Do not modify code, tests, spec or plan while `HEAD=H` is frozen.

**Candidate-state machine:**

```text
C0 clean H
C1 H + exact machine-evidence final
C2 H + exact machine-evidence + exact owner-attestation finals
C3 H + exact three non-plan formal finals
C4 clean after the three-artifact commit
```

- [ ] **Step 1: Collect current machine evidence from C0**

Run the parameterless command in an independent process. It must record pre-command raw Git status, exact argv/transcripts, runtime root/plist/service observations, artifact inventories and collector side-effect counters. After publication, C1 allowlist contains only the fixed evidence final and no protocol staging.

- [ ] **Step 2: Display the exact owner approval package and stop for explicit approval**

Display:

```text
ACCOUNTABLE_OWNER_DECLARATION_V3 exact UTF-8 bytes
declaration_sha256
v0.64 plan file SHA/ID/hash
v0.68 tag/commit/manifest identity
v3 plan file SHA/ID/hash
machine-evidence file SHA/evidence ID/hash/observed_at
owner uid and proposed signed_at
```

Do not accept general project authorization as a signature. Require the user to approve this exact package.

- [ ] **Step 3: Record attestation from C1**

After approval, invoke the parameterless attestation command with only its fixed acknowledgement token. It replays C1 allowlist and all bindings before publishing. C2 contains exactly evidence + attestation.

- [ ] **Step 4: Assemble supersession record from C2**

The parameterless command loads exact plan/evidence/attestation, verifies no start/event/order fact, builds the record and no-overwrite publishes it. C3 contains exactly the three uncommitted formal artifacts.

- [ ] **Step 5: Run precommitted formal-artifact regressions**

Tests for the three fixed paths may be explicitly skipped before Task 6; at C3, assert those exact tests run without skip and pass. Do not edit tests after `H`.

- [ ] **Step 6: Commit only the three artifacts and verify C4**

```bash
git add \
  artifacts/challenger-replacement/challenger-replacement-v3-supersession-machine-evidence-v0.69.0.json \
  artifacts/challenger-replacement/challenger-replacement-v3-owner-attestation-v0.69.0.json \
  artifacts/challenger-replacement/challenger-replacement-plan-v3-supersession-v0.69.0.json
git commit -m "evidence: record replacement v3 pre-start supersession"
git status --short
```

Expected: clean C4. Any sealed orphan or unexpected path blocks release; preserve the worktree for evidence and restart from exact pre-artifact `H` in a new isolated worktree without deleting the orphan.

### Task 7: Release Metadata and Complete Verification

**Files:**

- Create: `tests/test_challenger_replacement_v069_release.py`
- Create: `docs/adr/0069-decision-opportunity-binance-canary-preregistration.md`
- Create: `docs/implementation-status-v0.69.0.md`
- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `setup.py`
- Modify: `src/crypto_quant/__init__.py`
- Modify: `src/crypto_quant/build.py`
- Modify: `scripts/refresh_evaluator_build_manifest.py`
- Modify: `config/evaluator-build-manifest-v1.json`
- Modify: `tests/test_estimators.py`
- Modify: `tests/test_nautilus_v065_release.py`
- Modify: `tests/test_nautilus_v0651_hardening.py`
- Modify: `tests/test_challenger_replacement_v066_release.py`
- Modify: `tests/test_challenger_replacement_v067_release.py`
- Modify: `tests/test_challenger_replacement_v068_release.py`
- Modify: `tests/test_v064_public_ci_bundle.py`

**Interfaces:**

- Consumes: committed four-artifact governance chain.
- Produces: local v0.69 release candidate only.

- [ ] **Step 1: Add RED release tests**

Require package `0.69.0`, manifest next version, exact file inventory, all artifact loader replays, predecessor immutability, v0.69 plan-only boundaries, absence of runtime/Binance SDK/Broker/credential/production changes, and documentation non-claims.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_v069_release -v
```

Expected: fail on old version/manifest and missing ADR/status.

- [ ] **Step 3: Add minimal release metadata**

ADR records why v3 is an explicit hypothesis reset and why dual-track opportunity evidence was chosen. Status is fixed to `PLAN_FROZEN_REPLACEMENT_V3_NOT_STARTED`; README says no production install/start, no credential/order/funds, no seven-day or 90-day timer and no profitability/AI/Canary claim.

Refresh the build manifest only after all tracked bytes are final.

- [ ] **Step 4: Run focused, adjacent and single final full suite**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_plan_v3 \
  tests.test_challenger_replacement_plan_v3_supersession \
  tests.test_challenger_replacement_v069_release -v
PYTHONPATH=src python3 -m unittest discover -s tests
python3 -m compileall -q src tests
make validate
git diff --check
```

Record exact counts, skips, expected policy status and manifest hashes. Do not repeat the full suite unless code bytes change.

- [ ] **Step 5: Independent review and local release-candidate commit**

Request one complete read-only review against the spec/plan. Fix Critical/Important findings with focused RED/GREEN tests and targeted re-review only. When zero:

```bash
git add README.md pyproject.toml setup.py \
  src/crypto_quant/__init__.py src/crypto_quant/build.py \
  scripts/refresh_evaluator_build_manifest.py \
  config/evaluator-build-manifest-v1.json \
  docs/adr/0069-decision-opportunity-binance-canary-preregistration.md \
  docs/implementation-status-v0.69.0.md \
  tests/test_challenger_replacement_v069_release.py \
  tests/test_estimators.py tests/test_nautilus_v065_release.py \
  tests/test_nautilus_v0651_hardening.py \
  tests/test_challenger_replacement_v066_release.py \
  tests/test_challenger_replacement_v067_release.py \
  tests/test_challenger_replacement_v068_release.py \
  tests/test_v064_public_ci_bundle.py
git diff --cached --check
git commit -m "release: freeze decision opportunity governance v0.69.0"
```

Verify clean worktree, exact HEAD and production-loader replay.

### Task 8: Remote Release and Handoff

**Files:** None beyond committed release candidate.

**Interfaces:**

- Produces: public Draft PR, merged main, annotated `v0.69.0`, and v0.70 handoff only after remote approval.

- [ ] **Step 1: Prepare exact remote approval package**

Show target public repository, origin URL, branch/head/tree, commit range, changed-file inventory, no-secret scan, review result and local verification evidence. Obtain explicit push/PR/merge/tag approval if not already exact for this candidate.

- [ ] **Step 2: Push branch and create Draft PR**

Verify PR head equals local HEAD. Wait for Python 3.9/3.12 and macOS arm64 CI; do not substitute unrelated runs.

- [ ] **Step 3: Merge and verify main CI**

Merge only the reviewed head. Verify origin/main commit and tree, then wait for merged-main CI success.

- [ ] **Step 4: Create and verify annotated tag**

Create annotated `v0.69.0` only after main CI. Verify tag object type, peeled commit and origin/main exact equality.

- [ ] **Step 5: Freeze v0.70 handoff**

Record that v0.70 may implement DecisionOpportunity/evaluators but still has no credential, Broker, money or production activation. Do not install/start v0.68 or v0.69 because their old/new plan authority remains disabled.

## Completion Evidence

v0.69 is complete only when all eight tasks are checked, four formal artifacts replay exactly, owner attestation is explicitly approved, no-observable-state evidence is valid, final tests/review/CI are green, main and annotated tag identities match, and no production install/start/credential/order/fund action occurred. This is a governance milestone, not operational qualification, economic PASS or Canary authorization.
