# v0.64 Public Core CI Umask Correction Design

**Status:** approved through the user's standing execution authorization
**Date:** 2026-08-21
**Release:** `v0.64.0`
**Failed public PR run:** `32485858116`
**Failed exact head:** `81d57221b6e1b947921aa30532e771654472f409`

## 1. Decision

The canonical repository `cjl308868584-lang/crypto-quant-core` is now public. Future code-state
verification therefore uses that repository's ordinary pull-request Python 3.9/3.12 CI, fixed-UID
security boundary, merged-main CI, and annotated-tag identity. The obsolete response to private
Actions billing limits—creating another parentless public mirror and another R4 bundle/witness—is
forbidden.

The successful R3 mirror remains immutable historical evidence for private source commit
`f9705fa2151ab98a5b9efe63be05979e4bc5bfa6`. Its exact artifacts, repository, root commit, run,
schemas, and witness are not rewritten. Historical tests must replay R3 from that exact Git object;
they must not require every future descendant of the core repository to keep the old publisher blob
forever.

## 2. Observed failure and root cause

Public PR run `32485858116` executed exact head `81d57221b6e1b947921aa30532e771654472f409`.
Python 3.9 completed all 1472 tests successfully and 22 of 23 fixed-UID tests. The only failure was
`test_temporary_git_ceremony_transitions_c0_through_c4_exactly`; Python 3.12 was cancelled by matrix
fail-fast while its full suite was still running.

Two deterministic RED reproductions identify one environmental contract gap:

1. Git checkout under a restrictive process umask can create a trusted tracked plan as mode `0640`.
   The test fixture used a discrete mode allowlist and rejected this safer mode.
2. `os.open(..., mode=0644)` is also filtered by the caller's umask. The publisher then rejected its
   own newly created mode-`0640` staging file before publication.

Later public-core runs exposed a distinct test-fixture boundary after the production publisher fix:

- run `32501051838` passed the complete Python 3.12 suite, then failed only the UID-501 ceremony;
- run `32509529713` moved that fixed-owner gate before the full suite and recorded the exact checkout
  identity as `mode=0666 uid=501 euid=501 nlink=1 regular=True`;
- run `32510011662` proved the corrected fixed-owner gate on both Python 3.9 and 3.12 before entering
  the full suites.

The reviewed Git checkout can therefore materialize a world-writable worktree file even while the
calling process temporarily uses umask `0022`. Ambient checkout mode is not itself authority. The
general ceremony helper must continue rejecting any arbitrary world-writable existing plan, while
the test-owned private clone may normalize only its exact reviewed checkout through a retained
descriptor after proving the Git object, canonical bytes, ownership, type, link count, size, and
attachment.

The failure is not an Actions quota issue, strategy failure, evidence corruption, or permission to
weaken fixed-owner checks.

## 3. Alternatives

### 3.1 Create an R4 mirror

Rejected. It repeats bundle, repository, workflow, acquisition, witness, and release infrastructure
that is no longer needed after the core repository became public.

### 3.2 Delete the historical blob gate

Rejected. R3's claim that its publisher and Linux test matched the original frozen candidate remains
valuable and must stay replayable.

### 3.3 Freeze R3 historically and verify current code directly

Adopted. The historical gate reads the exact F/F3 Git blobs and proves the original R3 claim. The
current publisher may change only through normal reviewed/TDD changes and is verified directly by
the public core PR/main CI pipeline.

## 4. Minimal implementation

### 4.1 Trusted tracked fixture

Before normalization, the tracked plan must be a regular file, owned by the effective UID, have one
link, be owner-readable, contain no special or execute bits, and not be world-writable. Exact bytes
must match both the reviewed HEAD blob and the canonical plan. It is then normalized to mode `0644`
for the fixed ceremony. Symlink, hardlink, wrong owner, executable/special, world-writable, or byte
drift remains fail-closed and is not modified.

### 4.2 New staging descriptor

The publisher still creates only a noncanonical nonce staging entry with
`O_CREAT|O_EXCL|O_RDWR|O_NOFOLLOW` and requested mode `0644`. Before changing permissions it must
verify through the retained descriptor that the new object is regular, UID 501, nlink 1, size 0,
and its actual mode is a permission-subset of `0644`. It may then call only
`fchmod(staging_fd, 0644)`, re-`fstat`, and require the same device/inode plus exact mode. It never
path-chmods or modifies an existing final, staging entry, or external inode.

All existing write/readback, short-write/EINTR, file fsync, atomic no-replace, directory fsync,
attachment, close, bounded-read, FIFO, symlink, hardlink, and crash-recovery gates remain unchanged.

### 4.3 Historical/current evidence split

- R1/R2/R3 committed bytes and loaders remain unchanged.
- The R3 blob equality regression checks the exact historical F3 source object against the original
  F object instead of building a new R3 bundle from current HEAD.
- Public core PR CI is the authority for the current candidate. A failed PR run is preserved by
  GitHub and referenced in the correcting commit/PR; it does not require a new formal mirror artifact.
- No new repository, mirror schema, witness root, or Actions workflow is introduced.

### 4.4 Reviewed checkout fixture

The UID-501 C0→C4 integration test creates a fresh `0700`, effective-UID-owned private parent and
uses `--no-local --no-hardlinks` for the reviewed clone. Its fixed plan path must be a `100644` HEAD
blob whose bytes equal the canonical v2 plan. The checked-out entry is opened
`O_RDONLY|O_NOFOLLOW|O_NONBLOCK`; `fstat` must prove regular file, effective-UID ownership, one link,
exact size, owner readability, and no executable or special permission bits. Exact bytes are read
from that retained descriptor before `fchmod(fd, 0644)`. A second `fstat` and final `lstat` must keep
the same device/inode and exact attachment. No path chmod or generic acceptance of mode `0666` is
allowed.

The ordinary helper remains unchanged: a caller-supplied world-writable tracked plan is untrusted,
is not modified, and fails closed.

The fixed-owner security boundary runs before `make test` in each public matrix job. This preserves
all coverage while making a boundary regression fail in seconds rather than after both long suites.

## 5. Tests and release gates

Required RED/GREEN evidence:

1. mode `0640` tracked plan fails before the fixture correction and succeeds after normalization;
2. publisher under `umask 0027` fails before descriptor normalization and publishes an exact
   mode-`0644` final afterward;
3. the full C0→C4 ceremony succeeds under `umask 0027`;
4. world-writable, hardlink, symlink, wrong-owner, nonregular, and existing-entry cases remain
   fail-closed with sentinel identity unchanged;
5. historical R3 replay still proves its publisher/Linux-test blobs equal the original frozen F
   blobs, while current HEAD is not constrained to those bytes;
6. an exact reviewed checkout at initial mode `0666` is normalized only by retained descriptor,
   while the generic world-writable fixture remains rejected without modification;
7. fixed-owner CI precedes the full suite without deleting either gate;
8. focused and adjacent tests, compileall, diff-check, build-manifest replay, and one full local suite
   pass for the final code state;
9. exact public PR Python 3.9/3.12 CI and fixed UID boundary pass, then merged-main CI passes;
10. annotated `v0.64.0` peels exactly to `origin/main`.

Any failed gate stops merge/tag. CI must not be rerun without a code-state change merely to search for
a better result.

## 6. Non-goals and safety

This correction does not install or start services; invoke Runner, scheduler, maintenance, Broker,
market/account network, credentials, orders, or production state; change v0.62/v2 research facts;
or claim profitability, AI advantage, Paper completion, Canary eligibility, or live-trading safety.
All production and trading authorities remain false.
