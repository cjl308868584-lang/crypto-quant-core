# Replacement Challenger Preregistration V2 Supersession Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish v0.64.0 as an explicit plan-only superseding preregistration v2 only when a current `NO_OBSERVABLE_REPLACEMENT_STATE_AT_COLLECTION` snapshot, immutable Git/release-history evidence, and an accountable owner pre-start history attestation are all bound and reviewed.

**Architecture:** A separate parameterless v2 builder copies the research-bearing v0.62 canonical subtrees exactly, binds the exact v0.63 predecessor foundation, and changes only version, storage paths, event-log authority, and supersession metadata. Schema/loaders validate canonical structure, hashes, claims, and cross-artifact bindings but do not prove collection provenance or the truth of historical statements. A dedicated OS-process collector records only current machine and Git observations; an independently reviewed owner attestation supplies the accountable historical declaration, and a fixed-path crash-safe publisher durably publishes the four formal governance artifacts.

**Tech Stack:** Python 3.9+, standard-library `json`/`hashlib`/`pathlib`/`os`/`subprocess`, Draft 2020-12 JSON Schema, existing canonical JSON and strict-loader conventions, `unittest`, Make validation, Git/GitHub Actions.

## Global Constraints

- Work only from annotated `v0.63.0` peeled commit `df91e19240df14839125608422489adf3b902e76` on isolated branch `codex/v0.64-replacement-plan-v2`.
- Never modify, regenerate, delete, or force-move v0.62 plan bytes, Schema, ADR, status document, annotated tag, tag object, or peeled commit.
- v0.62 plan file SHA-256 is `d450d1e9f8dc422eb5a93beb8a5ffbb1746a4a6d1facb3c5a20a76f4bd527734`; plan ID/hash are the exact values in the design.
- v0.64 is governance/plan-only. Other than the private four-fixed-path governance publisher in this plan, do not add replacement runtime, event implementation, SQLite, runtime artifact publisher, deployment, installer, observer, exporter, evaluator, Runner, scheduler, maintenance, market, account, Broker, credential, order, or production-state code.
- Never create the replacement runtime root or plist and never load/bootstrap/kickstart its service.
- Preserve all v0.62 research-bearing canonical subtree bytes identified in the design.
- Use `state/challenger-replacement-events-v1` as the sole future authority and `exports` only as a non-authoritative, reconstructible future output root.
- Generate the formal v2 plan artifact only after all builder, Schema, equality, loader, and supersession-contract tests pass.
- Generate formal machine evidence only after the committed-candidate v2 plan artifact passes its production loader; generate the owner attestation only after the owner reviews its exact declaration and the linked evidence hashes; generate the supersession record only after both pass strict loaders.
- Machine evidence proves only `NO_OBSERVABLE_REPLACEMENT_STATE_AT_COLLECTION`. An absent runtime root derives only current absent-tree counts; it does not prove historical zero. Collector state-write count describes only collector actions.
- Historical pre-start status requires the accountable owner attestation and observable immutable Git/release-history evidence. Missing or ambiguous provenance fails closed; no code or loader claims to prove the attestation true.
- Test fixtures use `TEST_FIXTURE_ONLY_NOT_SUPERSESSION_EVIDENCE`. Schema/loaders reject mismatched qualification claims but cannot prove that structurally valid bytes came from an unpatched process; independent-process transcripts, owner approval, review and commit ceremony enforce provenance.
- V2 `foundation` is the exact v0.63 predecessor object. V0.64 build/manifest identity is bound later by release manifest/status/ADR and never enters plan, attestation, or record hashes.
- All formal governance artifacts use the dedicated fixed-path staging publisher; direct writes to canonical final and reuse of `system_paper_evidence.publish_owner_exact` are forbidden.
- Darwin uses only `renameatx_np(..., RENAME_EXCL=0x00000004)`; Linux uses only `renameat2(..., RENAME_NOREPLACE=1)`, both through controlled `ctypes`. Missing/incorrect platform semantics fail closed with no rename/hardlink/direct-final fallback.
- No formal artifact may be generated until the current platform feasibility gate passes. The 2026-08-13 transport amendment replaces only the billing-blocked pre-artifact Linux Draft-PR jobs with an exact-byte-bound public Linux witness; the target Mac must independently pass the Darwin gate before Task 5. Neither substitutes for the other.
- After Task 5 commits the plan, freeze `HEAD=H` through collection, attestation and record assembly. Intermediate Git status must match the exact candidate-state allowlist; only `C0` and post-commit `C4` are called clean.
- Protocol staging is separately inventoried even though its exact filename pattern is ignored by Git. A sealed orphan is never modified and does not prevent an exact publisher retry, but any remaining orphan blocks attestation, record assembly, commit and release.
- An orphan-blocked worktree is retained unchanged as failure evidence. Recovery starts from the exact pre-artifact commit in a new isolated worktree and repeats the ceremony; it never deletes or modifies the orphan.
- Keep `v0.65.0` reserved for the approved single end-to-end NautilusTrader Spike; replacement three-stage runtime is `v0.66.0` or later.
- Run one local full suite for the final code state, one complete independent review, targeted re-review after fixes, PR Python 3.9/3.12 CI, merged-main CI, and annotated-tag identity verification.

### 2026-08-13 pre-artifact Linux transport amendment

Private PR #32 run `31436609135` did not execute tests because the private Actions quota blocked runner
allocation. Preserve it with the exact status:

```text
PRIVATE_PR_CI_NOT_EXECUTED_BILLING_BLOCKED = run 31436609135
PUBLIC_SOURCE_CANDIDATE_F = reviewed private source commit exported byte-for-byte
PUBLIC_LINUX_PORTABILITY_WITNESS_NOT_PRIVATE_PR_CHECK = independent bound transport
POST_WITNESS_PRIVATE_CANDIDATE_G = strict descendant of F with unchanged public-source blobs
```

