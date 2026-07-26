# Historical Market Data Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Use `superpowers:test-driven-development` for every behavior change and `superpowers:verification-before-completion` before any completion claim.

**Goal:** Add a public-only, fail-closed Binance historical archive ingestion pipeline that verifies official checksums, normalizes real market/cost facts, records deterministic provenance and makes archive-only PIT limitations machine-enforceable.

**Architecture:** A strict `HistoricalArchiveRequest` generates allowlisted Binance public-data paths; an injectable GET-only fetch boundary returns raw ZIP and CHECKSUM responses; safety and checksum validation occur before exact family parsers normalize Decimal/UTC facts. `PublicArchiveReceipt`, `DataQualityReport`, and `HistoricalMarketDataSnapshot` form a self-hashed evidence chain. Archive snapshots always remain `ARCHIVE_REPLAY_ONLY`; account-specific fee schedules stay separate and effective-dated.

**Tech Stack:** Python 3.9+, standard-library `urllib`, `zipfile`, `csv`, `Decimal`, `datetime`, existing canonical SHA-256 helpers, JSON Schema Draft 2020-12, `unittest`.

## Global Constraints

- Supported symbols are exactly `ETHUSDT` and `BTCUSDT`.
- Supported families are Spot Kline/AggTrade and USDⓈ-M Mark Price Kline/Funding Rate.
- The library never accepts an arbitrary URL.
- Network operations are HTTPS GET only to `data.binance.vision`, with no credentials or authentication headers.
- Official SHA-256 verification precedes archive decompression and CSV parsing.
- Spot timestamp units are explicit: milliseconds before 2025-01-01, microseconds on/after that date.
- Binary float is forbidden in business facts.
- Archive-derived `available_at` equals the observed retrieval time and every snapshot is `ARCHIVE_REPLAY_ONLY`.
- Market facts never write directly to the Economic Ledger.
- No API key, signed endpoint, account, Broker, order, or deployment capability is added.
- Existing Release Gates remain unchanged and fail closed.
- Final package version is `0.16.0`.

## File Structure

- Create `src/crypto_quant/market_data.py`: request, locator, response boundary, checksum/ZIP validation, family parsers, receipt, quality report, snapshot and fetch orchestration.
- Create `src/crypto_quant/market_data_cli.py`: structured fetch command and immutable artifact writes.
- Create `config/historical-market-data-snapshot-v1.schema.json`: strict artifact contract.
- Create `config/fee-schedule-snapshot-v1.schema.json`: separate effective-dated cost contract.
- Create `tests/test_market_data.py`: pure contract, security, parser, quality and deterministic artifact tests.
- Create `tests/test_market_data_cli.py`: GET-only transport and CLI integration tests.
- Create `artifacts/market-data/binance-public-data-smoke-v0.16.0.json`: small real-source receipt and quality summary, without raw market data.
- Modify `README.md`, `pyproject.toml`, `src/crypto_quant/__init__.py`, `src/crypto_quant/build.py`, and `config/evaluator-build-manifest-v1.json`.
- Create `docs/adr/0016-public-historical-data-provenance.md` and `docs/implementation-status-v0.16.0.md`.

---

### Task 1: Freeze Requests, Paths, Checksums, and Archive Safety

**Files:**

- Create: `tests/test_market_data.py`
- Create: `src/crypto_quant/market_data.py`

**Interfaces:**

- `HistoricalArchiveRequest.create(...)`
- `HistoricalArchiveRequest.archive_url`
- `HistoricalArchiveRequest.checksum_url`
- `verify_official_checksum(request, archive_bytes, checksum_bytes) -> VerifiedArchive`
- `extract_expected_csv(request, verified_archive)`

- [ ] **Step 1: Write failing request/locator tests**

Add literal expected URLs for all four supported family shapes and tests that reject wrong symbols, family/market combinations, intervals, period kinds and malformed dates/months.

```python
def test_spot_daily_kline_request_has_exact_allowlisted_urls(self): ...
def test_monthly_usdm_funding_request_has_exact_urls_without_interval(self): ...
def test_request_rejects_unsupported_or_ambiguous_combinations(self): ...
```

Mutation target: changing a path component, allowing an arbitrary symbol or accidentally assigning an interval to Funding makes a test fail.

- [ ] **Step 2: Verify RED**

```bash
python -m unittest \
  tests.test_market_data.HistoricalArchiveRequestTests -v
```

Expected: import failure because `crypto_quant.market_data` does not exist.

- [ ] **Step 3: Implement the immutable request and locator**

Use enums or validated strings internally. Generate URLs from constants only. Require exact uppercase symbols and UTC calendar period syntax. Expose no URL constructor parameter.

- [ ] **Step 4: Verify focused GREEN**

```bash
python -m unittest \
  tests.test_market_data.HistoricalArchiveRequestTests -v
```

- [ ] **Step 5: Write failing checksum and ZIP safety tests**

Use hand-built in-memory ZIP bytes and literal SHA-256 text. Cover success plus:

- checksum digest mismatch;
- checksum filename mismatch;
- malformed/oversized checksum text;
- multiple members;
- unexpected member;
- absolute path or `..`;
- encrypted flag;
- compressed/uncompressed size and compression-ratio limits;
- malformed archive.

