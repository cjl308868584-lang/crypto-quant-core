# System Paper Finalization Residual Hardening Design

Date: 2026-08-05  
Status: FROZEN FOR IMPLEMENTATION  
Release target: v0.59.0 (still unreleased)  
Implementation base: `84a72f0cc71fad86d66bb61dfe4e40f68af42c83`

## 1. Purpose

The first v0.59 final-fix wave closed its original three Critical and three
Important findings and passed 1,108 local tests. Its single scoped re-review
then found two combined-state defects that still block release:

1. the lock file pathname can be replaced after one evaluator locks its inode,
   allowing a second evaluator to lock a different inode in the same output
   root; and
2. stable prepared-state corruption combined with an `EMPTY` slot inventory is
   classified as event-chain-bound `COHORT_INCOMPLETE` before the prepared
   corruption can select the raw-SQLite binding.

This design closes only those two defects and the audit/build changes required
to bind their implementation. It does not expand v0.59 into deployment,
installation, scheduling, market access, brokerage or trading.

## 2. Frozen authority and global constraints

- Remote `origin/main` and annotated tag `v0.58.0` peel to
  `35a810622fc0449f2131ccbb806354b48deac15d`.
- Work remains on `codex/v0.59-system-paper-evaluation` in the existing linked
  worktree.
- v0.59 package version remains `0.59.0`; evaluator build manifest version
  remains `1.53.0`. Exact input hashes are refreshed after all tracked inputs
  settle.
- `production_activation.enabled=false` remains unchanged.
- No production install, start, bootstrap, kickstart, Runner, scheduler,
  maintenance, market request, Broker call, order, credential access or
  production-state write is permitted.
- System Paper production root, plist and service remain absent/not loaded.
- The prior final-fix SDD workspace is historical evidence. This design gets a
  separate plan, SDD workspace, ledger, implementer and review chain.

## 3. Root-cause analysis

### 3.1 Split lock identity

`_RetainedOutputRoot.acquire_lock()` currently opens
`.system-paper-evaluation.lock`, verifies its directory entry, then calls
`flock()` on that file descriptor. `flock()` protects the opened inode, not the
pathname. If the directory entry is renamed or replaced after the first open,
a second evaluator can open and lock a different inode. Both evaluators then
enter the terminal scan/publish critical section.

The output-root directory inode is already retained and verified for the full
publication lifetime. Creating a second mutable lock pathname adds an avoidable
identity boundary.

### 3.2 Prepared corruption loses precedence

After a valid event-metadata replay, the post-tail flow currently captures the
slot inventory surface and returns `COHORT_INCOMPLETE` whenever that surface is
not `PRESENT`. Full start-receipt/prepared-state replay happens only afterward.
Consequently, the same stable SQLite corruption receives different state
bindings depending on the unrelated slot-directory surface.

The binding question must be answered before the inventory-completeness
question: first establish whether the retained SQLite group is semantically
replayable, then describe the retained slot inventory.

## 4. Considered approaches

### 4.1 Directory-inode lock plus post-tail binding-first flow — selected

Use `flock(LOCK_EX)` on the already retained output-root directory descriptor.
Remove the lock-file namespace entry entirely. Separately, perform the strict
post-tail start/prepared replay before choosing an inventory result, while
preserving one retained inventory capture.

This has the smallest authority surface, introduces no new persistent state,
and directly removes both root causes.

### 4.2 Separate immutable lock-anchor directory — rejected

A sibling anchor could be retained and locked, but it introduces another path,
ownership contract and loader/build input while still requiring attachment
verification. It offers no advantage over the already retained output root.

### 4.3 SQLite terminal transaction — rejected

A database uniqueness row could serialize finalization, but it would write the
strategy/runtime state that the evaluator is required to consume read-only. It
would also couple immutable result publication to scheduler availability.

## 5. Directory-inode finalization lock

`_RetainedOutputRoot.acquire_lock()` must:

1. acquire `fcntl.flock(self.descriptor, fcntl.LOCK_EX)` on the retained
   owner-`0700` directory descriptor;
2. re-run output-root attachment verification after the blocking acquisition;
3. mark the retained root as locked without opening or creating a child entry;
4. reject double acquisition on the same retained object; and
5. release the directory lock during `close()` before closing the descriptor.

The output root must contain result JSON files only. The former lock filename is
not allowlisted or silently ignored. If an unexpected entry appears, terminal
inventory validation fails closed and publishes no second final.

All existing operations remain inside one directory-inode critical section:
strict existing-final scan, exact-idempotency decision, authority verification,
publication, post-publication scan and final attachment verification.

Replacing, adding or renaming the former lock pathname cannot create a second
lock domain because that pathname is no longer opened. Replacing the entire
output-root path is still detected by the retained root attachment checks. A
detached root cannot yield a loadable canonical final.

## 6. Post-tail state-binding precedence

The post-tail flow uses this immutable ordering:

1. retain authority inputs and the raw SQLite main/WAL/SHM group;
2. replay event metadata;
3. strictly replay the full start receipt and prepared state;
4. capture the slot inventory exactly once and retain that capture;
5. choose the terminal outcome using the table below; and
6. reverify every retained authority before returning or publishing.