The private Draft PR remains the code-review and release object. The public run is a permanently
auditable, minimal Linux portability witness for exact files from `F`; it is not a private PR check or
full-project CI. After the run, `G` may add only the sealed witness/regression/build-manifest delta and
must prove strict `F` ancestry plus unchanged public-source blobs. No Task 5 artifact may exist before
the target-Mac Darwin gate, public Python 3.9/3.12 Linux witness, strict witness replay and `F`→`G`
unchanged-blob verification all pass.

Only this unavailable pre-artifact transport changes. Test semantics, thresholds, private release
authority, v0.62 bytes/tag, the owner-approval gate, C0-C4 and the Task 5-8 evidence ceremony remain
unchanged. The public repository and push require the separate exact eight-file approval package; this
amendment grants no external-write authority.

---

## File Map

### New v2 plan unit

- `src/crypto_quant/challenger_replacement_plan_v2.py`: parameterless v2 builder, semantic reasons and strict plan loader.
- `src/crypto_quant/schemas/challenger-replacement-plan-v2.schema.json`: package Schema.
- `config/challenger-replacement-plan-v2.schema.json`: byte-identical config Schema mirror.
- `tests/test_challenger_replacement_plan_v2.py`: v0.62 equality, v2 storage, hashing, Schema and loader tests.

### New supersession unit

- `src/crypto_quant/challenger_replacement_plan_supersession.py`: strict machine-evidence, owner-attestation and record models, hash/ID derivation, binding validation and loaders.
- `src/crypto_quant/schemas/challenger-replacement-supersession-machine-evidence-v1.schema.json`: package machine-evidence Schema.
- `config/challenger-replacement-supersession-machine-evidence-v1.schema.json`: byte-identical config Schema mirror.
- `src/crypto_quant/schemas/challenger-replacement-owner-attestation-v1.schema.json`: package owner-attestation Schema.
- `config/challenger-replacement-owner-attestation-v1.schema.json`: byte-identical config Schema mirror.
- `src/crypto_quant/schemas/challenger-replacement-plan-supersession-v1.schema.json`: package record Schema.
- `config/challenger-replacement-plan-supersession-v1.schema.json`: byte-identical config Schema mirror.
- `src/crypto_quant/challenger_replacement_plan_supersession_cli.py`: parameterless read-only machine/Git collector, owner-attestation ceremony and record assembly commands over fixed reviewed paths.
- `src/crypto_quant/challenger_replacement_supersession_publish.py`: private fixed-path staging/readback/fsync/no-replace publisher used only by the four v0.64 governance artifacts.
- `.gitignore`: exact v0.64 staging basename rule; ignored staging remains subject to explicit dirfd inventory and is never treated as absent.
- `tests/test_challenger_replacement_plan_supersession.py`: fixture, collector boundary, no-side-effect and record tests.

### Generated only after test gates

- `artifacts/challenger-replacement/challenger-replacement-plan-v0.64.0.json`: exact v2 plan artifact.
- `artifacts/challenger-replacement/challenger-replacement-supersession-machine-evidence-v0.64.0.json`: current snapshot plus immutable Git/release-history transcripts.
- `artifacts/challenger-replacement/challenger-replacement-owner-attestation-v0.64.0.json`: accountable owner declaration bound to both plans and evidence hashes.
- `artifacts/challenger-replacement/challenger-replacement-plan-supersession-v0.64.0.json`: exact supersession record binding plan, evidence and attestation.

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

The allowed-prefix test is necessary but not sufficient. Require `foundation == V2_FOUNDATION` as an
exact object. Require `warnings` to equal the six v1 strings in their original order and value plus
exactly one final `V0_62_SUPERSEDED_PRE_START_STORAGE_SAFETY_CORRECTION`; deletion, rewrite, reorder or
an eighth warning fails. Require all policy hashes and the overall self-hash to recompute. Derive
`plan_id` from an identity containing the v1 exact identity, unchanged research policy hashes, new
isolation/storage hashes, v0.62 peeled commit and exact v0.63 predecessor foundation.

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

This exact object is the complete plan foundation; it contains no v0.64 build or manifest identity.
The builder performs no filesystem inspection outside reading the committed v1 plan resource, no
process call and no production write. Do not accept caller-supplied policy or path overrides.

- [ ] **Step 5: Implement strict reasons and production loader**

Reuse the v1 duplicate-key, float, canonical-byte, owner, regular-file, hardlink and size rules under
v2-specific reason codes. After Schema/hash validation, independently rerun the canonical subtree
equality and allowed-diff gates; Schema validity alone is insufficient.

- [ ] **Step 6: Add adversarial tests**

Reject recomputed tampering of any byte-equal subtree, authority leaf, service/root identity, old key,
storage authority, supersession reason, v1 binding, foundation field, warning value/order/count, policy
hash, plan ID or plan hash. Reject v1 bytes as v2 and v2 bytes through the v1 loader.

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

## Task 3: Freeze Machine Evidence, Owner Attestation and Record Contracts

**Files:**

- Create: `src/crypto_quant/challenger_replacement_plan_supersession.py`
- Create: `config/challenger-replacement-supersession-machine-evidence-v1.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-supersession-machine-evidence-v1.schema.json`
- Create: `config/challenger-replacement-owner-attestation-v1.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-owner-attestation-v1.schema.json`
- Create: `config/challenger-replacement-plan-supersession-v1.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-plan-supersession-v1.schema.json`
- Create: `tests/test_challenger_replacement_plan_supersession.py`

**Interfaces:**

- Produces:

