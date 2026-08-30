# v0.78.7 partial-install recovery design

## Scope and authority

v0.78.7 is the only recovery release for the immutable v0.78.5 partial
installation.  It adds no trading, strategy, UI, scheduler or generic
deployment feature.  Code release does not run the renderer, preflight,
installer, LaunchAgent or runtime.  It performs no credential, account,
Broker, order or fund operation.

The recovery protocol is eligible only while both service labels are disabled
and absent from `gui/501`, automation `v0-78-3-replacement` is `PAUSED`, and
the replacement event, start-receipt and log roots contain no files.  Any
different or ambiguous observation fails closed.

## Preserved incident evidence

The frozen recovery plan records these exact v0.78.5 objects.  File records
include absolute path, SHA-256, decimal device and inode, owner UID, mode,
link count, size, `st_mtime_ns` and `st_ctime_ns`:

- installed target plist SHA-256
  `30efabbd76ab5af9c277213b3377612b5119a7889c6b8165748dbcc36acd329b`;
- failed install receipt SHA-256
  `97747c0ebd2f49c3afe875e9a1f99d541d98e363ac457e767a622586f8523198`;
- successful preflight receipt SHA-256
  `3440beab833c998a3d0c250e60fd2f6876f4aa206c0e5c609a772d4333a59ce5`;
- v0.78.5 contract SHA-256
  `03d6cf60e51ebe87d5a81d8f45d33d8e39d4074bf57b6bd450c4b5cdfbd026af`;
- v0.78.5 candidate plist, whose bytes equal the installed target bytes;
- snapshot tree
  `b5ac484d5b7b8e61d36c33b7cc686fda23a79524734167158123720b2c14cfbe`,
  101 files and 3,248,480 bytes, plus its root identity and timestamps;
- empty event root, empty start-receipt root and empty log root, each with its
  exact directory identity, timestamps and exact child-name inventory;
- the predecessor plist for `local.crypto-quant.challenger-forward`, including
  its exact bytes and filesystem record.

The plan also binds the exact v0.78.6 foundation: public repository
`cjl308868584-lang/crypto-quant-core`, annotated tag `v0.78.6`, peeled commit
`faf6e03632c21dba0894f0a1248f308306b13737`, tag object
`bc78d140129a23b38d3c72c1f4a93d8df568275e`, manifest version `1.78.0`,
manifest hash
`808c2fd2aefbfc363725f0cf2a46a74cfc56a538e284dce6fd62042d475ea477`
and manifest file SHA-256
`f06bbfa5dba81cd9f713c4d6b51bbd403d67439b063fdfe1f5b7fe49ae0f5cea`.

These records are prerequisites, not objects the recovery code may repair.
The protocol never opens a preserved file for writing and never calls chmod,
rename, unlink or replace on a preserved path.  It only opens existing files
with no-follow, nonblocking read flags and validates type, attachment,
identity, bounds and exact bytes.  Directory checks use retained descriptors
and exact child-name inventories.  A mismatch is permanent evidence conflict,
not a reason to update the plan.

## Chosen design

Three approaches were considered:

1. **Release-scoped recovery receipt and new target path (chosen).**  Preserve
   the old incident, publish an immutable receipt that binds it to the exact
   new candidate, and install only to a new path.
2. **Adopt or rewrite the old target.**  Rejected because the old target is
   bound by a receipt that cannot pass its published schema; mutation would
   destroy the incident replay.
3. **Delete or move old files before retry.**  Rejected because cleanup would
   erase the evidence this release exists to preserve.

`activation_paths()` retains the service label but assigns the new target:

`/Users/chenm4/Library/LaunchAgents/local.crypto-quant.challenger-replacement-v1-v0.78.7.plist`

The v0.78.7 contract, candidate, preflight, install and recovery receipt paths
are all release scoped.  The runtime, snapshot, event, log and start-receipt
roots remain unchanged.  The old target path is never an installer output.

## Components and data flow

### Frozen recovery plan

`config/challenger-replacement-v3-partial-install-recovery-v0.78.7.json` is
canonical JSON with a strict schema, self-hash and business ID.  It contains
only the exact foundation, fixed paths, preserved evidence records, required
empty-root records, required service/automation observations and the new
target pathname.  Loader reconstruction rejects extra keys, noncanonical
bytes, identity drift and semantic mismatch.

### Read-only qualification

The no-argument recovery CLI is executed only in a later separately authorized
ceremony, after the exact v0.78.7 renderer has published its candidate and
contract.  It:

1. strictly loads the checked-in plan and exact published v0.78.7 contract;
2. validates every preserved file and directory against the plan;
3. verifies the old and replacement labels are both explicitly disabled and
   `launchctl print` reports both absent;
4. verifies the automation file has exact `status = "PAUSED"` with no duplicate
   status key;
5. verifies the event, start-receipt and log inventories remain empty;
6. verifies the new target path is absent;
7. publishes one canonical recovery receipt with the existing crash-safe,
   no-overwrite exact publisher.

The receipt status is
`PARTIAL_INSTALL_RECOVERY_ELIGIBLE_NOT_EXECUTED`.  It binds the plan, all
observed evidence identities, launchctl transcript hashes, automation status,
the exact v0.78.7 contract/candidate/release identity and the explicit relation
`v0.78.5 failed install -> v0.78.7 install candidate`.  Its authority counters
are all zero except fixed read-only process observations.  It is not an install
receipt and does not authorize runtime or trading.

### Installer gate

The v0.78.7 installer loads exactly one recovery receipt from its fixed root.
It strictly reconstructs the receipt, revalidates the preserved incident and
current safety state, replays the exact v0.78.7 contract/candidate binding, and
requires the new target to remain absent before any existing plist publication
or bootstrap code can run.  It never scans or adopts the old v0.78.5 install
receipt as a current receipt.  Subsequent installed-state loaders use the new
install receipt's exact contract and preflight bindings as before.

## Crash and replay semantics

- Before staging creation: no recovery artifact exists; retry repeats all
  read-only checks.
- Partial staging write or failed file fsync: only a noncanonical staging file
  may exist; the existing publisher fails closed on orphan staging and never
  treats it as evidence.
- Complete staging before no-replace: no canonical receipt exists; retry fails
  closed on orphan staging for explicit incident handling.
- Canonical rename before directory fsync: an exact retry confirms directory
  durability and strict replay before returning `ALREADY_PUBLISHED`.
- Canonical receipt present and exact: retry performs full current-state
  revalidation and returns the same receipt ID/hash without writing.
- Canonical receipt different or untrusted: fixed conflict; no overwrite.
- Any old-path identity, timestamp, byte or inventory change: fixed evidence
  conflict; no receipt and no installer continuation.
- Concurrent attempts: no-replace yields one canonical inode.  Exact loser
  replays it; different loser fails conflict.

The protocol does not silently delete orphan staging.  Recovery from such a
crash preserves the affected work/root for diagnosis and begins from a clean,
separately authorized ceremony only after the conflict is understood.

## Schemas and errors

New plan and receipt schemas are closed (`additionalProperties=false`).
Filesystem device, inode, nanosecond timestamp and other values that can exceed
the canonical safe-integer range are unsigned decimal strings with no leading
zeros.  Canonical timestamps end in `.000Z`.  Files are bounded before read.

Public failures map to fixed codes:

- `CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_PLAN_INVALID`
- `CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_EVIDENCE_CONFLICT`
- `CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_STATE_CONFLICT`
- `CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_CANDIDATE_INVALID`
- `CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_RECEIPT_INVALID`
- `CHALLENGER_REPLACEMENT_PARTIAL_RECOVERY_PUBLICATION_FAILED`

Unexpected I/O never becomes success.  Close failure does not replace an
existing primary error and is attached as diagnostic context where possible.

## Verification and release gates

TDD must first demonstrate failures for missing evidence, same bytes on a new
inode, mtime/ctime drift, symlink/hardlink/wrong mode, nonregular/FIFO entries,
nonempty event/start/log roots, either service loaded or not explicitly
disabled, automation not paused, existing new target, different canonical
receipt, interrupted staging and concurrent publication.  Sentinel bytes,
mode, size, inode, link count, mtime and ctime must remain unchanged on every
rejection path.

Tests then prove exact qualification, receipt schema/self-hash/business-ID
rebuild, strict replay, idempotent retry, installer rejection without a valid
receipt and installer acceptance only after full revalidation.  All execution
tests use fixtures and patched fixed OS command boundaries; no test runs a real
renderer, preflight, installer or launchctl mutation.

The final code state receives focused and adjacent tests, one full local suite,
`compileall`, `make validate`, diff checks, one independent review, public PR
CI, merged-main CI and an annotated exact `v0.78.7` tag.  v0.78.7 publication
does not authorize the later recovery ceremony.  No v0.78.8 is permitted for
this recovery design; a contradiction stops the work rather than expanding it.
