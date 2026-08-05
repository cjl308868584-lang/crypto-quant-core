# Replacement Challenger Preregistration and Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish v0.62.0 as an immutable, credential-free preregistration and isolation contract for a genuinely new replacement Challenger cohort, permanently bound to the old cohort's missed-slot failure and decommission evidence, without installing or starting any runtime.

**Architecture:** A parameterless pure builder creates the only permitted plan semantics. Every policy section has a deterministic business hash; the full plan has a stable identity and self-hash. A strict production loader accepts only canonical, owner-controlled exact bytes and proves equality with the builder. A committed artifact is generated from the builder, while Schema mirrors, release metadata, documentation, and build-manifest coverage make the artifact independently replayable from the tagged source.

**Tech Stack:** Python 3.9+, standard-library `json`/`hashlib`/`pathlib`, Draft 2020-12 JSON Schema, `unittest`, existing `crypto_quant` canonical JSON and strict-loader conventions, Make validation, Git/GitHub Actions.

## Global Constraints

- Never create or inspect replacement production paths from the builder or loader.
- Never install, bootstrap, kickstart, load, or invoke either old/new Challenger or System Paper services.
- Never invoke a Runner, scheduler, maintenance pipeline, market request, Broker, account endpoint, credential, or order path.
- Never migrate, copy, backfill, or count old decisions, Episodes, receipts, archives, results, PnL, or elapsed days toward the replacement cohort.
- Preserve `production_activation=false`, `runtime_install_authorized=false`, `replacement_start_authorized=false`, and all runtime/network/write counters at zero.
- Use test-driven development: add one coherent failing test slice, observe the expected failure, implement the minimum complete behavior, then re-run the focused slice.
- Run the final local full suite once for the final code state. Do not repeat a full suite on the same commit.
- Perform one independent complete review; after fixes, perform only targeted re-review of changed areas.
- Publish only after PR Python 3.9/3.12 CI, merged-main CI, and annotated-tag identity all verify.

---

## Task 1: Freeze the builder, policy identities, and Schema

**Files:**

- Create: `tests/test_challenger_replacement_plan.py`
- Create: `src/crypto_quant/challenger_replacement_plan.py`
- Create: `config/challenger-replacement-plan-v1.schema.json`
- Create: `src/crypto_quant/schemas/challenger-replacement-plan-v1.schema.json`

- [ ] **Step 1: Add the failing builder identity tests**

Write tests that call `build_challenger_replacement_plan()` 100 times and require exact equality plus canonical-byte equality. Freeze these identities:

```python
EXPECTED_LABEL = "local.crypto-quant.challenger-replacement-v1"
EXPECTED_SERVICE = "gui/501/local.crypto-quant.challenger-replacement-v1"
EXPECTED_ROOT = "/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1"
EXPECTED_STATUS = "PLAN_FROZEN_REPLACEMENT_NOT_STARTED"
EXPECTED_SLOTS = 540
```

Assert that the builder has no parameters, every `*_hash` is 64 lowercase hex characters, `plan_id` is derived from its identity input, `plan_hash` equals a recomputation with the self-hash removed, and all start/end/tail timestamps are `None`.

- [ ] **Step 2: Run the new test and confirm the intended red state**

Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_challenger_replacement_plan -v
```

Expected: import failure because `crypto_quant.challenger_replacement_plan` does not yet exist.

- [ ] **Step 3: Implement canonical hashing and the parameterless builder**

Implement private helpers using the existing canonical JSON convention:

```python
def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

def _business_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()
```

Build the fixed top-level sections described in the design:

```text
$schema, schema_version, plan_id, plan_hash,
foundation, predecessor, scope, decision_policy, cohort_policy,
isolation_policy, evidence_policy, authority, status, eligibility, warnings
```

Bind the exact v0.61 foundation and exact v0.54/v0.43/v0.44 predecessor file hashes, business IDs, and business hashes from the design. Derive a replacement decision-policy hash from the unchanged thresholds while excluding the old fixed `forward_start`. Set all install/start/network/Runner/write authorities to false or zero.

- [ ] **Step 4: Add and validate strict Draft 2020-12 Schemas**

Define every property, enum, type, pattern, absolute path, fixed counter, and `additionalProperties: false`. Require the two Schema mirrors to be byte-identical. Add tests that validate the builder result with the repository's supported Schema validator and assert the mirror bytes are equal.

- [ ] **Step 5: Add semantic isolation and forbidden-content tests**

Assert:

- the new label/service/root/plist differ from all old Challenger and System Paper identities;
- every relative child path is normalized, non-absolute, and cannot escape its root;
- old roots, repository/worktree paths, `/tmp`, and `/private/tmp` are forbidden;
- no URL, header, key, token, secret, credential path, account endpoint, Broker endpoint, order endpoint, price, fee override, PnL, outcome label, or manual date exists anywhere in canonical plan bytes;
- no old evidence object can be counted as replacement evidence;
- the cohort is 90 days at 14,400-second cadence and therefore exactly 540 required slots.

- [ ] **Step 6: Run the focused tests to green**

Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_challenger_replacement_plan -v
```

