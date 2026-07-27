# Paper Runtime Health Implementation Plan

**Goal:** Gate every new 4h public Paper cycle on replayable Binance
server-time health, and persist heartbeat continuity and machine-readable local
alerts without enabling accounts or orders.

**Architecture:** A fixed three-sample public time probe computes conservative
offset intervals. Stable bounded offsets feed a monotonic corrected clock;
untrusted clocks block the existing v0.19 scheduler. A separate append-only
SQLite event chain records every heartbeat and publishes a fully replayable
runtime snapshot.

## Task 1: clock probe contract

1. Add failing tests for the exact public URL, three requests and no retries.
2. Implement bounded same-host HTTPS transport with proxy bypass.
3. Preserve raw response, selected headers, wall/monotonic timings and hashes.
4. Reject status, redirect, JSON, integer, body, wall reversal and RTT faults.
5. Implement exact integer offset intervals with no binary floats.

## Task 2: health policy and corrected clock

1. Test aligned, stable-correctable and blocked classifications.
2. Require three intervals, <=3000ms RTT, nonempty <=1000ms intersection and
   <=5000ms conservative absolute offset.
3. Derive an integer midpoint correction.
4. Implement a monotonic anchored clock and prove it never goes backward when
   the injected wall clock jumps.
5. Validate probe self-hash and external attestation.

## Task 3: append-only heartbeat state

1. Add SQLite WAL/FULL synchronous runtime event state.
2. Reject symlink state paths and event UPDATE/DELETE.
3. Verify canonical payload hashes and the full chain on every append/open.
4. Calculate trusted heartbeat gaps without fabricating first-boot history.
5. Emit explicit unknown continuity when either endpoint is untrusted.

## Task 4: alerts and wrapper

1. Gate v0.19 scheduler before all four market-data requests.
2. Report separate time, market and total network counts.
3. Derive S2/S3 active alerts and raised/cleared transitions.
4. Record scheduler success, already-succeeded, busy and failure outcomes.
5. Prove blocked clock means zero scheduler/market calls.
6. Prove healthy retry keeps v0.19 market-network idempotency.

## Task 5: runtime snapshot and CLI

1. Add strict package/governance JSON Schema.
2. Replay every embedded probe and runtime event.
3. Project summaries, latest references and alerts from the event chain.
4. Implement `paper-runtime-run` with only state/output/worker arguments.
5. Publish immutable runtime snapshot and external attestation.
6. Keep URL/header/key/account/order/time overrides unavailable.

## Task 6: real smoke and release

1. Run a real three-sample public server-time probe.
2. If healthy, execute the current v0.19 slot with the corrected clock; if
   blocked, prove the market transport was never invoked.
3. Re-run to demonstrate market request idempotency where the same schedule
   state is available.
4. Reconcile probe intervals, runtime replay, scheduler snapshot and network
   counts.
5. Add ADR-0020, implementation status and README update.
6. Update package/evaluator release metadata to 0.20.0.
7. Run focused tests, full suite, Golden vectors and all validators.
8. Commit isolated implementation, merge main and tag v0.20.0.

## Acceptance

- Every scheduler call is preceded by a valid current server-time probe.
- Stable bounded offset is corrected with a monotonic anchor.
- Untrusted time cannot trigger market-data capture.
- Heartbeat gaps and scheduler failures remain visible in append-only evidence.
- Local Artifact alerts are never misrepresented as externally delivered.
- v0.19 scheduling and v0.18 economic replay remain backward compatible.
- No credentials, account endpoints, Broker, orders, OS scheduler installation,
  AI execution, Canary or Live authority is introduced.
