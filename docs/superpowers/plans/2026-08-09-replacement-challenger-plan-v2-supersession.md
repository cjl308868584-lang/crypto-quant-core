# Replacement Challenger Preregistration V2 Supersession Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish v0.64.0 as an explicit plan-only superseding preregistration v2 that replaces the infeasible v0.62 storage contract before any replacement installation, start receipt, canonical event, real slot, or production state write.

**Architecture:** A separate parameterless v2 builder copies the research-bearing v0.62 canonical subtrees exactly and changes only version/foundation, storage paths, event-log authority, and supersession metadata. Strict v2 plan and supersession-record loaders reject ambiguity and test evidence. A dedicated read-only collector can generate the sole real-machine supersession record only after the v2 plan artifact exists and only while the replacement identity remains absent and unused.

**Tech Stack:** Python 3.9+, standard-library `json`/`hashlib`/`pathlib`/`os`/`subprocess`, Draft 2020-12 JSON Schema, existing canonical JSON and strict-loader conventions, `unittest`, Make validation, Git/GitHub Actions.

## Global Constraints

- Work only from annotated `v0.63.0` peeled commit `df91e19240df14839125608422489adf3b902e76` on isolated branch `codex/v0.64-replacement-plan-v2`.
- Never modify, regenerate, delete, or force-move v0.62 plan bytes, Schema, ADR, status document, annotated tag, tag object, or peeled commit.
- v0.62 plan file SHA-256 is `d450d1e9f8dc422eb5a93beb8a5ffbb1746a4a6d1facb3c5a20a76f4bd527734`; plan ID/hash are the exact values in the design.
- v0.64 is governance/plan-only. Do not add replacement runtime, event implementation, SQLite, artifact publisher, deployment, installer, observer, exporter, evaluator, Runner, scheduler, maintenance, market, account, Broker, credential, order, or production-state code.
- Never create the replacement runtime root or plist and never load/bootstrap/kickstart its service.
- Preserve all v0.62 research-bearing canonical subtree bytes identified in the design.
- Use `state/challenger-replacement-events-v1` as the sole future authority and `exports` only as a non-authoritative, reconstructible future output root.
- Generate the formal v2 plan artifact only after all builder, Schema, equality, loader, and supersession-contract tests pass.
- Generate the formal supersession record only after the committed-candidate v2 plan artifact passes its production loader and a real-machine read-only precondition check passes.
- Test fixtures must use `TEST_FIXTURE_ONLY_NOT_SUPERSESSION_EVIDENCE`; they can never be committed as the formal supersession record.
- Keep `v0.65.0` reserved for the approved single end-to-end NautilusTrader Spike; replacement three-stage runtime is `v0.66.0` or later.
- Run one local full suite for the final code state, one complete independent review, targeted re-review after fixes, PR Python 3.9/3.12 CI, merged-main CI, and annotated-tag identity verification.

---

## File Map

### New v2 plan unit

- `src/crypto_quant/challenger_replacement_plan_v2.py`: parameterless v2 builder, semantic reasons and strict plan loader.
- `src/crypto_quant/schemas/challenger-replacement-plan-v2.schema.json`: package Schema.
- `config/challenger-replacement-plan-v2.schema.json`: byte-identical config Schema mirror.
- `tests/test_challenger_replacement_plan_v2.py`: v0.62 equality, v2 storage, hashing, Schema and loader tests.

### New supersession unit

- `src/crypto_quant/challenger_replacement_plan_supersession.py`: strict record model, hash/ID derivation, real-evidence validation and loader.
- `src/crypto_quant/schemas/challenger-replacement-plan-supersession-v1.schema.json`: package record Schema.
- `config/challenger-replacement-plan-supersession-v1.schema.json`: byte-identical config Schema mirror.
- `src/crypto_quant/challenger_replacement_plan_supersession_cli.py`: read-only real-machine collector and no-overwrite repository artifact writer.
- `tests/test_challenger_replacement_plan_supersession.py`: fixture, collector boundary, no-side-effect and record tests.