```python
def build_challenger_replacement_plan_supersession_record(
    *,
    v2_plan_path: Path,
    machine_evidence_path: Path,
    owner_attestation_path: Path,
    ceremony_precondition: Mapping[str, Any],
) -> Dict[str, Any]: ...

def load_challenger_replacement_supersession_machine_evidence(
    path: Path,
) -> Dict[str, Any]: ...

def load_challenger_replacement_owner_attestation(
    path: Path, *, v2_plan_path: Path, machine_evidence_path: Path
) -> Dict[str, Any]: ...

def load_challenger_replacement_plan_supersession_record(
    path: Path,
    *,
    v2_plan_path: Path,
    machine_evidence_path: Path,
    owner_attestation_path: Path,
) -> Dict[str, Any]: ...
```

The record builder is internal to the fixed-path assembly command; no public caller or CLI may supply
individual count, history claim, status, reason, hash, ID, qualification, service identity or
authority fields. Python callers can still construct or monkeypatch bytes; loaders validate structure
and bindings, not provenance or historical truth.

- [ ] **Step 1: Add failing exact-binding and qualification tests**

Require machine evidence to distinguish current observations from history: exact observation
`NO_OBSERVABLE_REPLACEMENT_STATE_AT_COLLECTION`, absent current runtime root/plist, not-loaded current
service, absent-tree-derived current counts, and collector-only write/Runner/market/Broker/order
counters. No field named or described as historical production state-write count is allowed.

Require owner attestation to bind the exact v1 constants, dynamically loaded v2 path/file SHA/plan
ID/hash, machine-evidence hash, Git-history-evidence hash, fixed signer identity
`cjl308868584-lang`/`chenm4`/uid `501`, exact declaration and explicit acknowledgement from the design.
Its exact type is `ACCOUNTABLE_OWNER_PRE_START_HISTORY_ATTESTATION_V1`.
Require the record to bind those artifacts, reason
`SUPERSEDED_PRE_START_STORAGE_SAFETY_CORRECTION`, and prohibition
`PLAN_SUPERSESSION_FORBIDDEN_AFTER_FIRST_START_RECEIPT_OR_CANONICAL_EVENT`.

Fixture evidence is:

```python
TEST_EVIDENCE_QUALIFICATION = "TEST_FIXTURE_ONLY_NOT_SUPERSESSION_EVIDENCE"
REAL_EVIDENCE_QUALIFICATION = "REAL_MACHINE_READ_ONLY_SUPERSESSION_PRECONDITION"
```

Formal loaders reject a test qualification claim even when every observed count is zero. Tests must
state the limit explicitly: a loader cannot prove that identical bytes were not fabricated or that the
attestation is true.

Also commit these exact fixed-path regression skeletons before any formal artifact exists:

```text
test_committed_supersession_machine_evidence_exact
test_committed_owner_attestation_exact
test_committed_plan_supersession_record_exact
```

Each method may use only a method-level `skipUnless` for its own exact fixed formal-artifact path with
reason `FIXED_FORMAL_SUPERSESSION_ARTIFACT_NOT_YET_PUBLISHED`. It must not catch loader exceptions,
skip a class/module, inspect an alternate path or treat any other failure as absence. Once its fixed
file exists, the production loader and all exact identity/binding assertions must execute.

- [ ] **Step 2: Run and confirm red**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_plan_supersession -v
```

Expected: missing module and Schema failures.

- [ ] **Step 3: Implement the three strict Schemas**

Machine evidence requires observed UTC time, timezone, effective uid, current root/plist/service
observations, explicitly current absent-tree-derived counts, collector action counters, and exact
launchctl and Git command transcript metadata. Owner attestation requires signer identity/uid,
canonical signed time, exact declaration/acknowledgement, both plan bindings, both evidence hashes,
and the exact `C1_EVIDENCE_ONLY` ceremony precondition. The record requires the exact
`C2_EVIDENCE_ATTESTATION_ONLY` ceremony precondition plus exact objects for
`previous_plan`, `superseding_plan`, `machine_evidence_binding`,
`owner_attestation_binding`, `prohibition`, `authority`, `record_id`, `record_hash`, `status` and
`warnings`. Every ceremony precondition binds the candidate HEAD/status transcripts, empty staging
inventory and the allowlisted finals' file SHA plus stat identity; device/inode/mtime/ctime nanosecond
values use canonical unsigned decimal strings because native values may exceed the exact JSON integer
range.
Every object uses `additionalProperties: false`.

- [ ] **Step 4: Implement deterministic record identity and loader**

Derive record ID from both exact plan identities and file SHAs, machine-evidence hash,
owner-attestation hash, Git-history-evidence hash, reason and prohibition. Exclude only `record_hash`
from self-hash. The record identity and self-hash also bind the full `C2` ceremony precondition. The
record file SHA is external and must not be a record field. Recompute every hash
and reject unknown/missing fields, duplicate keys, floats, noncanonical bytes, unsafe paths and
ambiguous observations. V0.64 build/manifest identity is not a plan, attestation or record field.

- [ ] **Step 5: Add prohibition tests**

Each of the following independently rejects formal assembly or loading:

```text
observation != NO_OBSERVABLE_REPLACEMENT_STATE_AT_COLLECTION
current runtime root present or observation unknown
current plist present or observation unknown
current service loaded or observation unknown
current absent-tree-derived start/event count != 0 or unknown
collector state-write/Runner/market/Broker/order count != 0 or unknown
owner attestation absent, ambiguous, test-qualified or not explicitly acknowledged
owner identity/uid/declaration/signed time or plan/evidence binding differs
Git/release-history transcript absent, ambiguous or disagrees with frozen identities
```

Also assert that a structurally valid fabricated fixture can pass pure structure/hash validation when
labeled accordingly; this negative-boundary test prevents documentation or code from claiming that a
loader proves collection provenance.

- [ ] **Step 6: Run the record contract tests to green**

Run the Task 3 command. Expected: Schema, identity, qualification and prohibition tests pass without
touching any production path.

- [ ] **Step 7: Commit the record-contract slice**

```bash
git add src/crypto_quant/challenger_replacement_plan_supersession.py \
  config/challenger-replacement-supersession-machine-evidence-v1.schema.json \
  src/crypto_quant/schemas/challenger-replacement-supersession-machine-evidence-v1.schema.json \
  config/challenger-replacement-owner-attestation-v1.schema.json \
  src/crypto_quant/schemas/challenger-replacement-owner-attestation-v1.schema.json \
  config/challenger-replacement-plan-supersession-v1.schema.json \
  src/crypto_quant/schemas/challenger-replacement-plan-supersession-v1.schema.json \
  tests/test_challenger_replacement_plan_supersession.py
