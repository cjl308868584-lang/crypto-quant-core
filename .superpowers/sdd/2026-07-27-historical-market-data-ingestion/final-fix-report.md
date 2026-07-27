# v0.16 Historical Market Data Final-Fix Report

Date: 2026-07-27

Status: COMPLETE — ready for parent review; not merged or tagged

Implementation commits:

- `b09ff96 fix: close historical market data final review`
- `cc2dc45 fix: bind trust to complete market snapshots`

## Scope and outcome

This was the single final repair wave for the blocking v0.16 review. It closes
the one Critical and five Important finding groups, including the residual
snapshot-attestation finding discovered after the first report:

1. coordinated provenance forgery;
2. incomplete receipt, quality, fact, and snapshot contracts;
3. incomplete account-tier Fee Schedule contract;
4. hard-coded Funding interval/coverage behavior;
5. idempotent final-name TOCTOU.
6. receipt-only trust failed to bind snapshot-layer identity and time.

The final self-review also found one remaining authoritative-design mismatch:
facts lacked the fact-level `ingested_at` required by design section 6.3. That
field was added under a separate RED/GREEN cycle before the implementation
commit. Archive facts now enforce:

```text
event_time <= available_at
available_at == fact.ingested_at == snapshot.ingested_at
snapshot.ingested_at <= snapshot.recorded_at
```

The residual repair replaces receipt-only trust with a canonical external
snapshot-attestation envelope. The envelope is not stored in the snapshot and
therefore does not create a self-hash cycle. It binds attestation/schema/parser
versions, `snapshot_id`, `recorded_at`, `receipt_hash`, and `snapshot_hash`.

## Implemented repairs

### Provenance, trust, and complete market-fact replay

- Snapshot builders accept only the opaque verified-archive capability. The
  removed construction path cannot accept caller-provided facts, archive
  hashes, or checksum hashes.
- The capability carries the request, archive bytes, checksum bytes, and
  official digest. Construction re-verifies the checksum and archive before
  parsing.
- Every fact retains its strict source row, source-row hash, source-row
  identity, normalized payload hash, fact-level `ingested_at`, and complete
  family payload.
- Kline facts retain open/close time, OHLC, volume, quote volume, trade count,
  taker base/quote volume, and the validated ignore field.
- Validation reparses each source row with its request, row number, and
  snapshot ingestion time; it then compares the complete reconstructed fact,
  including the fact-level ingestion timestamp.
- The receipt binds the complete request, URLs, retrieval time, byte sizes,
  official/archive/checksum hashes, CSV member/hash, source-row root, facts
  root, and HTTP validators.
- The quality report binds all approved counters, coverage state, findings,
  and its self-hash.
- Snapshots bind parser version, conservative availability basis,
  `ARCHIVE_REPLAY_ONLY`, explicit quality eligibility, receipt/report/facts,
  all three snapshot times, and the snapshot self-hash.
- Self-hashes remain integrity mechanisms, not trust sources. Validation
  defaults to `TRUSTED_SNAPSHOT_ATTESTATION_REQUIRED`; an explicit but
  non-matching external anchor returns
  `TRUSTED_SNAPSHOT_ATTESTATION_MISMATCH`.
- The legacy `trusted_receipt_hashes` input cannot produce a complete PASS. If
  it is supplied without the external snapshot anchor, validation also returns
  `TRUSTED_RECEIPT_ATTESTATION_INSUFFICIENT`.

The final-review attack probes are covered:

- changing a normalized close and recomputing the snapshot hash is rejected by
  source-row parser replay;
- changing the raw CSV, ZIP, checksum, and all derived self-hashes still
  cannot match the originally stored snapshot-attestation anchor;
- changing only `recorded_at` or `snapshot_id` and recomputing the snapshot
  self-hash also cannot match the original external anchor.

### Fee Schedule

- The schema and runtime require venue, product, account tier, symbol,
  maker/taker rates, effective interval, source reference, recorded time,
  lifecycle, approval, and top-level content hash.
- Overlap is scoped to `(venue, product, account_tier, symbol)`.
- Structurally valid `RESEARCH` contracts remain usable for research.
- `usage_environment=PRODUCTION` always returns
  `FEE_SCHEDULE_PRODUCTION_UNSUPPORTED`; caller-filled approval text and a
  recomputed content hash cannot create a production approval path.

### Funding coverage and degraded research

- `funding_interval_hours` is a strict source integer in `1..24`.
- Continuity uses the current row's source interval, so an in-month schedule
  change is valid.
- Month-start and month-end checks are conservative.
- `missing_interval_count` counts each missing source interval when the
  schedule makes that count exact.
- The strict builder rejects gaps.
- The separate degraded builder permits only coverage/gap findings, emits
  `RESEARCH_ONLY_DEGRADED`, and always validates with a non-empty degradation
  reason. Duplicate facts and other integrity failures remain rejected.

### Immutable CLI publication

- Existing final artifacts are read together with their inode identity and
  re-stat'ed through the final name.