Expected: all builder, Schema, hashing, and isolation tests pass.

- [ ] **Step 7: Commit the builder and Schema slice**

```bash
git add tests/test_challenger_replacement_plan.py \
  src/crypto_quant/challenger_replacement_plan.py \
  config/challenger-replacement-plan-v1.schema.json \
  src/crypto_quant/schemas/challenger-replacement-plan-v1.schema.json
git commit -m "feat: freeze replacement challenger plan"
```

---

## Task 2: Add the fail-closed production loader and side-effect boundary

**Files:**

- Modify: `tests/test_challenger_replacement_plan.py`
- Modify: `src/crypto_quant/challenger_replacement_plan.py`

- [ ] **Step 1: Add failing path and parser tests**

Test that `load_challenger_replacement_plan(path)` rejects:

- relative paths, missing paths, directories, symlinks, non-regular files, and files larger than 256 KiB;
- group/world-writable files and files with more than one hardlink;
- invalid UTF-8, duplicate JSON keys, all JSON floating-point values (including NaN/Infinity), non-object roots, and non-canonical bytes;
- unknown/missing fields, Schema violations, self-hash tampering, policy-hash tampering, and semantic changes whose hashes are recomputed.

Each case must return one of the fixed reason codes from the design and must not write any file.

- [ ] **Step 2: Run only the loader tests and confirm red**

Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_challenger_replacement_plan.ChallengerReplacementPlanLoaderTests -v
```

Expected: failure because the loader is not implemented.

- [ ] **Step 3: Implement strict exact-byte loading**

Implement:

1. absolute lexical path check before resolution;
2. `lstat`/`open`/`fstat` identity checks that reject symlinks and file substitution;
3. maximum-size, regular-file, owner/mode, and single-hardlink checks;
4. UTF-8 and duplicate-key rejection through `object_pairs_hook`;
5. float rejection through `parse_float` and `parse_constant`;
6. canonical-byte comparison allowing exactly one final newline for the committed artifact;
7. Schema validation;
8. section-hash, plan-id, and plan-hash recomputation;
9. exact semantic equality with `build_challenger_replacement_plan()`.

Return a deep copy of the validated object so callers cannot mutate module-level constants.

- [ ] **Step 4: Add predecessor exact-byte replay tests**

Load the four committed predecessor files named in the plan and prove their SHA-256, object IDs, and business hashes match the frozen plan. Tampered temporary copies must be rejected by semantic comparison even if their internal self-hashes are recomputed.

- [ ] **Step 5: Add AST and filesystem side-effect tests**

Parse the module AST and reject imports or calls for `socket`, HTTP clients, exchange clients, `sqlite3`, `subprocess`, `launchctl`, Runner, scheduler, maintenance, Broker, account, or order code. Snapshot the absence of the replacement runtime root/plist and verify builder/load operations leave them absent and do not alter old/System Paper paths.

- [ ] **Step 6: Run focused and adjacent tests**

Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_challenger_replacement_plan \
  tests.test_challenger_cohort_failure \
  tests.test_challenger_cohort_decommission -v
```

Expected: all pass without production side effects.

- [ ] **Step 7: Commit the loader slice**

```bash
git add tests/test_challenger_replacement_plan.py \
  src/crypto_quant/challenger_replacement_plan.py
git commit -m "feat: verify replacement challenger plan"
```

---

## Task 3: Publish and replay the exact committed artifact

**Files:**

- Create: `artifacts/challenger-replacement/challenger-replacement-plan-v0.62.0.json`
- Modify: `tests/test_challenger_replacement_plan.py`

- [ ] **Step 1: Add a failing committed-artifact contract test**

Require the committed path to exist, be canonical builder bytes plus exactly one newline, load successfully through the production loader, and match both a frozen file SHA-256 and the builder's business identity.

- [ ] **Step 2: Confirm the intended red state**

Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_challenger_replacement_plan.ChallengerReplacementPlanArtifactTests -v
```

Expected: missing committed artifact.

- [ ] **Step 3: Generate the artifact only from the builder**

Use a small reviewed one-shot Python invocation that imports the builder and writes its canonical bytes plus one newline to the repository path. Do not accept parameters or manually edit the JSON.

- [ ] **Step 4: Freeze the exact file SHA in tests and replay it**

Calculate the file SHA-256, freeze it in the test, load through `load_challenger_replacement_plan`, and compare the loaded object to a fresh builder result. Re-run the artifact test.

- [ ] **Step 5: Commit the exact artifact**

```bash
git add artifacts/challenger-replacement/challenger-replacement-plan-v0.62.0.json \
  tests/test_challenger_replacement_plan.py
git commit -m "data: publish replacement challenger plan"
```

---

## Task 4: Bind v0.62 release metadata and documentation

**Files:**

- Modify: `pyproject.toml`
- Modify: `src/crypto_quant/__init__.py`
- Modify: `src/crypto_quant/evaluator_build.py`
- Modify: `artifacts/evaluator-build-manifest.json`
- Modify: `tests/test_estimators.py`
- Create: `docs/adr/ADR-0062-replacement-challenger-preregistration-isolation.md`
- Modify: `docs/implementation-status.md`
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-08-05-replacement-challenger-preregistration-isolation.md`