Assert stable `MarketDataError` reason codes, not incidental library error text.

- [ ] **Step 6: Verify RED**

```bash
python -m unittest \
  tests.test_market_data.ArchiveIntegrityTests -v
```

Expected: missing validation functions.

- [ ] **Step 7: Implement minimal checksum and ZIP validation**

Parse exactly one ASCII checksum record, compare the expected filename and use `hmac.compare_digest` on lowercase SHA-256 values. On success, return an opaque `VerifiedArchive` capability bound to the validated request and archive bytes. `extract_expected_csv` accepts only that capability, never raw archive bytes. Inspect all ZIP metadata before reading the single expected CSV. Enforce both declared and actual byte limits.

- [ ] **Step 8: Verify GREEN and commit**

```bash
python -m unittest \
  tests.test_market_data.HistoricalArchiveRequestTests \
  tests.test_market_data.ArchiveIntegrityTests -v
git add src/crypto_quant/market_data.py tests/test_market_data.py
git commit -m "feat: add safe public archive boundary"
```

---

### Task 2: Normalize Market Facts and Enforce Data Quality

**Files:**

- Modify: `tests/test_market_data.py`
- Modify: `src/crypto_quant/market_data.py`
- Create: `config/historical-market-data-snapshot-v1.schema.json`
- Create: `config/fee-schedule-snapshot-v1.schema.json`

**Interfaces:**

- `parse_market_facts(request, csv_bytes, ingested_at)`
- `build_historical_market_data_snapshot(...)`
- `historical_market_data_snapshot_hash(snapshot)`
- `historical_market_data_snapshot_reasons(snapshot)`
- `fee_schedule_snapshot_hash(snapshot)`

- [ ] **Step 1: Write failing Spot Kline/AggTrade parser tests**

Use literal 2024 millisecond and 2025 microsecond fixtures. Assert exact UTC timestamps and Decimal strings. Add invalid column count, header, boolean, ID order, numeric, time and OHLC relation cases.

```python
def test_spot_kline_timestamp_unit_changes_at_2025_boundary(self): ...
def test_spot_aggtrade_normalizes_exact_decimal_and_business_id(self): ...
def test_spot_parsers_reject_malformed_business_values(self): ...
```

- [ ] **Step 2: Verify RED**

```bash
python -m unittest tests.test_market_data.SpotParserTests -v
```

- [ ] **Step 3: Implement strict Spot parsers**

Parse with `csv.reader`, reject unknown headers, normalize via fixed `Decimal` context and generate deterministic fact IDs from source row identity plus business key.

- [ ] **Step 4: Write failing USDⓈ-M Mark/Funding tests**

Assert mark Kline OHLC/time rules and Funding Rate `calc_time`, exact negative/positive rate preservation, symbol consistency and strict columns.

- [ ] **Step 5: Verify RED**

```bash
python -m unittest tests.test_market_data.UsdMParserTests -v
```

- [ ] **Step 6: Implement the two USDⓈ-M parsers**

Keep Funding Rate as a market/cost input fact; do not create a cashflow.

- [ ] **Step 7: Write failing quality, artifact and schema tests**

Cover:

- exact source order and duplicate detection;
- Kline interval gaps;
- expected daily/monthly period coverage;
- receipt, report and snapshot self-hashes;
- mutation after rehash;
- deterministic replay;
- `event_time <= available_at <= ingested_at <= recorded_at`;
- fixed `ARCHIVE_REPLAY_ONLY`;
- strict JSON schemas with no unknown business fields;
- separate Fee Schedule effective intervals, Decimal rates, lifecycle and approval fields.

- [ ] **Step 8: Verify RED**

```bash
python -m unittest \
  tests.test_market_data.MarketDataArtifactTests \
  tests.test_market_data.FeeScheduleContractTests -v
```

- [ ] **Step 9: Implement artifact builders, semantic validation and schemas**

Reuse existing `business_hash` and `artifact_self_hash` patterns. A blocking quality finding makes snapshot construction fail; warnings remain hashed evidence. Fee Schedule validation must reject unapproved production use and overlapping/invalid effective intervals.

- [ ] **Step 10: Verify GREEN and commit**

```bash
python -m unittest tests.test_market_data -v
python -m unittest tests.test_canonical tests.test_contracts tests.test_economics -v
git add \
  src/crypto_quant/market_data.py \
  tests/test_market_data.py \
  config/historical-market-data-snapshot-v1.schema.json \
  config/fee-schedule-snapshot-v1.schema.json
git commit -m "feat: normalize historical market data evidence"
```

---

### Task 3: Add the GET-only Fetch Workflow and CLI

**Files:**

- Create: `tests/test_market_data_cli.py`
- Modify: `src/crypto_quant/market_data.py`
- Create: `src/crypto_quant/market_data_cli.py`

**Interfaces:**

- `HttpResponse`
- `PublicArchiveTransport.get(url)`
- `fetch_historical_market_data(request, transport, retrieved_at)`
- `market_data_cli.main(argv=None)`