git commit -m "feat: freeze replacement plan supersession contract"
```

---

## Task 4: Implement Fixed Collector and Crash-Safe Supersession Publisher

**Files:**

- Create: `src/crypto_quant/challenger_replacement_plan_supersession_cli.py`
- Create: `src/crypto_quant/challenger_replacement_supersession_publish.py`
- Modify: `.gitignore`
- Modify: `src/crypto_quant/challenger_replacement_plan_supersession.py`
- Modify: owner-attestation and supersession-record Schema mirrors from Task 3
- Modify: this plan and its design spec to close the discovered C1/C2 transcript-contract omission
- Modify: `tests/test_challenger_replacement_plan_supersession.py`

**Interfaces:**

- Produces parameterless fixed-path commands:

```text
python -m crypto_quant.challenger_replacement_plan_supersession_cli collect-machine-evidence
python -m crypto_quant.challenger_replacement_plan_supersession_cli record-owner-attestation
python -m crypto_quant.challenger_replacement_plan_supersession_cli assemble-record
```

The subcommand is the only argument. The module derives the repository root from its reviewed module
location, verifies the exact candidate-state-machine HEAD/status/final/staging precondition and fixed
relative input/output paths, and rejects
symlink ancestry or a different Git root. It accepts no repository root, input/output path, service,
runtime root, plist, count, history claim, signer identity, status, reason, hash, ID, command,
transcript or qualification override.

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

Add fixed Git observations for the v0.62/v0.63 annotated tag objects and peeled commits, v0.62 exact
plan identity, C0-empty-status reviewed v0.64 candidate/ancestry, and committed history under
`artifacts/challenger-replacement/`, `docs/adr/0062-replacement-challenger-preregistration-isolation.md` and
`docs/implementation-status-v0.62.0.md`. Capture exact argv, exit code, stdout/stderr bytes/hash. State
in tests that these are repository observations, not proof of machine execution history.

The collector builds these exact argv tuples after deriving and validating `reviewed_repo_root` from
the reviewed module location:

```python
GIT_ARGV = (
    ("/usr/bin/git", "-C", str(reviewed_repo_root), "rev-parse", "v0.62.0"),
    ("/usr/bin/git", "-C", str(reviewed_repo_root), "cat-file", "-t", "v0.62.0"),
    ("/usr/bin/git", "-C", str(reviewed_repo_root), "rev-parse", "v0.62.0^{}"),
    ("/usr/bin/git", "-C", str(reviewed_repo_root), "rev-parse", "v0.63.0"),
    ("/usr/bin/git", "-C", str(reviewed_repo_root), "cat-file", "-t", "v0.63.0"),
    ("/usr/bin/git", "-C", str(reviewed_repo_root), "rev-parse", "v0.63.0^{}"),
    ("/usr/bin/git", "-C", str(reviewed_repo_root), "rev-parse", "HEAD"),
    ("/usr/bin/git", "-C", str(reviewed_repo_root), "merge-base", "--is-ancestor", "v0.63.0", "HEAD"),
    ("/usr/bin/git", "-C", str(reviewed_repo_root), "status", "--porcelain=v1", "--untracked-files=all"),
    (
        "/usr/bin/git", "-C", str(reviewed_repo_root), "status", "--porcelain=v1",
        "--untracked-files=all", "--ignored=matching", "--", "artifacts/challenger-replacement/",
    ),
    (
        "/usr/bin/git", "-C", str(reviewed_repo_root), "show",
        "v0.62.0:artifacts/challenger-replacement/challenger-replacement-plan-v0.62.0.json",
    ),
    (
        "/usr/bin/git", "-C", str(reviewed_repo_root), "log", "--all", "--full-history",
        "--format=%H", "--", "artifacts/challenger-replacement/",
        "docs/adr/0062-replacement-challenger-preregistration-isolation.md",
        "docs/implementation-status-v0.62.0.md",
    ),
)
```

Both tag `cat-file -t` results must be `tag`; each transcript records argv, exit code and exact
stdout/stderr bytes or their canonical encoding plus SHA-256. The empty status result proves only that
the intended worktree was in `C0_PLAN_COMMITTED_CLEAN` immediately before evidence staging creation.

Forbid `mkdir`, `chmod`, `unlink`, bootstrap, kickstart, Runner, scheduler, maintenance and all network
APIs. The only allowed mutation is through the private fixed-path publisher after all observations
pass.

- [ ] **Step 2: Run and confirm red**

Run the Task 3 command. Expected: collector module missing.

- [ ] **Step 3: Implement exact read-only collection**

Require `os.geteuid() == 501`; any other value fails closed before `launchctl` and cannot select a
different service domain. Map runtime-root and plist `FileNotFoundError` to explicit absent
observations. Execute only
`launchctl print`; nonzero “service not found” is accepted only when stderr/stdout match the reviewed
not-loaded class, while unexpected exit or ambiguous transcript fails closed. Capture argv, exit code,
stdout/stderr bytes encoded deterministically, and SHA-256.

Set observation to `NO_OBSERVABLE_REPLACEMENT_STATE_AT_COLLECTION`. Derive current-tree start/event
counts as zero only because the entire fixed runtime root is currently absent. Never call them
historical counts. Set collector-only action counters for state write, Runner, market, Broker and order
to zero because the collector has no such code paths.

- [ ] **Step 4: Add failing fixed-path and publication crash tests**

Require every derived input/output to remain under the exact reviewed repository and exact artifact
filename. Require the retained artifact parent to be a regular directory owned by uid `501` with mode
`0755`. Add exactly this ignore rule and no broader directory rule:

```gitignore
/artifacts/challenger-replacement/.v064-supersession-*.staging
```

Inventory accepts only basenames matching
`\A\.v064-supersession-(plan|machine-evidence|owner-attestation|supersession-record)-[0-9a-f]{64}-[0-9a-f]{32}\.staging\Z`.

Test the exact candidate states: after the plan commit `C0` is empty at `HEAD=H`; collect produces
only evidence; attest requires exactly evidence and produces exactly evidence+attestation; assemble
requires those two and produces exactly three; committing those exact three produces empty status at
`H2`. Reject arbitrary cwd, alternative Git root, symlink ancestor, wrong owner/mode, unexpected
tracked/untracked path, mutated allowlisted final or mismatched HEAD before staging.
Use byte-sorted exact porcelain tuples: C1 contains only
`?? artifacts/challenger-replacement/challenger-replacement-supersession-machine-evidence-v0.64.0.json`;
C2 adds only
`?? artifacts/challenger-replacement/challenger-replacement-owner-attestation-v0.64.0.json`; C3 adds
only `?? artifacts/challenger-replacement/challenger-replacement-plan-supersession-v0.64.0.json`.

At each crash point—partial staging write, file-fsync boundary, no-replace boundary and directory-fsync
boundary—start a fresh process. Before every create, emit the exact staging basename in the command
transcript. Inventory the ignored staging namespace independently through the retained dirfd. A fresh
process classifies up to 64 exact-grammar, regular, uid-501/mode-0644/nlink-1, bounded-size entries as
`SEALED_UNTRUSTED_PROTOCOL_NAMESPACE_ENTRY` without claiming creator provenance or reading their
contents. Such an orphan does not block a new-nonce idempotent retry,
but fresh recovery never reads, writes, chmods, unlinks, renames or quarantines it. Retry may publish
the exact final, then must return `RECOVERY_EVIDENCE_PRESENT_RELEASE_BLOCKED`; later subcommands and
release stay blocked while any orphan exists. A nonconforming or 65th staging entry fails closed. A
visible exact trusted final requires directory fsync plus identity replay before already-published.
Different bytes and symlink/hardlink/FIFO/socket/directory/wrong-owner/wrong-mode/extra-link finals fail
without blocking or altering external sentinel bytes/mode/size/mtime/ctime/inode/nlink. Missing
`O_NOFOLLOW`, `O_DIRECTORY` or `O_NONBLOCK` fails as unsupported without downgraded flags.
Precreate an exact-grammar regular nlink-1 sentinel and snapshot bytes/mode/size/mtime/ctime/dev/ino/nlink;
fresh retry must seal it as untrusted, leave every snapshot field unchanged, publish via a different
nonce, and return the release-blocked status. Precreated symlink/hardlink/nonregular staging entries
must fail before retry and likewise leave their external sentinels unchanged.
Assert normal no-crash publication removes its current staging name through atomic rename and leaves
an empty staging inventory; only that path may enter the next candidate state.

- [ ] **Step 5: Implement the private artifact-specific publisher**

Do not call `system_paper_evidence.publish_owner_exact` and do not open a canonical final for direct
write. Retain a validated parent dirfd; create a same-directory noncanonical nonce staging file with
`O_CREAT|O_EXCL|O_RDWR|O_NOFOLLOW` and requested mode `0644`; verify actual uid `501`, mode `0644` and
nlink `1` without path chmod; handle short write/EINTR; read back exact bytes from the same fd;
verify size/hash/identity; fsync the file; then use exactly one platform primitive:

```text
Darwin renameatx_np(dirfd, staging, dirfd, final, RENAME_EXCL=0x00000004)
Linux  renameat2(dirfd, staging, dirfd, final, RENAME_NOREPLACE=1)
```

Resolve the current-platform symbol only through `ctypes.CDLL(None, use_errno=True)` with signature
`c_int, c_char_p, c_int, c_char_p, c_uint -> c_int`. Missing symbol or
`ENOSYS`/`EOPNOTSUPP`/`ENOTSUP` maps to
`CHALLENGER_REPLACEMENT_SUPERSESSION_ATOMIC_NOREPLACE_UNSUPPORTED`. Never call `os.rename`,
`os.replace`, hardlink, a raw syscall number or a non-no-replace fallback. After successful no-replace,
fsync the parent directory and revalidate parent/final before success. Existing final opens use
`O_RDONLY|O_NOFOLLOW|O_NONBLOCK` and require regular file, uid `501`, mode `0644`, nlink `1` and bounded
size before read. Every fd close
is attempted exactly once; fsync/close/identity failure never returns success.

Keep the module private and expose only the four fixed artifact publications. Do not create a generic
path/data publisher API.

The implementation and tests use the design's baseline threat model: they cover untrusted existing
objects, observable attachment replacement and cooperating publisher races. They must not claim that
`renameatx_np`/`renameat2` atomically binds the source pathname to an already-held staging fd or that
the boundary resists a persistent malicious same-UID directory-entry swapper. Such a conflict may
leave forensic bytes but can never authorize commit/release; the strong-adversary solution requires a
separate OS isolation boundary and is outside v0.64.

- [ ] **Step 6: Add platform feasibility and provenance tests**

In owner-only temporary directories, actual current-platform tests must prove: two fresh processes
racing the same final yield exactly one success and one `EEXIST`; an existing final keeps exact
bytes/dev/ino; source/final use the same retained dirfd; and file-fsync/no-replace/dir-fsync crash
boundaries replay as specified. Patch symbol absence and unsupported errno to prove fixed unsupported
reasons and zero fallback calls. Static-scan for forbidden `os.rename`, `os.replace`, hardlink and
syscall-number paths.

Darwin tests call actual `renameatx_np`; Linux tests call actual `renameat2`. Platform skips may skip
only the other operating system, never the current one. Linux Python 3.9/3.12 witness must execute the
actual Linux test; target-Mac execution must execute the actual Darwin test. A mock success is not a
platform gate.

Test helper-produced evidence remains test-qualified. Static-scan the CLI signature/parser for every
forbidden override and prove only the three fixed subcommands exist. Test that the owner command shows
the exact declaration and exact plan/evidence hashes, requires the exact acknowledgement
`I_SIGN_AND_ACCEPT_ACCOUNTABILITY_FOR_THE_EXACT_DECLARATION` from an interactive ceremony, fixes the
signer to `cjl308868584-lang`/`chenm4`/uid `501`, and fails without explicit acknowledgement.

Tests must say explicitly that monkeypatching/direct Python calls can fabricate identical bytes; the
governance gate—independent process, exact transcript, owner approval, review and commit ceremony—not
the loader, determines formal provenance.

- [ ] **Step 7: Run focused and adjacent tests**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_plan \
  tests.test_challenger_replacement_plan_v2 \
  tests.test_challenger_replacement_plan_supersession -v
```