- [ ] **Step 1: Add failing release-binding tests**

Update estimator/build tests to require package version `0.62.0`, evaluator manifest version `1.56.0`, and inclusion of the new module, both Schema mirrors, exact artifact, design, implementation plan, ADR, implementation status, README, and tests in the build input set.

- [ ] **Step 2: Confirm the release-binding red state**

Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_estimators \
  tests.test_challenger_replacement_plan -v
```

Expected: version/build-manifest assertions fail before release metadata is changed.

- [ ] **Step 3: Update versions and build inputs**

Set the package and module versions to `0.62.0`, advance the build-manifest contract to `1.56.0`, and add all v0.62 source/evidence/document paths to the evaluator build's allowlist.

- [ ] **Step 4: Write the ADR and status documentation**

The ADR must record the rejected path-reuse and monolithic-release alternatives, the selected three-version layering, predecessor failure ancestry, zero-authority boundary, and future first-natural-slot rule. README and implementation status must say `PLAN_FROZEN_REPLACEMENT_NOT_STARTED`, not “Paper running” or “ready for live trading.”

- [ ] **Step 5: Refresh the build manifest mechanically**

Use the repository's existing manifest refresh command. Inspect the diff and confirm the new manifest hashes the complete intended input set and no production artifact or local path leaked into Git.

- [ ] **Step 6: Run focused and adjacent verification**

Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_challenger_replacement_plan \
  tests.test_estimators \
  tests.test_challenger_forward \
  tests.test_challenger_cohort_failure \
  tests.test_challenger_cohort_decommission -v
python3 -m compileall -q src tests
git diff --check
```

- [ ] **Step 7: Commit the release binding**

```bash
git add pyproject.toml src/crypto_quant/__init__.py \
  src/crypto_quant/evaluator_build.py artifacts/evaluator-build-manifest.json \
  tests/test_estimators.py docs/adr/ADR-0062-replacement-challenger-preregistration-isolation.md \
  docs/implementation-status.md README.md \
  docs/superpowers/plans/2026-08-05-replacement-challenger-preregistration-isolation.md
git commit -m "release: bind replacement challenger v0.62.0"
```

---

## Task 5: Complete the streamlined safety gate and publish v0.62.0

**Files:** Review all changes from `origin/main...HEAD`.

- [ ] **Step 1: Perform one complete independent review**

Review the full branch against the design and this plan. Pay special attention to:

- whether any old cohort evidence can become replacement evidence;
- whether a semantic change can survive recomputed hashes;
- path substitution, symlink, hardlink, permissions, canonical-byte, duplicate-key, and float bypasses;
- build-manifest omissions;
- accidental install/start/network/state-write capability;
- misleading claims about profitability, AI advantage, Paper completion, Canary, or live-trading eligibility.

Critical and Important findings must be zero before publication.

- [ ] **Step 2: Fix findings with failing regression tests first**

For each accepted finding, write the smallest failing regression test, observe red, fix the implementation, and run the focused/adjacent slice. Review only the changed areas afterward; do not repeat the whole-branch review.

- [ ] **Step 3: Run the final local verification exactly once**

On the final code state, run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -v
/usr/bin/python3 -m compileall -q src tests
make validate
git diff --check
git status --short
```

Record the exact commit and counts. Do not run the full suite a second time on the same commit.

- [ ] **Step 4: Re-verify remote authority immediately before write**

Confirm the repository is private, authenticated access is ADMIN, `origin` is exactly the intended repository, and `origin/main` plus annotated `v0.61.0` still peel to `0811402ae4f9baebf905f548336ca2c29885ce9c`. Stop if any identity changed unexpectedly.

- [ ] **Step 5: Push the branch and open a Draft PR**

Push `codex/v0.62-replacement-challenger-plan`, create a Draft PR, and require the Python 3.9 and 3.12 jobs. Confirm the PR exact head matches the reviewed/tested commit.

- [ ] **Step 6: Wait for PR CI, merge, and verify main CI**

Only after both PR jobs pass, mark ready and merge. Verify `origin/main` is the expected merge commit and wait for the corresponding main CI run to succeed.

- [ ] **Step 7: Create and verify the annotated release tag**

Create annotated `v0.62.0` on the exact verified `origin/main` commit, push it, and independently confirm:

```text
origin/main peeled commit == v0.62.0 peeled commit
tag type == tag
tag target == verified main commit
```

- [ ] **Step 8: Confirm production remains untouched**

Read-only verify the replacement root/plist/service are still absent, System Paper remains absent/not loaded, the old Challenger remains decommissioned/not loaded, and no Runner/market/Broker/order/state-write action occurred. v0.62 ends at `PLAN_FROZEN_REPLACEMENT_NOT_STARTED`.