### Generated only after test gates

- `artifacts/challenger-replacement/challenger-replacement-plan-v0.64.0.json`: exact v2 plan artifact.
- `artifacts/challenger-replacement/challenger-replacement-plan-supersession-v0.64.0.json`: exact real-machine supersession record.

### Governance and release

- `docs/adr/0064-replacement-challenger-plan-v2-storage-supersession.md`
- `docs/implementation-status-v0.64.0.md`
- `README.md`
- `pyproject.toml`
- `src/crypto_quant/__init__.py`
- `src/crypto_quant/build.py`
- `config/evaluator-build-manifest-v1.json`

---

## Task 1: Freeze v0.62 Equality and V2 Schema Before Building Anything

**Files:**

- Create: `tests/test_challenger_replacement_plan_v2.py`
- Create: `config/challenger-replacement-plan-v2.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-plan-v2.schema.json`

**Interfaces:**

- Consumes: `load_challenger_replacement_plan(path: Path)` from v0.62 production code and the committed v0.62 artifact.
- Produces: strict Draft 2020-12 v2 Schema mirrors and exact constants used by the v2 builder tests.

- [ ] **Step 1: Add the v0.62 immutable-source test**

Load exact bytes from:

```python
V1_PATH = Path(
    "artifacts/challenger-replacement/"
    "challenger-replacement-plan-v0.62.0.json"
)
V1_FILE_SHA256 = "d450d1e9f8dc422eb5a93beb8a5ffbb1746a4a6d1facb3c5a20a76f4bd527734"
V1_PLAN_ID = "challenger_replacement_plan_d4a542c1566f7a90466ca4d5301b81847f5b5eba93c7a00903d2d95331bc23a2"
V1_PLAN_HASH = "95f395b17d9c09d325c58391542ce5f3d9df5ce6a706b1bba8ffcb62dc6c883c"
V1_PEELED_COMMIT = "e0a9b3eb6a3f385ea259722e6613df8708e8fe5a"
```

Assert file SHA, plan ID/hash and loader replay. Record `V1_PATH.read_bytes()` before the test class and assert it remains identical in `tearDownClass`; tests may never write this path.

- [ ] **Step 2: Add the initially failing Schema mirror and exact-key tests**

Require the two v2 Schema files to be byte-identical and require this exact relative-path object:

```python
EXPECTED_RELATIVE_PATHS = {
    "state_events": "state/challenger-replacement-events-v1",
    "non_authoritative_exports": "exports",
    "stdout": "log/challenger-replacement.stdout.log",
    "stderr": "log/challenger-replacement.stderr.log",
    "deployment_contract": "deployment/contract.json",
    "deployment_plist": "deployment/local.crypto-quant.challenger-replacement-v1.plist",
    "preflight_receipts": "preflight-receipts",
    "install_receipts": "install-receipts",
    "start_receipts": "start-receipts",
    "episode_receipts": "episode-receipts",
    "archives": "archives",
    "results": "results",
    "indexes": "indexes",
    "evaluations": "evaluations",
}
```

Assert `state`, `source_bundles`, and `decisions` are not Schema properties and are rejected through `additionalProperties: false`.

- [ ] **Step 3: Run the Schema test and confirm red**

Run:

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_plan_v2 -v
```

Expected: failure because the v2 Schema mirrors do not exist.

- [ ] **Step 4: Write the two strict v2 Schema mirrors**

The top-level exact key set is:

```text
$schema, schema_version, plan_id, plan_hash, foundation, predecessor,
scope, decision_policy, cohort_policy, isolation_policy, evidence_policy,
storage_authority, supersession, authority, status, eligibility, warnings
```

Use `additionalProperties: false` at every object. Freeze:

```text
$schema       ./challenger-replacement-plan-v2.schema.json
schema_version 2.0.0
status        PLAN_FROZEN_REPLACEMENT_V2_NOT_STARTED
```

Copy all const values for `scope`, `decision_policy`, `cohort_policy`, `evidence_policy`,
`predecessor`, `eligibility`, `authority`, and all unchanged isolation fields from the v1
Schema exactly. Add the exact storage and supersession objects from the design.

- [ ] **Step 5: Run the Schema slice to green**

Run the Task 1 command. Expected: Schema mirror and exact-key tests pass; builder import tests may remain skipped only through a test class explicitly dedicated to later Tasks, not through broad exception handling.

- [ ] **Step 6: Commit the Schema-first slice**

```bash
git add tests/test_challenger_replacement_plan_v2.py \
  config/challenger-replacement-plan-v2.schema.json \
  src/crypto_quant/schemas/challenger-replacement-plan-v2.schema.json