| Condition | Outcome |
|---|---|
| Authority receipt/hash mismatch | hard `AUTHORITY_INVALID`, no final |
| Any retained source changes after capture | hard `SOURCE_CHANGED`, no final |
| Stable event/schema replay corruption | raw-bound `STATE_REPLAY_INVALID` |
| Stable prepared replay corruption | raw-bound `PREPARED_REPLAY_INVALID` |
| Replayable state plus `EMPTY`/`MISSING`/`UNSAFE`/mismatched inventory | event-chain-bound `COHORT_INCOMPLETE` |
| Replayable state plus exact 540 inventory | full cohort/economic replay |

Stable prepared corruption always wins over inventory incompleteness because it
determines which state bytes can be truthfully authenticated. The retained
inventory is still recorded in the raw-bound result, including `EMPTY`,
`MISSING`, `UNSAFE` or extra/missing-name evidence.

Only the exact known prepared-state replay failure is mapped to raw-bound
INCONCLUSIVE. A malformed/tampered start receipt or an unrecognized loader
failure remains a hard authority error. The implementation must preserve the
existing causal allowlist instead of using a broad `except Exception` fallback.

## 7. Interfaces and code boundaries

### 7.1 `_RetainedOutputRoot`

- Remove `_LOCK_NAME` and `lock_descriptor` as authority mechanisms.
- Add a boolean `locked` lifecycle flag.
- `acquire_lock()` operates only on `self.descriptor`.
- `verify()` continues to bind the directory descriptor to the declared path
  and every retained result to its directory entry.
- `_strict_existing_finals()` treats every child as a candidate result JSON;
  no child filename is excluded for locking.

### 7.2 Post-tail prepared replay helper

Introduce one focused helper whose contract is:

```python
def _post_tail_prepared_replay(
    *, paths, preflight_path, install, start, retained,
    state_retained, machine_probe, filesystem_probe
) -> Tuple[Optional[Mapping[str, Any]], Optional[str]]:
    ...
```

It returns `(replayed_start, None)` on success or
`(None, "SYSTEM_PAPER_EVALUATION_PREPARED_REPLAY_INVALID")` only for the exact
stable prepared-state failure. It raises `AUTHORITY_INVALID` for receipt
tampering or any non-allowlisted failure. It does not capture slot inventory,
publish, or write state.

The main readiness function calls this helper before inventory outcome
selection, then performs the single retained inventory capture. If the helper
returned the prepared-invalid reason, readiness publishes a raw-bound
INCONCLUSIVE using that same inventory capture.

## 8. Required RED-to-GREEN evidence

### 8.1 Lock-domain tests

- `test_directory_inode_lock_survives_former_lock_path_replacement`
  opens two retained views of the same root, holds the first lock, replaces or
  creates the former filename, and proves the second directory lock cannot
  enter until the first releases.
- `test_former_lock_path_race_never_publishes_two_finals` races two distinct,
  schema-valid final candidates while mutating the former filename. The only
  allowed outcomes are one exact winner plus terminal conflict, or fail-closed
  output/result conflict; two final JSON files are forbidden.
- Existing normal concurrency, idempotency, output-root attachment and loader
  tests remain green.

### 8.2 Binding-precedence tests

- `test_stable_prepared_corruption_with_empty_inventory_is_raw_bound`
- `test_stable_prepared_corruption_with_missing_inventory_is_raw_bound`
- `test_stable_prepared_corruption_with_unsafe_inventory_is_raw_bound`
- `test_authority_tamper_with_empty_inventory_remains_hard_failure`
- `test_prepared_capture_after_change_with_empty_inventory_is_source_changed`

Each raw-bound test must load the exact published artifact and assert
`state_binding_kind == "RAW_SQLITE_GROUP"`, null event-chain hash, the prepared
reason code and the real retained inventory state. The hard-failure tests must
assert zero result JSON files.

### 8.3 Regression boundaries

- Tail blindness remains unchanged: no slot/prepared replay before the tail.
- Replayable state plus incomplete inventory remains event-chain-bound
  `COHORT_INCOMPLETE`.
- Stable event corruption remains raw-bound.
- Wrong first receipt remains hard authority failure.
- Exact 540 and 541st-slot behavior remains unchanged.

## 9. Build, documentation and release gates

The new design, implementation plan, source and tests become evaluator build
inputs. The original v0.59 design, ADR, implementation status and README must
state that the residual defects were found and closed before release. No text
may claim installation, a started 90-day cohort, profitability, AI advantage,
Canary eligibility or live-trading eligibility.

After tracked inputs settle, refresh the evaluator build manifest once under
version `1.53.0`, retaining package `0.59.0`. Required controller evidence is:

- named RED and GREEN tests;
- focused evaluator/CLI/evidence/start/build suites;
- full test discovery;
- compileall;
- both Schema parses and byte mirror;
- evaluator build validation;
- `make validate`;
- `git diff --check v0.58.0...HEAD` and a clean worktree;
- read-only proof that production root/plist/service remain absent/not loaded;
- independent task reviews and one broad whole-branch review with Critical 0
  and Important 0.

Only after those gates may the branch be pushed to a Draft PR, pass Python
3.9/3.12 PR CI, merge exact reviewed HEAD, pass main CI and receive an annotated
`v0.59.0` tag aligned exactly with remote main.

## 10. Failure closure

Any duplicate final, lock-domain split, wrong state binding, loader failure,
source mutation, unexpected inventory entry, Schema/build/hash mismatch, test
failure or Git/GitHub identity mismatch stops release. There is no backfill,
manual result selection, threshold change, production activation or claim of
profitability.