Expected: all applicable tests pass; only the opposite-OS primitive test may use the platform skip
defined in Step 6. No production root, plist or formal artifact exists. Before formal publication,
only the three named fixed-path regression methods from Task 3 may additionally report the exact
`FIXED_FORMAL_SUPERSESSION_ARTIFACT_NOT_YET_PUBLISHED` skip. No class/module-wide skip, caught loader
failure or additional artifact-absence skip is allowed. Tests may publish only under owner-only
temporary fixture roots.

- [ ] **Step 8: Commit collector and fixed publisher without generated artifacts**

```bash
git add .gitignore src/crypto_quant/challenger_replacement_plan_supersession_cli.py \
  src/crypto_quant/challenger_replacement_supersession_publish.py \
  src/crypto_quant/challenger_replacement_plan_supersession.py \
  config/challenger-replacement-owner-attestation-v1.schema.json \
  src/crypto_quant/schemas/challenger-replacement-owner-attestation-v1.schema.json \
  config/challenger-replacement-plan-supersession-v1.schema.json \
  src/crypto_quant/schemas/challenger-replacement-plan-supersession-v1.schema.json \
  docs/superpowers/specs/2026-08-09-replacement-challenger-plan-v2-supersession-design.md \
  docs/superpowers/plans/2026-08-09-replacement-challenger-plan-v2-supersession.md \
  tests/test_challenger_replacement_plan_supersession.py
git commit -m "feat: add fixed replacement supersession evidence boundary"
```