- [ ] **Step 1: Write failing orchestration tests with a complete in-memory transport**

The fake returns full HTTP status, final URL, headers and body for both archive and checksum URLs. Assert only the resulting receipt/snapshot behavior, including:

- exactly two allowlisted GET requests;
- redirect final host rejection;
- non-200, missing response metadata and content limit rejection;
- official checksum verified before parser invocation;
- receipt binds response ETag/Last-Modified when present;
- no authentication/header input exists.

- [ ] **Step 2: Verify RED**

```bash
python -m unittest tests.test_market_data_cli.FetchWorkflowTests -v
```

- [ ] **Step 3: Implement transport boundary and fetch orchestrator**

Use `urllib.request` only in the concrete transport. Restrict method and redirect destination, use bounded reads, a finite timeout and a small fixed retry count only for safe public GET failures.

- [ ] **Step 4: Write failing CLI tests**

Invoke `main([...])` against injected transport/clock/output path. Assert:

- valid structured arguments produce canonical receipt, quality and snapshot JSON;
- no URL/API-key/order/account arguments exist;
- existing identical artifact is idempotent;
- existing conflicting bytes fail without overwrite;
- partial failure leaves no final artifact;
- output uses an explicit directory below the caller-selected root.

- [ ] **Step 5: Verify RED**

```bash
python -m unittest tests.test_market_data_cli.MarketDataCliTests -v
```

- [ ] **Step 6: Implement CLI and atomic immutable writes**

Write to a same-directory temporary file, fsync, and publish with no-overwrite semantics. Output a concise JSON summary to stdout and errors to stderr with a non-zero status.

- [ ] **Step 7: Verify GREEN and commit**

```bash
python -m unittest tests.test_market_data tests.test_market_data_cli -v
git add \
  src/crypto_quant/market_data.py \
  src/crypto_quant/market_data_cli.py \
  tests/test_market_data_cli.py
git commit -m "feat: add get-only market data fetch workflow"
```

---

### Task 4: Capture Real Smoke Evidence and Publish v0.16.0

**Files:**

- Create: `artifacts/market-data/binance-public-data-smoke-v0.16.0.json`
- Create: `docs/adr/0016-public-historical-data-provenance.md`
- Create: `docs/implementation-status-v0.16.0.md`
- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `src/crypto_quant/__init__.py`
- Modify: `src/crypto_quant/build.py`
- Modify: `config/evaluator-build-manifest-v1.json`

- [ ] **Step 1: Execute one real official archive smoke ingestion**

Use a recent completed ETHUSDT Spot daily 4h archive. Do not commit the raw ZIP or normalized row payload. Generate a compact evidence document containing request, official/archive/checksum hashes, receipt hash, row count, quality report hash, snapshot hash, retrieval time and `ARCHIVE_REPLAY_ONLY`.

If the remote archive is genuinely unavailable, record a fail-closed smoke result with status/error evidence; do not fabricate success and do not block unit-level release.

- [ ] **Step 2: Independently verify the smoke receipt**

Re-download the official `.CHECKSUM`, confirm it matches the recorded archive SHA-256, then re-run the importer against the retained temporary raw bytes and compare snapshot/report hashes before deleting temporary data.

- [ ] **Step 3: Add ADR, README, and implementation status**

Explain:

- why official archives are replay-only;
- why source URL is not artifact identity;
- why fee schedules are separate;
- which data families remain missing;
- why this version cannot claim profitability or PIT-valid OOS evidence;
- the next step: contemporaneous capture plus real offline Paper artifacts.

- [ ] **Step 4: Update version and frozen evaluator build**

Set package and module version to `0.16.0`. Include new code, schemas and smoke evidence in the evaluator build manifest using existing repository conventions. Regenerate and verify the build hash.

- [ ] **Step 5: Run focused and full verification**

```bash
python -m unittest tests.test_market_data tests.test_market_data_cli -v
python -m unittest discover -s tests -v
python -m crypto_quant.build verify
python -m crypto_quant.estimators golden
git diff --check
git status --short
```

Expected:

- all tests pass;
- evaluator build verifies;
- Golden report hash remains intentionally unchanged unless a reviewed manifest binding requires regeneration;
- only planned v0.16 files are modified.

- [ ] **Step 6: Commit documentation and release metadata**

```bash
git add \
  artifacts/market-data/binance-public-data-smoke-v0.16.0.json \
  docs/adr/0016-public-historical-data-provenance.md \
  docs/implementation-status-v0.16.0.md \
  README.md pyproject.toml src/crypto_quant/__init__.py \
  src/crypto_quant/build.py config/evaluator-build-manifest-v1.json
git commit -m "chore: publish historical data build v0.16.0"
```

- [ ] **Step 7: Review, merge, tag, and verify clean main**

Run the code-review checklist against the design and plan, fix only evidence-backed findings, merge the isolated branch to `main`, rerun the full suite and build verification, then:

```bash
git tag -a v0.16.0 -m "v0.16.0 historical market data ingestion"
git status --short
git log --oneline --decorate -8
```

Expected: clean `main` at the reviewed release commit with tag `v0.16.0`.