- Both idempotent return paths—the pre-existing artifact path and the
  concurrent link-collision path—reopen the final name at the commit point and
  require the same inode and identical bytes.
- Concurrent same-byte rename/replacement probes fail with
  `ARTIFACT_OUTPUT_INVALID`.
- The CLI computes the external snapshot-attestation hash before the immutable
  publish commit point and exposes it in its success summary, so callers can
  persist it separately without adding fallible post-commit work.

### Packaging and frozen evaluator build

- Governance and packaged schemas are byte-identical.
- The wheel smoke uses the v0.16.0 filename and enforces offline pip mode.
- Evaluator manifest version is `1.11.0` and binds 54 inputs.
- Build input tree hash:
  `8b8e759e226acb57d79ca9c9161e5d226b86c17effa9116c924e6f027611a544`
- Evaluator build hash:
  `2538bc3eec3a33a921cc7141d118bd4277eb9d703eeabeedf3d71d3267c8121f`

## TDD evidence

All production changes were driven by a failing test first.

### Provenance and complete contract

Initial RED:

- three provenance/contract tests failed;
- the strong builder calls raised `TypeError` because only the weak
  caller-assembled interface existed;
- a fully coordinated forged artifact validated with no reasons when no
  independent trust anchor was supplied.

GREEN:

```text
Ran 3 tests
OK
```

### Fee Schedule

Initial RED:

- all three tests failed because the schema lacked the content hash and full
  tier/effective/source/lifecycle fields;
- the runtime accepted the incomplete shape;
- production did not fail unconditionally.

GREEN:

```text
Ran 3 tests
OK
```

### Funding schedule and degraded research

Initial RED showed the schedule-change rows rejected as
`MARKET_FACT_INVALID` and the gap path returned the wrong behavior. A further
RED proved that the degraded path admitted a duplicate source fact. Another
RED showed two removed 8-hour source intervals were counted as one.

GREEN covered schedule changes, strict interval bounds, strict-builder gap
rejection, research-only degradation, duplicate rejection, and exact missing
count:

```text
Ran 5 tests
OK
```

### CLI final-name commit point

Initial RED:

```text
two tests: expected exception was not raised
```

GREEN:

```text
Ran 2 tests
OK
```

### Wheel and manifest metadata

- Wheel mock RED exposed `0.15.0`; GREEN uses `0.16.0`.
- Evaluator-manifest assertion RED exposed `1.9.0`; the initial final wave
  bound `1.10.0`, and the committed residual attestation input change advances
  the manifest to `1.11.0`.

### Fact-level `ingested_at` final self-review

Explicit RED command:

```text
PYTHONPATH=src python3 -m unittest \
  tests.test_market_data_final_review.ProvenanceAndApprovedContractTests.test_fact_contract_carries_ingested_at_and_schema_requires_it \
  tests.test_market_data_final_review.ProvenanceAndApprovedContractTests.test_fact_ingested_at_must_crosslink_snapshot_and_source_row_replay -v
```

RED result:

```text
KeyError: 'ingested_at'
AssertionError: 'MARKET_DATA_FACT_TIME_CROSSLINK' not found
Ran 2 tests
FAILED (failures=1, errors=1)
```

GREEN result after runtime/schema/replay repair:

```text
Ran 2 tests in 0.067s
OK
```

### External snapshot-attestation residual

Before adding the tests, the reviewer attacks were reproduced directly against
the receipt-only API:

```text
recorded_at_rewrite_reasons=()
snapshot_id_rewrite_reasons=()
```

The two reviewer probes were then added before production implementation:

```text
PYTHONPATH=src python3 -m unittest \
  tests.test_market_data_final_review.ProvenanceAndApprovedContractTests.test_external_snapshot_attestation_rejects_recorded_at_rewrite \
  tests.test_market_data_final_review.ProvenanceAndApprovedContractTests.test_external_snapshot_attestation_rejects_snapshot_id_rewrite -v
```

RED result:

```text
ImportError: cannot import name
'historical_market_data_snapshot_attestation_hash'
Ran 2 tests
FAILED (errors=2)
```

GREEN result after adding the external envelope/hash, validator anchor, legacy
receipt insufficiency reason, builder self-check, and CLI output:

```text
Ran 2 tests in 0.080s
OK
```

## Real official smoke

Request:

```text
Binance Public Data
SPOT / KLINES / ETHUSDT / 4h / DAILY / 2026-07-25
```

The production CLI made the allowlisted public GETs without credentials. A
second independent GET of both the ZIP and `.CHECKSUM` was replayed with the
same observation time. The full snapshot dictionaries and canonical snapshot
bytes were identical, and both executions produced the same external
snapshot-attestation hash.

- Retrieved at: `2026-07-27T11:07:08.007133Z`
- Independently verified at: `2026-07-27T11:09:31.022716Z`
- Archive ETag: `"cbc72817e886639cc48397c0290934bb"`
- Archive Last-Modified: `Sun, 26 Jul 2026 02:41:56 GMT`
- Archive SHA-256:
  `a1f42574c036d4ae7670bb163dc1b787acf20f06bee958c32e736186757dc08b`