- [ ] **Step 9: Run both pre-artifact platform gates**

On the target Mac, run the focused tests with Python 3.9 and Python 3.12 when both interpreters are
available; the actual Darwin feasibility test must pass at least once on the release candidate. Preserve
private Draft PR #32 and run `31436609135` as billing-blocked pre-run evidence. Then follow the fixed
minimal-public-witness plan to freeze private source candidate `F`, obtain the separate irreversible
eight-file approval, run Python 3.9/3.12 Ubuntu against the exact exported bytes, seal the run, and create
strict descendant `G`. Record exact local/public commands, commit/tree/blob identities and run/job IDs.

If target-Darwin or either public Linux job is unsupported, skipped, mocked, absent or failing, or strict
witness replay / `F`→`G` unchanged-source verification fails, stop before Task 5. Do not generate any
formal plan/evidence/attestation/record artifact.

---

## Task 5: Generate and Freeze the Formal V2 Plan Artifact

**Files:**

- Create: `artifacts/challenger-replacement/challenger-replacement-plan-v0.64.0.json`
- Modify: `tests/test_challenger_replacement_plan_v2.py`

**Interfaces:**

- Consumes: fully tested `build_challenger_replacement_plan_v2()` and v2 loader.
- Produces: exact canonical v2 plan bytes required by the current-machine/Git collector.

- [ ] **Step 1: Re-run all pre-artifact design/Schema tests**

Run the Task 4 focused command. Expected: all pass. Stop if any test fails; artifact generation is
forbidden before this gate. Independently verify the target-Mac Darwin gate passed on `F`, the exact
public mirror bytes from `F` recorded successful non-skipped Python 3.9/3.12 Ubuntu jobs executing the
actual Linux primitive, the strict witness replay passed, and `G` is a strict descendant of `F` with all
public-source blobs unchanged. Exact private/public commit/tree/blob/run/job identities must match;
private run `31436609135` remains honestly billing-blocked and mock coverage is insufficient.

- [ ] **Step 2: Generate the plan from the parameterless builder**

Use the reviewed fixed-path publisher to publish exactly:

```python
canonical_json(build_challenger_replacement_plan_v2()).encode("utf-8") + b"\n"
```

to the fixed artifact path through nonce staging, same-fd readback/file fsync, atomic no-replace and
directory fsync. Do not call a generic/direct-final writer and do not hand-edit plan ID, plan hash,
policy hash or file bytes.