git commit -m "test: freeze replacement plan v2 schema"
```

---

## Task 2: Implement the Parameterless V2 Builder With Canonical Equality

**Files:**

- Create: `src/crypto_quant/challenger_replacement_plan_v2.py`
- Modify: `tests/test_challenger_replacement_plan_v2.py`

**Interfaces:**

- Produces:

```python
def build_challenger_replacement_plan_v2() -> Dict[str, Any]: ...
def challenger_replacement_plan_v2_hash(plan: Mapping[str, Any]) -> str: ...
def challenger_replacement_plan_v2_reasons(plan: Mapping[str, Any]) -> Tuple[str, ...]: ...
def load_challenger_replacement_plan_v2(path: Path) -> Dict[str, Any]: ...
```

- [ ] **Step 1: Add failing canonical subtree equality tests**

Call the v2 builder 100 times and require exact equality. For each path below, compare canonical bytes from v1 and v2:

```python
BYTE_EQUAL_PATHS = (
    "scope", "decision_policy", "cohort_policy", "evidence_policy",
    "predecessor", "eligibility",
)
```

Compare every `/authority` leaf and every `/isolation_policy` child except `relative_paths` and
`policy_hash`. Include explicit assertions for `service_label`, `service_identity`, `runtime_root`,
and `target_plist`. Fail if code refers to nonexistent `strategy` or `evaluation` sections.

- [ ] **Step 2: Add failing allowed-diff and hash-identity tests**

Recursively diff v1 and v2 and require every difference to be under one of:

```python
ALLOWED_DIFF_PREFIXES = (
    "/$schema", "/schema_version", "/foundation", "/plan_id", "/plan_hash",
    "/status", "/warnings", "/isolation_policy/relative_paths",
    "/isolation_policy/policy_hash", "/storage_authority", "/supersession",
)
```

Require all policy hashes and the overall self-hash to recompute. Derive `plan_id` from an identity
containing the v1 exact identity, unchanged research policy hashes, new isolation/storage hashes,
v0.62 peeled commit and v0.63 foundation.

- [ ] **Step 3: Run the builder tests and confirm red**

Run the Task 1 command. Expected: import failure for `challenger_replacement_plan_v2`.

- [ ] **Step 4: Implement the minimum v2 builder**

Load the fixed v1 artifact through the v1 production loader, deep-copy only the approved subtrees,
and construct new version/storage/supersession sections. Foundation constants are:

```python
V2_FOUNDATION = {
    "release_tag": "v0.63.0",
    "peeled_commit": "df91e19240df14839125608422489adf3b902e76",
    "package_version": "0.63.0",
    "manifest_version": "1.57.0",
    "build_input_tree_hash": "7fdfd6c69f1342892b222882b76ee4988487a482c958a9cdacf00461b2fd8f19",
    "manifest_hash": "f4a74896a6d7b2166adba86075ef06b8d7986f900a086d04ee2f03754baded4b",
    "manifest_file_sha256": "13bea4bfcf633e767eed73d431e57d496dcee47820aacf92e7b61b0efed5c546",
}
```

The builder performs no filesystem inspection outside reading the committed v1 plan resource, no
process call and no production write. Do not accept caller-supplied policy or path overrides.

- [ ] **Step 5: Implement strict reasons and production loader**

Reuse the v1 duplicate-key, float, canonical-byte, owner, regular-file, hardlink and size rules under
v2-specific reason codes. After Schema/hash validation, independently rerun the canonical subtree
equality and allowed-diff gates; Schema validity alone is insufficient.

- [ ] **Step 6: Add adversarial tests**

Reject recomputed tampering of any byte-equal subtree, authority leaf, service/root identity, old key,
storage authority, supersession reason, v1 binding, policy hash, plan ID or plan hash. Reject v1 bytes
as v2 and v2 bytes through the v1 loader.

- [ ] **Step 7: Run the focused tests to green**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_plan \
  tests.test_challenger_replacement_plan_v2 -v
```

