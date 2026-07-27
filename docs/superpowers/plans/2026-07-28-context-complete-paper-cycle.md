# Context-Complete Paper Cycle Implementation Plan

**Goal:** Freeze and crash-recover one 4h Paper slot's verified account costs
and perpetual context without changing the legacy Paper run.

## Task 1: bundle and PIT validation

1. Validate the complete cost binding and all three source attestations.
2. Validate the complete perpetual snapshot and its external attestation.
3. Infer and freeze the exact v1 Paper schedule slot.
4. Enforce scheduled run identity, active-slot timestamps and 15-minute skew.
5. Mark perpetual data observational and Funding unrealized.
6. Add strict mirrored Schema, self-hash, trust hash and full replay.

## Task 2: append-only context state

1. Add isolated SQLite WAL event and PREPARED-blob tables.
2. Add immutable update/delete triggers.
3. Verify event chain, state transitions, blob bytes and every source trust.
4. Implement lease, BUSY, reclaim, PREPARED resume and idempotent success.
5. Bind PREPARED output root and exact Artifact name.

## Task 3: runner and CLI

1. Build and prepare before immutable publish.
2. Resume PREPARED without rereading sources or using network.
3. Adopt already-published exact bytes after a crash.
4. Add fault injection tests after prepare and publish.
5. Publish mode-0600 because the bundle embeds account fingerprint evidence.
6. Expose only local source/trust/state/output/worker arguments.

## Task 4: release

1. Add PIT, slot, mutation, state-chain, recovery and CLI tests.
2. Freeze no-real-source failure evidence.
3. Add ADR-0024, implementation status and README update.
4. Bump package/build versions and freeze new inputs.
5. Run focused/full tests, compileall, Golden Vectors and validators.
6. Commit, fast-forward main and tag v0.24.0.