- [ ] **Step 3: Add committed-artifact regression**

Require builder bytes equal artifact bytes after applying the repository newline convention, load the
artifact through the v2 production loader, recompute file SHA, and rerun every v1/v2 canonical subtree
equality assertion against the committed artifact.

- [ ] **Step 4: Prove v0.62 remains unchanged**

Recompute v0.62 file SHA and compare exact bytes against
`git show v0.62.0:artifacts/challenger-replacement/challenger-replacement-plan-v0.62.0.json`. Verify
`git rev-parse v0.62.0^{}` equals `e0a9b3...`. Any mismatch stops the version.

- [ ] **Step 5: Run focused tests to green**

```bash
PYTHONPATH=src python3 -m unittest tests.test_challenger_replacement_plan_v2 -v
```

Expected: exact artifact regression passes.

- [ ] **Step 6: Commit only the formal plan artifact and regression**

Before staging the commit, require the protocol-staging inventory to be empty and raw Git status to
contain exactly the plan artifact plus its intended test change. Any sealed orphan may be retried but
keeps the release blocked; do not commit around it.

```bash
git add artifacts/challenger-replacement/challenger-replacement-plan-v0.64.0.json \
  tests/test_challenger_replacement_plan_v2.py
git commit -m "feat: freeze replacement preregistration v2 artifact"
```

Record the resulting exact commit as `H`. Require raw Git status empty immediately after the commit;
this is `C0_PLAN_COMMITTED_CLEAN`.

---

## Task 6: Freeze Machine Evidence, Owner Attestation and Supersession Record

**Files:**

- Create: `artifacts/challenger-replacement/challenger-replacement-supersession-machine-evidence-v0.64.0.json`
- Create: `artifacts/challenger-replacement/challenger-replacement-owner-attestation-v0.64.0.json`
- Create: `artifacts/challenger-replacement/challenger-replacement-plan-supersession-v0.64.0.json`

**Interfaces:**

- Consumes: exact v2 plan artifact, fixed v1 identity, current read-only observations, immutable
  Git/release-history transcripts and explicit owner approval.
- Produces: machine-evidence, owner-attestation and supersession-record artifacts. This task is a
  governance release gate; loaders validate bytes and bindings but do not prove provenance or
  historical truth.

- [ ] **Step 1: Read-only precheck repository and machine identity**

Verify exact `HEAD=H`, state `C0_PLAN_COMMITTED_CLEAN`, empty protocol-staging inventory, v0.63 baseline
ancestry, unchanged v0.62 and
v0.63 annotated tag identities, effective uid, and current absence of runtime root/plist/service. Run
the fixed Git-history queries for the committed challenger-replacement artifact, ADR and status paths.
Do not create missing runtime paths. If any observation or transcript is ambiguous, stop without
output.

- [ ] **Step 2: Collect and durably publish the machine/Git evidence exactly once**

In a new OS process run exactly:

```bash
PYTHONPATH=src python3 -m \
  crypto_quant.challenger_replacement_plan_supersession_cli \
  collect-machine-evidence
```

The command takes no path or fact overrides, records exact argv/exit/stdout/stderr hashes, labels the
result only `NO_OBSERVABLE_REPLACEMENT_STATE_AT_COLLECTION`, and uses the fixed publisher. It must
state that absent-tree counts are current-only and collector state-write count is collector-only. Its
embedded raw Git-status transcript is the empty `C0` status collected before staging creation.
Successful publication must leave an empty staging inventory and produce exactly
`C1_EVIDENCE_ONLY` at unchanged `HEAD=H`.

- [ ] **Step 3: Replay evidence in a separate read-only process**

Load exact bytes from the fixed path; verify Schema, canonical hash, observation claim, plan/Git
bindings and transcripts. Compute and report its external file SHA. Do not call this replay proof of an
unpatched collector or historical non-use. Before proceeding require raw status exactly equal to the
evidence final, staging inventory empty, and evidence bytes/hash/stat/identity unchanged.

- [ ] **Step 4: Obtain explicit accountable owner approval and publish attestation**

Show the owner the exact declaration from the design, signer identity/uid, signed-at time, v0.62/v2
identities, machine-evidence hash and Git-history-evidence hash. Stop and request explicit approval;
prior general project authorization is not a substitute for signing these exact bytes. After approval,
run only the parameterless `record-owner-attestation` command and enter the exact acknowledgement
through its interactive ceremony. Publish through the fixed publisher, then replay in a separate
read-only process. Record the owner approval transcript reference in review notes; do not claim the
loader proves the statement true. The command must save the exact `C1_EVIDENCE_ONLY` precondition
transcript and, on success with empty staging inventory, produce exactly
`C2_EVIDENCE_ATTESTATION_ONLY` at unchanged `HEAD=H`.

- [ ] **Step 5: Assemble and publish the supersession record**

Run only the parameterless `assemble-record` command. It loads exact fixed plan, machine-evidence and
attestation paths, verifies every binding, and publishes with the fixed publisher. It accepts no
caller-supplied fact or path. A missing/ambiguous attestation, current observation, Git transcript or
provenance review stops without record output. It saves the exact `C2_EVIDENCE_ATTESTATION_ONLY`
precondition transcript and, on success with empty staging inventory, produces exactly
`C3_THREE_FINALS_UNCOMMITTED` at unchanged `HEAD=H`.

- [ ] **Step 6: Replay record and compute external file SHA**

In a separate read-only process load the exact record against the exact three input artifacts. Verify
record ID/hash, both plan identities, evidence/attestation hashes, reason and prohibition. Only after
exact record bytes exist, compute the record canonical file SHA externally; bind it later in
status/ADR/manifest, never inside the record.

- [ ] **Step 7: Run the pre-committed committed-artifact regressions**

