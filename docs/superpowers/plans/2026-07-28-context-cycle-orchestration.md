# v0.25 Context-Complete Cycle Orchestration Plan

## Task 1 — Shared verified runtime gate

- Add an issued `VerifiedRuntimeGate` in `runtime_health.py`.
- Add shared-gate account and perpetual capture paths without changing their
  standalone network-count contracts.
- Test construction blocking, probe replay and one monotonic clock identity.

## Task 2 — Append-only orchestration journal

- Add immutable SQLite WAL events and exact source blobs.
- Freeze legal stage transitions, leases, retries and slot expiry.
- Replay hashes and stage projection on every open.
- Test tampering, concurrency and recovery after each prepared stage.

## Task 3 — End-to-end orchestrator

- Preflight signer before network.
- Execute account → Paper → perpetual → binding → context in fixed order.
- Reuse prepared sources after crash and publish exact bytes.
- Report physical request counts and shared-gate lineage.
- Keep all outputs owner-only and preserve existing schedulers unchanged.

## Task 4 — Snapshot, CLI and local scheduler contract

- Add orchestration snapshot Schema and packaged mirror.
- Add a one-shot CLI with fixed paths and no URL/key/order/time overrides.
- Add deterministic LaunchAgent renderer/validator; do not call `launchctl`.
- Test missing credentials produce zero network and generated plist contains
  paths but no secret values.

## Task 5 — Release evidence

- Add ADR-0025, v0.25 status and fail-closed real-run evidence.
- Add new sources, schemas and artifacts to the evaluator build manifest.
- Bump package version to 0.25.0.

## Task 6 — Verification and Git

- Run focused tests, full tests, compileall and `make validate`.
- Verify schema mirrors, file permissions and sensitive-value scans.
- Commit implementation, fast-forward `main` and create annotated `v0.25.0`.
- Push when a GitHub repository and authenticated transport exist.