Expected: v1 immutability and every v2 builder/loader test pass.

- [ ] **Step 8: Commit the builder slice**

```bash
git add src/crypto_quant/challenger_replacement_plan_v2.py \
  tests/test_challenger_replacement_plan_v2.py
git commit -m "feat: define replacement preregistration v2"
```

---

## Task 3: Freeze the Supersession Record Contract Without Real Collection

**Files:**

- Create: `src/crypto_quant/challenger_replacement_plan_supersession.py`
- Create: `config/challenger-replacement-plan-supersession-v1.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-plan-supersession-v1.schema.json`
- Create: `tests/test_challenger_replacement_plan_supersession.py`

**Interfaces:**

- Produces:

```python
def build_challenger_replacement_plan_supersession_record(
    *, v2_plan_path: Path, machine_evidence: Mapping[str, Any]
) -> Dict[str, Any]: ...

def load_challenger_replacement_plan_supersession_record(
    path: Path, *, v2_plan_path: Path
) -> Dict[str, Any]: ...
```

The builder is internal to the collector; no public caller may supply individual count, status,
reason, hash, ID or authority fields.

- [ ] **Step 1: Add failing exact-binding and qualification tests**

Require the record to bind the exact v1 constants, dynamically loaded v2 path/file SHA/plan ID/hash,
reason `SUPERSEDED_PRE_START_STORAGE_SAFETY_CORRECTION`, and prohibition
`PLAN_SUPERSESSION_FORBIDDEN_AFTER_FIRST_START_RECEIPT_OR_CANONICAL_EVENT`.

Fixture evidence is:

```python
TEST_EVIDENCE_QUALIFICATION = "TEST_FIXTURE_ONLY_NOT_SUPERSESSION_EVIDENCE"
REAL_EVIDENCE_QUALIFICATION = "REAL_MACHINE_READ_ONLY_SUPERSESSION_PRECONDITION"
```

The formal-record loader must reject the test qualification even when every count is zero.

- [ ] **Step 2: Run and confirm red**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_plan_supersession -v
```

Expected: missing module and Schema failures.

- [ ] **Step 3: Implement strict record Schemas**

Require exact objects for `previous_plan`, `superseding_plan`, `machine_evidence`, `prohibition`,
`authority`, `record_id`, `record_hash`, `status` and `warnings`. Machine evidence requires observed
UTC time, timezone, effective uid, root/plist/service observations, derived start/event counts,
collector action counters and exact launchctl transcript metadata. Every object uses
`additionalProperties: false`.

- [ ] **Step 4: Implement deterministic record identity and loader**

Derive record ID from both exact plan identities, v1/v2 file SHAs, observed machine-evidence hash,
reason and prohibition. Exclude only `record_hash` from self-hash. Recompute every hash and reject
unknown/missing fields, duplicate keys, floats, noncanonical bytes, unsafe paths and ambiguous counts.

- [ ] **Step 5: Add prohibition tests**

Each of the following independently rejects the record:

```text
runtime root present or observation unknown
plist present or observation unknown
service loaded or observation unknown
start receipt count != 0 or unknown
canonical event count != 0 or unknown
state write count != 0 or unknown
collector Runner/market/Broker/order count != 0
```

- [ ] **Step 6: Run the record contract tests to green**

Run the Task 3 command. Expected: Schema, identity, qualification and prohibition tests pass without
touching any production path.

- [ ] **Step 7: Commit the record-contract slice**

```bash
git add src/crypto_quant/challenger_replacement_plan_supersession.py \
  config/challenger-replacement-plan-supersession-v1.schema.json \
  src/crypto_quant/schemas/challenger-replacement-plan-supersession-v1.schema.json \
  tests/test_challenger_replacement_plan_supersession.py