Run the three exact fixed-path regression methods committed before `HEAD=H`. They load machine
evidence, owner attestation and record through their production loaders. Require all three methods to
execute and pass with zero skips; the pre-artifact absence-only `skipUnless` conditions are now false.
Do not modify code or tests in Task 6. Test fixtures remain temporary and test-qualified, and the tests
assert loader capabilities are limited to structure/hash/claim/binding checks without describing
fixture fabrication as technically impossible.

- [ ] **Step 8: Run focused tests to green**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_challenger_replacement_plan_v2 \
  tests.test_challenger_replacement_plan_supersession -v
```

Expected: formal plan, machine evidence, owner attestation and record replay exactly with all bindings;
the three exact fixed-path regressions report zero skips, and the test report makes no historical-truth
or unpatched-process claim. A broad skip, caught loader exception or unexpected skip is failure.

- [ ] **Step 9: Commit the three immutable supersession artifacts**

Require raw status exact allowlist to contain only evidence, attestation and record finals; require
all three strict replays, identities and external SHAs to match and protocol-staging inventory to be
empty. Any other entry or orphan blocks the commit.

```bash
git add artifacts/challenger-replacement/challenger-replacement-supersession-machine-evidence-v0.64.0.json \
  artifacts/challenger-replacement/challenger-replacement-owner-attestation-v0.64.0.json \
  artifacts/challenger-replacement/challenger-replacement-plan-supersession-v0.64.0.json
git commit -m "feat: record pre-start replacement plan supersession"
```

Record the new commit as `H2`; require raw Git status empty and staging inventory empty. Only this is
`C4_THREE_FINALS_COMMITTED_CLEAN`.

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

- Consumes: exact v1/v2 plans, machine evidence, owner attestation and exact supersession record.
- Produces: honest v0.64 release identity; no runtime eligibility.

- [ ] **Step 1: Write ADR-0064**

Record the infeasibility of strict v0.62 storage under the approved security model, explicit pre-start
supersession, canonical subtree equality, event-only authority, non-authoritative exports, old-plan
immutability and post-start supersession prohibition. Use the precise layered account: current
`NO_OBSERVABLE_REPLACEMENT_STATE_AT_COLLECTION` machine snapshot, immutable Git/release-history
observations, and accountable owner historical attestation. State explicitly that neither snapshot,
Git nor loader proves the attestation true. State that v0.62 is historical and superseded, not silently
amended and not a failed research cohort.

- [ ] **Step 2: Write implementation status**

Status must say:

```text
PLAN_FROZEN_REPLACEMENT_V2_NOT_STARTED
```

List both plan identities/file SHAs, machine-evidence/attestation identities and file SHAs,
supersession record identity/hash/external file SHA, current observable facts, owner declaration and
provenance limits. List the v0.64 build/manifest identity only here and in ADR/manifest after all four
artifacts exist; never write it back into plan, attestation or record. Preserve explicit ineligibility
for runtime, deployment, start, 90-day completion, profitability, AI advantage, Canary and live
trading.

- [ ] **Step 3: Update README and release metadata**

Set package version `0.64.0`, advance manifest version once, register all new code/Schema/artifact/docs
files in the build file set, and recompute manifest hashes through the repository validation workflow.
The release manifest/status/ADR bind plan, evidence, attestation and record external file SHAs plus the
v0.64 build identity in one direction only. Do not add runtime or deployment claims.

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

## Task 8: Review, Final Draft-PR CI, Main CI and Annotated Tag

**Files:**

- No intended source changes unless review finds a Critical or Important issue.

**Interfaces:**

- Produces: reviewed `v0.64.0` plan-only release exactly aligned to merged main.

- [ ] **Step 1: Perform one complete independent review**

Review v1 immutability, exact foundation/warning gates, Schema/loader capability limits, collector
read-only boundary, fixed-path crash-safe publication, current-snapshot vs historical-attestation
separation, exact C0-C4 state machine, sealed-orphan release block, Darwin/Linux no-replace feasibility,
Git/release provenance, post-start prohibition and absence of runtime scope.
Critical and Important findings must reach zero. After fixes, review only changed areas.

- [ ] **Step 2: Re-run proportionate verification after review fixes**

Run focused tests for touched files; run the full suite again only if production code changed after its
single final-state run. Never rerun the same unchanged full state mechanically.

- [ ] **Step 3: Re-verify GitHub write authority before the final push**

Recheck target private repository, exact origin URL, remote main, authenticated ADMIN permission, intended
branch and clean worktree. A connector 404 for the private repository may fall back only to authenticated
`gh` after target identity is proven.

- [ ] **Step 4: Update the approved replacement Draft PR and wait for final Python 3.9/3.12 CI**

PR #32 and run `31436609135` remain immutable historical evidence of the original billing-blocked
attempt; they are not the replacement PR's original run. After the separate private integration approval,
push `G` and the later reviewed commits only to the approved replacement private Draft PR, verify its
exact final head commit, and require both final Python jobs to belong to and execute on that exact head.
The public witness does not make these private checks green and does not replace this final release gate.
If private hosted CI is still quota-blocked, retain that evidence and keep the release pending until the
replacement PR jobs can actually execute; do not merge on billing block, failure, skip or ambiguity.

- [ ] **Step 5: Merge, verify main CI and tag identity**

Merge only after approval and green PR CI. Wait for merged-main CI, then create annotated `v0.64.0`
exactly at merged main. Push the tag and verify remote main and peeled tag commit are identical.

- [ ] **Step 6: Reconfirm the non-start boundary**

After release, report only plan supersession completion. Do not install, start, create production paths,
invoke Runner or begin 90-day timing. Record that v0.65 remains the Nautilus Spike and v0.66 is the
earliest replacement runtime version.
