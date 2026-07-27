# Contemporaneous Public Capture Implementation Plan

**Goal:** Add a public-only, fail-closed Binance contemporaneous capture pipeline
that records actual receive times, preserves Kline revisions and observable
AggTrade gaps, explicitly degrades REST BBO sequence claims, and publishes a
replayable externally anchored session snapshot.

**Architecture:** An immutable allowlisted plan emits four exact market-data-only
GET requests. An injectable transport records request/receive times and bounded
response bytes. Strict family parsers create source-bound observations. A session
builder deduplicates or chains revisions, computes quality findings and issues a
fixed research-only snapshot. Complete trust requires an external attestation
binding the entire snapshot, not a self-hash.

**Tech Stack:** Python 3.9+, standard-library `urllib`, `json`, `Decimal`,
`datetime`, existing canonical SHA-256 helpers, JSON Schema Draft 2020-12,
`unittest`.

## Global constraints

- Only `ETHUSDT` and `BTCUSDT`.
- Exactly `1m`/`4h` Kline, latest 100 AggTrades and one-symbol BBO.
- Only `https://data-api.binance.vision`; no arbitrary URL, path, query or header.
- No API key, account, order, Broker or trading dependency.
- Binary float forbidden in evidence.
- Actual receive time is availability time.
- BBO event time is explicitly a client-receive proxy and has no sequence claim.
- Every snapshot remains `CONTEMPORANEOUS_RESEARCH_ONLY` and
  `CAPTURE_REPLAY_ONLY`.
- No changes to Release Gate thresholds.
- Final package version is `0.17.0`.

## File structure

- Create `src/crypto_quant/contemporaneous_capture.py`.
- Create `src/crypto_quant/capture_cli.py`.
- Create `tests/test_contemporaneous_capture.py`.
- Create `tests/test_capture_cli.py`.
- Create `config/contemporaneous-capture-snapshot-v1.schema.json`.
- Create package copy under `src/crypto_quant/schemas/`.
- Create `docs/adr/0017-contemporaneous-public-capture.md`.
- Create `docs/implementation-status-v0.17.0.md`.
- Create `artifacts/market-data/binance-contemporaneous-smoke-v0.17.0.json`.
- Modify version, exports, README and evaluator build manifest.

## Task 1: freeze the plan, requests and response receipts

1. Write failing tests for the exact four URLs and rejection of unsupported
   symbol/family/interval/query/header inputs.
2. Implement `ContemporaneousCapturePlan.create` and request generation.
3. Write failing receipt tests for UTC clocks, final host, metadata, body limits,
   body SHA-256 and self-hash.
4. Implement immutable `PublicCaptureResponseReceipt`.
5. Verify focused tests and commit.

Required interfaces:

- `ContemporaneousCapturePlan.create(symbol)`
- `capture_requests(plan)`
- `PublicCaptureHttpResponse`
- `build_response_receipt(request, response)`

## Task 2: parse source-bound observations

1. Write failing Kline tests covering exact Decimal strings, 1m/4h, open/close
   semantics, current/closed state and malformed OHLC/time/count values.
2. Implement strict Kline parsing.
3. Write failing AggTrade tests covering source IDs/time, maker flag, ID ordering,
   duplicate/conflicting IDs and malformed values.
4. Implement strict AggTrade parsing.
5. Write failing BBO tests covering bid/ask relations and mandatory
   `CLIENT_RECEIVE_TIME_PROXY`.
6. Implement strict BBO parsing.
7. Reparse every saved source payload and compare all normalized fields and hashes.
8. Verify and commit.

Required interfaces:

- `parse_capture_response(request, receipt, response_body, ingested_at, recorded_at)`
- `observation_hash(observation)`
- `observation_replay_reasons(observation)`

## Task 3: build revision, gap and quality evidence

1. Write failing tests for:
   - same Kline key/same payload duplicate;
   - current Kline payload revision chain;
   - closed Kline mutation blocking;
   - AggTrade duplicate, gap and conflicting ID;
   - BBO duplicate and mandatory sequence-unobservable reason;
   - missing family and clock violations.
2. Implement deterministic canonicalization and quality report.
3. Write failing snapshot tests for roots, fixed eligibility, self-hash,
   deterministic replay and mutation detection.
4. Implement opaque capture batch/session input so callers cannot assemble a
   trusted snapshot from arbitrary observations.
5. Write failing external attestation tests: missing anchor, self-derived anchor,
   old snapshot anchor and receipt-only anchor all fail closed.
6. Implement complete session attestation and semantic reasons.
7. Add strict JSON Schema and schema parity tests.
8. Verify and commit.

Required interfaces:

- `capture_once(plan, transport, clock)`
- `build_capture_session(batches, session_id, recorded_at)`
- `capture_snapshot_hash(snapshot)`
- `capture_snapshot_attestation_envelope(snapshot)`
- `capture_snapshot_attestation_hash(snapshot)`
- `capture_snapshot_reasons(snapshot, trusted_attestation_hash=None)`

## Task 4: add safe production transport and immutable CLI

1. Write failing tests for GET-only behavior, no proxy, no caller headers, fixed
   host redirects, bounded reads, timeout, 429/418/5xx and structured errors.
2. Implement `BinancePublicMarketDataTransport`.
3. Write failing CLI tests for structured args, no secrets/URLs, atomic
   no-overwrite publishing, idempotency, symlink/conflict protection and
   partial-failure cleanup.
4. Implement CLI.
5. Verify focused and security regression tests; commit.

## Task 5: publish real smoke and v0.17 delivery evidence

1. Run two real public capture rounds for `ETHUSDT`.
2. Validate both complete snapshots with independently persisted attestation hashes.
3. Reparse/rebuild the saved snapshot and require byte/hash equality.
4. Commit only compact hashes, counts, timings and eligibility reasons.
5. Add ADR, README and implementation status.
6. Update version, package schema, evaluator manifest and golden build evidence.
7. Run focused tests, full suite, schema/build validators and Golden Vectors.
8. Review the complete diff for secret/order/account capability and eligibility
   escalation.
9. Merge to `main`, rerun final verification and tag `v0.17.0`.

## Completion criteria

- Exact public-only requests and clocks are replayable.
- Source payload mutations or semantic mutations are detected.
- Kline revision chains and AggTrade observable gaps are deterministic.
- BBO limitations cannot be suppressed.
- Complete validation requires an external snapshot attestation.
- Real smoke succeeds without credentials and remains research-only.
- Full repository tests and evaluator build validation pass.
- No account, order, Broker or profitability claim exists.