git commit -m "feat: freeze replacement plan supersession contract"
```

---

## Task 4: Implement the Read-Only Real-Machine Collector With No Artifact Yet

**Files:**

- Create: `src/crypto_quant/challenger_replacement_plan_supersession_cli.py`
- Modify: `tests/test_challenger_replacement_plan_supersession.py`

**Interfaces:**

- Produces CLI:

```text
python -m crypto_quant.challenger_replacement_plan_supersession_cli \
  --v2-plan /absolute/repository/path/to/challenger-replacement-plan-v0.64.0.json \
  --output /absolute/repository/path/to/challenger-replacement-plan-supersession-v0.64.0.json
```

CLI arguments select only the reviewed v2 input and no-overwrite output. They do not accept service,
runtime root, plist, count, status, reason, hash, ID, command or transcript overrides.

- [ ] **Step 1: Add failing zero-side-effect collector tests**

Patch only OS/process boundaries in tests and record calls. Require exactly these observations:

```text
datetime.now(timezone.utc)
time.tzname / local UTC offset
os.geteuid()
os.lstat(fixed runtime root)
os.lstat(fixed target plist)
/bin/launchctl print gui/501/local.crypto-quant.challenger-replacement-v1
```

Forbid `mkdir`, `chmod`, `unlink`, `rename`, bootstrap, kickstart, Runner, scheduler, maintenance and
all network APIs. Output is the sole allowed write and must use no-overwrite semantics.

- [ ] **Step 2: Run and confirm red**

Run the Task 3 command. Expected: collector module missing.

- [ ] **Step 3: Implement exact read-only collection**

Require `os.geteuid() == 501`; any other value fails closed before `launchctl` and cannot select a
different service domain. Map runtime-root and plist `FileNotFoundError` to explicit absent
observations. Execute only
`launchctl print`; nonzero “service not found” is accepted only when stderr/stdout match the reviewed
not-loaded class, while unexpected exit or ambiguous transcript fails closed. Capture argv, exit code,
stdout/stderr bytes encoded deterministically, and SHA-256.

Derive internal start/event counts as zero only because the entire fixed runtime root is absent. Do not
claim global machine history. Set collector action counters for Runner, market, Broker, order and state
write to zero because the collector has no such code paths.

- [ ] **Step 4: Implement owner-only no-overwrite output**

Write the record only after the v2 loader and all preconditions pass. Use a repository-targeted atomic
no-overwrite protocol or existing reviewed exact-publish primitive that cannot overwrite an existing
record. Never write under the replacement runtime root.

- [ ] **Step 5: Add real-vs-test separation tests**

Test helper-produced evidence remains test-qualified. Only the unpatched collector path can label
evidence `REAL_MACHINE_READ_ONLY_SUPERSESSION_PRECONDITION`; production code must not expose a
qualification override. Static-scan the CLI signature and parser for count/status/reason/hash/ID inputs.

- [ ] **Step 6: Run focused and adjacent tests**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_plan \
  tests.test_challenger_replacement_plan_v2 \
  tests.test_challenger_replacement_plan_supersession -v
```

Expected: all pass; no production root, plist or formal artifact exists.

- [ ] **Step 7: Commit collector code without generated artifacts**

```bash
git add src/crypto_quant/challenger_replacement_plan_supersession_cli.py \
  tests/test_challenger_replacement_plan_supersession.py
git commit -m "feat: add read-only replacement supersession collector"
```

---

## Task 5: Generate and Freeze the Formal V2 Plan Artifact

**Files:**

- Create: `artifacts/challenger-replacement/challenger-replacement-plan-v0.64.0.json`
- Modify: `tests/test_challenger_replacement_plan_v2.py`

**Interfaces:**

