# Longitudinal Paper Scheduler Implementation Plan

**Goal:** Build a durable, one-shot 4h Paper scheduler that never backfills
missed contemporaneous decisions and recovers exact prepared artifacts after
process failure.

**Architecture:** A frozen UTC slot policy selects only the current due slot.
An append-only SQLite WAL event chain provides leases and state transitions.
Exact run bytes are persisted transactionally before immutable file
publication. A replayable schedule snapshot projects longitudinal coverage.

## Task 1: slot policy

1. Add failing tests for UTC floor, 5-minute delay, expiry and slot IDs.
2. Implement immutable `PaperSchedulePolicy` and `PaperSlot`.
3. Reject naive timestamps, floats, invalid schedule identity and future runs.
4. Prove first boot starts at current slot only.

## Task 2: append-only state and leases

1. Add failing tests for WAL/full synchronous/no UPDATE/no DELETE.
2. Implement event and prepared-blob schemas with no-follow state path checks.
3. Implement complete event-chain verification on every mutation.
4. Implement atomic CLAIM and 15-minute lease semantics.
5. Test two-state-handle contention, expired lease reclaim and idempotent success.

## Task 3: failure and missed-slot semantics

1. Implement FAILED retry inside the same active slot.
2. Implement terminal EXPIRED when a known unfinished slot window passes.
3. Insert explicit MISSED events for gaps after the first observed slot.
4. Prohibit execution of missed, expired or historical slots.
5. Test multi-slot gaps and no historical fabrication on first boot.

## Task 4: prepared-byte recovery

1. Persist exact canonical run bytes and its hashes in the PREPARED transaction.
2. Publish only a derived safe filename under `paper/`.
3. Resume PREPARED without any transport call after restart.
4. Adopt an already-published identical file idempotently.
5. Reject filename, byte, run hash, attestation or slot/time mismatches.
6. Fault-inject before prepare, after prepare and after publish.

## Task 5: schedule snapshot and CLI

1. Add strict governance/package JSON Schema.
2. Project slot states and counts from the event chain.
3. Build snapshot self-hash and external attestation.
4. Implement `paper-scheduler-run` CLI with state/output/worker only.
5. Print machine-readable outcome, cycle reference and schedule trust hash.
6. Ensure no URL/header/key/account/order/time-override CLI flags.

## Task 6: real smoke and release

1. Run one real current ETHUSDT slot using a temporary state DB.
2. Re-run the same slot with a transport that fails if called; prove zero GETs.
3. Freeze cycle and schedule smoke Artifacts.
4. Reconcile event root, prepared bytes, run replay and economic ledgers.
5. Add ADR-0019, implementation status and README update.
6. Update package to 0.19.0 and evaluator manifest.
7. Run focused tests, full suite, Golden vectors and all validators.
8. Commit isolated implementation, fast-forward main and tag v0.19.0.

## Acceptance

- Current-slot execution is exactly once at the evidence level.
- Process/file-publication crashes resume exact prepared bytes.
- Multiple workers cannot concurrently own a live lease.
- Missed cycles remain explicit and cannot be backfilled.
- Every successful cycle retains complete v0.18 replay guarantees.
- Short duration remains ineligible for Paper/profitability/AI claims.
- No account, credentials, Broker, orders, daemon or operating-system scheduler
  is introduced.