- CHECKSUM file SHA-256:
  `2413eb36a0d9f1fa90bea973bdf0c8dd0e15e4306c21427b5f543f09ceb55897`
- CSV SHA-256:
  `d132b8175bdf452165af93d0cd63e7cd2cf20bf40955218fc050ade702ca6935`
- Source-row root:
  `9f8a6349342061ce65bea467bd5f1ac1619e481fed945c852ad15ad81eb70cbf`
- Facts root:
  `c315367ef3b9fd664118c972dc57fe0ad67c6959b7d74b8ae777b9f3cb099039`
- Receipt hash:
  `fb70e609054a1d32c5a350bb4b623a076ac46c605e0236611726c5a5190b6b84`
- Quality report hash:
  `6e1a9aab31fbdae54fbac2fd34fc366d2f09bca546574a178feb4c7e46351b60`
- Snapshot hash:
  `0930b265622811a4d73e9704f4eab0ddd1d7b0bf62ee248934553d55538d324a`
- Trusted external snapshot-attestation hash:
  `042f6bcfa291f7343b1b3b0f8e1fbcba209f7d29eb825ac1b487b35372c00d2d`
- Full temporary snapshot SHA-256:
  `6dd0ac74a3cfbf4e2a7833d853fe067fd1953e7770ca223a5690ecdf1c93b9b3`
- Row count: 6
- All fact time cross-links: pass
- Trusted validation reasons: `[]`
- Unanchored validation reasons:
  `["TRUSTED_SNAPSHOT_ATTESTATION_REQUIRED"]`
- Receipt-only validation reasons:
  `["TRUSTED_RECEIPT_ATTESTATION_INSUFFICIENT",
  "TRUSTED_SNAPSHOT_ATTESTATION_REQUIRED"]`
- `recorded_at=2099` rewrite reasons:
  `["TRUSTED_SNAPSHOT_ATTESTATION_MISMATCH"]`
- `snapshot_id` rewrite reasons:
  `["TRUSTED_SNAPSHOT_ATTESTATION_MISMATCH"]`

The temporary full-snapshot directory was moved to the system Trash and its
original path was verified absent. No raw ZIP, full CSV, normalized row file,
or full snapshot was committed. Only the compact smoke document remains:
`artifacts/market-data/binance-public-data-smoke-v0.16.0.json`.

## Final verification

Focused market-data suite:

```text
PYTHONPATH=src python3 -m unittest \
  tests.test_market_data \
  tests.test_market_data_cli \
  tests.test_market_data_final_review -q

Ran 75 tests in 92.357s
OK
```

Full suite:

```text
PYTHONPATH=src python3 -m unittest discover -s tests -v

Ran 291 tests in 117.408s
OK
```

Offline packaged-wheel/schema suite:

```text
PYTHONPATH=src python3 -m unittest \
  tests.test_market_data.PackagedMarketSchemaTests -v

Ran 3 tests in 0.894s
OK
```

The following also completed successfully:

```text
PYTHONPATH=src python3 -m crypto_quant.build verify
PYTHONPATH=src python3 -m crypto_quant.estimators golden
python3 -m compileall -q src/crypto_quant
git diff --check
```

Additional verified values:

- Governance/package schema copies: byte-identical
- JSON Schema Draft 2020-12 meta-validation: pass
- Executable estimators: 26
- Explicitly unavailable estimators: 32
- Golden vectors: 41/41 pass
- Golden report hash:
  `e3e7dc45865d860489514a574c64ca14a8dd6f089a0b74129414231741882fc3`

## Final self-review

- No caller-assembled strong snapshot path remains.
- No artifact can validate completely without a separately supplied external
  snapshot-attestation anchor; receipt-only trust is explicitly insufficient.
- The external envelope binds receipt provenance to the complete snapshot
  self-hash without being inserted into that self-hash.
- Rewriting snapshot identity, recorded time, or any other snapshot field and
  recomputing the self-hash invalidates the original external anchor.
- Full fact replay covers strict raw rows, family payloads, identities, and
  fact/snapshot ingestion cross-links.
- Degraded Funding data remains research-only and cannot become formal or PIT
  eligible.
- Fee Schedule production use has no caller-controlled approval bypass.
- Both idempotent publish return paths bind final-name inode and bytes.
- No credentials, account endpoints, POST/order behavior, Broker adapter,
  EconomicLedger writes, or profitability/PIT-valid claims were introduced.
- No raw market-data payload was committed.
- No merge, tag, or push was performed.

Residual product limitations are intentional and documented: public historical
archives remain `ARCHIVE_REPLAY_ONLY`; contemporaneous capture, real
account-specific fees/fills/slippage/funding cashflows, and real offline Paper
artifacts are still absent. Downstream callers must persist the CLI's
snapshot-attestation hash in a separate trusted store; recomputing it from an
Artifact under validation does not create trust and is intentionally
insufficient.