- Consumes: fully tested `build_challenger_replacement_plan_v2()` and v2 loader.
- Produces: exact canonical v2 plan bytes required by the real-machine collector.

- [ ] **Step 1: Re-run all pre-artifact design/Schema tests**

Run the Task 4 focused command. Expected: all pass. Stop if any test fails; artifact generation is
forbidden before this gate.

- [ ] **Step 2: Generate the plan from the parameterless builder**

Use a repository script or one-shot module that writes exactly:

```python
canonical_json(build_challenger_replacement_plan_v2()).encode("utf-8") + b"\n"
```

to the fixed artifact path with no overwrite. Do not hand-edit plan ID, plan hash, policy hash or file
bytes.

- [ ] **Step 3: Add committed-artifact regression**

Require builder bytes equal artifact bytes after applying the repository newline convention, load the
artifact through the v2 production loader, recompute file SHA, and rerun every v1/v2 canonical subtree
equality assertion against the committed artifact.

- [ ] **Step 4: Prove v0.62 remains unchanged**

Recompute v0.62 file SHA and compare exact bytes against `git show v0.62.0:<path>`. Verify
`git rev-parse v0.62.0^{}` equals `e0a9b3...`. Any mismatch stops the version.

- [ ] **Step 5: Run focused tests to green**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_plan_v2 -v
```

Expected: exact artifact regression passes.

- [ ] **Step 6: Commit only the formal plan artifact and regression**

```bash
git add artifacts/challenger-replacement/challenger-replacement-plan-v0.64.0.json \
  tests/test_challenger_replacement_plan_v2.py
git commit -m "feat: freeze replacement preregistration v2 artifact"
```

---

## Task 6: Perform the One Real Read-Only Check and Freeze the Supersession Record

**Files:**

- Create: `artifacts/challenger-replacement/challenger-replacement-plan-supersession-v0.64.0.json`
- Modify: `tests/test_challenger_replacement_plan_supersession.py`

**Interfaces:**

- Consumes: exact v2 plan artifact and the fixed v1 identity.
- Produces: the sole real-machine supersession record. This task is a release gate, not a unit-test fixture.

- [ ] **Step 1: Read-only precheck repository and machine identity**

Verify clean intended worktree, v0.63 baseline ancestry, unchanged v0.62 tag, effective uid, and absence
of runtime root/plist/service. Do not create the missing paths. If any observation is present or
ambiguous, stop without output.

- [ ] **Step 2: Run the production collector exactly once**

Run the CLI with only the two reviewed absolute paths. Do not patch, inject or manually pass machine
facts. The CLI must fail rather than overwrite an existing output.

- [ ] **Step 3: Replay the exact record with the production loader**

Load the record against the exact v2 plan, verify real evidence qualification, both plan bindings,
record ID/hash/file SHA, zero-state facts, transcript hashes, reason and prohibition.

- [ ] **Step 4: Add committed-record regression**

Test exact committed bytes through the production loader. Test fixtures remain in temporary directories
and retain the test-only qualification.

- [ ] **Step 5: Run focused tests to green**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_plan_v2 \
  tests.test_challenger_replacement_plan_supersession -v
```

Expected: formal plan and formal real-machine record both replay exactly.

- [ ] **Step 6: Commit the immutable record**

```bash
git add artifacts/challenger-replacement/challenger-replacement-plan-supersession-v0.64.0.json \
  tests/test_challenger_replacement_plan_supersession.py
git commit -m "feat: record pre-start replacement plan supersession"
```

---

## Task 7: Publish Governance Documentation and Release Metadata

**Files:**

- Create: `docs/adr/0064-replacement-challenger-plan-v2-storage-supersession.md`
- Create: `docs/implementation-status-v0.64.0.md`
- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `src/crypto_quant/__init__.py`
- Modify: `src/crypto_quant/build.py`
- Modify: `config/evaluator-build-manifest-v1.json`

**Interfaces:**

- Consumes: exact v1 plan, exact v2 plan and exact supersession record.
- Produces: honest v0.64 release identity; no runtime eligibility.

