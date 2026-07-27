# Paper Account-Cost Binding Implementation Plan

**Goal:** Rebase an existing replay-verified ETHUSDT offline Paper result onto
a contemporaneous replay-verified account commission context, while preserving
all signals, fills, slippage and market facts.

## Task 1: source and PIT gates

1. Require complete Paper and account commission source objects.
2. Require their independently retained external trust hashes.
3. Re-run both existing semantic validators.
4. Require account observation before Paper decision and validity through run
   end.
5. Reject wrong symbol, expired, post-decision or non-current context.

## Task 2: exact fee-only replay

1. Freeze a v1 account-cost replay policy.
2. Reconstruct entry/exit notional and original 15-bps costs.
3. Apply authoritative no-discount taker-buy/taker-sell rates with Decimal.
4. Recompute ending liquidation equity and net change.
5. Keep signal, quantity, prices, slippage and market hashes unchanged.
6. Support no-trade cycles with exactly zero fee delta.

## Task 3: Artifact and replay

1. Add mirrored strict JSON Schema.
2. Embed both complete source Artifacts.
3. Bind source trust hashes, PIT facts, fee math and eligibility.
4. Add self-hash and external binding attestation.
5. Rebuild the entire result from embedded sources during validation.
6. Reject source, rate, cost, equity, hash, warning and eligibility mutations.

## Task 4: release

1. Add exact fee, no-trade, PIT, source trust and mutation tests.
2. Freeze explicit no-real-account integration evidence.
3. Add ADR-0023, v0.23 implementation status and README update.
4. Bump package/build versions and freeze new inputs.
5. Run focused tests, full tests, compileall, Golden Vectors and validators.
6. Commit the isolated implementation, fast-forward main and tag v0.23.0.
