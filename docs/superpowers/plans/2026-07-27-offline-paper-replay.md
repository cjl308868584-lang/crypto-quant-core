# Offline Paper Replay Implementation Plan

**Goal:** Build a deterministic, public-only offline Paper cycle from
contemporaneously received warm-up, public symbol rules and post-decision market
observations through baseline decision, conservative simulated fill, two virtual
economic ledgers, replay validation and external attestation.

**Architecture:** A fixed Paper capture plan performs two decision-input GETs,
freezes the decision time, then performs two execution-observation GETs. Strict
parsers issue an opaque verified market input. A frozen SMA20/vol12 baseline
builds existing decision contracts. A conservative BBO broker rounds with
public exchange filters and records a virtual fill. Separate temporary WAL
ledgers generate baseline and AI economic snapshots. AI is explicitly not run
without an approved model. The final artifact replays every layer from raw
responses and requires an external attestation.

**Tech Stack:** Python 3.9+, standard-library `urllib`, `Decimal`, `datetime`,
`tempfile`, existing contracts/instrument rounding/EventLedger/economic
validators/canonical hashes, JSON Schema Draft 2020-12, `unittest`.

## Global constraints

- Spot `ETHUSDT` LONG only.
- Exact public GET requests only; no caller URL/query/header.
- No credentials, account, Broker, order or external write capability.
- Decision-input responses precede decision time; BBO/AggTrade responses follow it.
- Exactly 200 4h Klines, at least 21 closed bars.
- Starting virtual equity is exactly 1000 USDT.
- Frozen baseline is `SPOT_LONG_SMA20_VOL12_BUCKET25_V1`.
- Frozen fill policy uses 10 bps slippage and 15 bps entry/exit fee assumptions.
- Quantity and price rounding never improve the simulated fill or increase risk.
- AI arm is explicit `NOT_RUN_NO_APPROVED_MODEL` and cannot trade.
- Final eligibility is always `OFFLINE_PAPER_SMOKE_ONLY`.
- Final package version is `0.18.0`.

## Files

- Create `src/crypto_quant/offline_paper.py`.
- Create `src/crypto_quant/offline_paper_cli.py`.
- Create `tests/test_offline_paper.py`.
- Create `tests/test_offline_paper_cli.py`.
- Create `config/offline-paper-run-snapshot-v1.schema.json`.
- Create package schema copy.
- Create `docs/adr/0018-offline-paper-replay.md`.
- Create `docs/implementation-status-v0.18.0.md`.
- Create `artifacts/paper/binance-offline-paper-smoke-v0.18.0.json`.
- Modify README, versions, build manifest and evaluator input tests.

## Task 1: exact staged Paper capture

1. Write failing tests for exact warm-up/exchangeInfo/BBO/AggTrade URLs and
   decision-before-execution ordering.
2. Implement immutable `OfflinePaperCapturePlan` and injectable transport
   orchestration.
3. Write failing tests for response status/host/clock/body limits and raw receipts.
4. Implement opaque `VerifiedPaperMarketInput`.
5. Verify and commit.

## Task 2: strict warm-up and public metadata

1. Write failing Kline tests for 200-row maximum, 21 closed-bar minimum, exact
   4h spacing, Decimal/OHLC/time/source payload hashes and current-bar exclusion.
2. Implement warm-up parser.
3. Write failing exchangeInfo tests for symbol/status/assets/MARKET plus
   PRICE_FILTER, LOT_SIZE and MIN_NOTIONAL/NOTIONAL.
4. Implement conservative normalized metadata and hash.
5. Write BBO/AggTrade parser and gap/clock tests.
6. Verify and commit.

## Task 3: baseline Decision Kernel

1. Write failing feature tests for exact SMA20, 20 log returns, sample volatility,
   annualization and base exposure.
2. Implement frozen baseline policy using Decimal only.
3. Write failing LONG and FLAT tests for StrategyProposal, NO_AI MetaDecision and
   TargetPosition lineage.
4. Implement decision builder.
5. Write tests that AI-unavailable always emits FREEZE/no target/no fill.
6. Verify 100-run determinism and commit.

## Task 4: conservative fill and two economic ledgers

1. Write failing order/fill tests covering round-down quantity, round-up BUY price,
   BBO quantity cap, min quantity/notional, partial/no fill and independent fees.
2. Implement simulated broker using normalized public metadata.
3. Write failing virtual-ledger tests for start/fill/end events, conservative
   liquidation, separate baseline/AI scopes and exact economic replay.
4. Implement temporary WAL ledger builder and existing EconomicLedgerSnapshot.
5. Assert AI ledger contains no fill and matched capital/window.
6. Verify and commit.

## Task 5: complete Paper run artifact and CLI

1. Write failing tests for complete raw-response replay, source roots, policy hashes,
   nested economic snapshots, fixed eligibility and mutation detection.
2. Implement `build_offline_paper_run`, `offline_paper_run_reasons`, snapshot
   attestation envelope/hash and strict schema.
3. Write CLI tests for structured public-only args and atomic no-overwrite publish.
4. Implement CLI.
5. Verify wheel/package schema parity and commit.

## Task 6: real smoke, delivery and release

1. Run one real ETHUSDT public-only Paper cycle without credentials.
2. Validate complete snapshot with independently persisted attestation.
3. Rebuild from raw responses and require identical bytes/hash.
4. Commit compact hashes/counts/decision/fill/eligibility only; omit prices,
   quantities and full raw responses.
5. Add ADR, implementation status and README history.
6. Update version and evaluator manifest.
7. Run focused tests, full suite, validators and Golden Vectors.
8. Review for credentials, write endpoints, profit/Paper escalation and cost
   double-counting.
9. Fast-forward merge to `main`, rerun validation, tag `v0.18.0`, remove worktree.

## Completion criteria

- The only live operations are four exact public GETs.
- The decision is frozen before execution observations.
- Latest closed 4h data alone drives the frozen baseline.
- Same-bar fill is impossible.
- Public filters constrain every simulated fill.
- Entry/exit cost and slippage are conservative and not double-counted.
- Baseline and AI have separate verified economic ledgers.
- AI absence cannot silently turn into an AI decision.
- Complete replay needs raw responses plus external attestation.
- Real smoke remains insufficient for Paper/profitability.
- Repository and evaluator validations pass at v0.18.0.