- [ ] **Step 1: Write ADR-0064**

Record the infeasibility of strict v0.62 storage under the approved security model, explicit pre-start
supersession, canonical subtree equality, event-only authority, non-authoritative exports, old-plan
immutability, zero-state machine evidence and post-start supersession prohibition. State that v0.62 is
historical and superseded, not silently amended and not a failed research cohort.

- [ ] **Step 2: Write implementation status**

Status must say:

```text
PLAN_FROZEN_REPLACEMENT_V2_NOT_STARTED
```

List both plan identities and file SHAs, supersession record identity/hash/SHA, real zero-state facts,
and explicit ineligibility for runtime, deployment, start, 90-day completion, profitability, AI
advantage, Canary and live trading.

- [ ] **Step 3: Update README and release metadata**

Set package version `0.64.0`, advance manifest version once, register all new code/Schema/artifact/docs
files in the build file set, and recompute manifest hashes through the repository validation workflow.
Do not add runtime or deployment claims.

- [ ] **Step 4: Run focused, adjacent and full validation once**

Run:

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_plan \
  tests.test_challenger_replacement_plan_v2 \
  tests.test_challenger_replacement_plan_supersession -v
PYTHONPATH=src python3 -m compileall -q src/crypto_quant tests
make validate
PYTHONPATH=src python3 -m unittest discover -s tests
git diff --check
```

Expected: all commands pass. Run the full suite only once for this final code state.

- [ ] **Step 5: Prove scope and old-plan immutability**

Require no replacement runtime/event/deployment/exporter implementation in the diff, no production
root/plist/service, and exact v0.62 bytes/tag identity unchanged. Verify no code or doc claims cohort
start, Paper completion, profitability, AI advantage, Canary or live eligibility.

- [ ] **Step 6: Commit governance and metadata**

```bash
git add docs/adr/0064-replacement-challenger-plan-v2-storage-supersession.md \
  docs/implementation-status-v0.64.0.md README.md pyproject.toml \
  src/crypto_quant/__init__.py src/crypto_quant/build.py \
  config/evaluator-build-manifest-v1.json
git commit -m "docs: publish replacement plan v2 governance"
```

---

## Task 8: Review, PR, Main CI and Annotated Tag

**Files:**

- No intended source changes unless review finds a Critical or Important issue.

**Interfaces:**

- Produces: reviewed `v0.64.0` plan-only release exactly aligned to merged main.

- [ ] **Step 1: Perform one complete independent review**

Review v1 immutability, allowed-diff gate, Schema/loader strictness, collector read-only boundary,
real-vs-test qualification, zero-state evidence, post-start prohibition and absence of runtime scope.
Critical and Important findings must reach zero. After fixes, review only changed areas.

- [ ] **Step 2: Re-run proportionate verification after review fixes**

Run focused tests for touched files; run the full suite again only if production code changed after its
single final-state run. Never rerun the same unchanged full state mechanically.

- [ ] **Step 3: Verify GitHub write authority before mutation**

Check target private repository, exact origin URL, remote main, authenticated ADMIN permission, intended
branch and clean worktree. A connector 404 for the private repository may fall back only to authenticated
`gh` after target identity is proven.

- [ ] **Step 4: Create Draft PR and wait for Python 3.9/3.12 CI**

Push `codex/v0.64-replacement-plan-v2`, create a Draft PR, verify its exact head commit, and wait for both
Python jobs. Do not merge on failure or ambiguity.

- [ ] **Step 5: Merge, verify main CI and tag identity**

Merge only after approval and green PR CI. Wait for merged-main CI, then create annotated `v0.64.0`
exactly at merged main. Push the tag and verify remote main and peeled tag commit are identical.

- [ ] **Step 6: Reconfirm the non-start boundary**

After release, report only plan supersession completion. Do not install, start, create production paths,
invoke Runner or begin 90-day timing. Record that v0.65 remains the Nautilus Spike and v0.66 is the
earliest replacement runtime version.
