# Perpetual Context Implementation Plan

**Goal:** Capture and replay current ETHUSDT USDⓈ-M Mark, Index, Premium, OI
and Funding context, including explicit per-1000-USDT SHORT funding scenarios.

## Task 1: request and transport boundary

1. Freeze five exact public Futures request objects.
2. Add no-proxy, same-host, bounded one-attempt HTTPS transport.
3. Reject arbitrary URLs, redirects, credentials and malformed responses.
4. Gate all Futures calls on a valid v0.20 server-time probe.

## Task 2: parsers and time quality

1. Strictly parse premium/mark, premium klines, current OI, OI history and
   Funding history.
2. Preserve raw receipts and exact Decimal strings.
3. Enforce symbol, ordering, source timestamps and trusted capture window.
4. Derive observed Funding interval only from consistent settlement times.

## Task 3: profitability context

1. Compute exact basis amount/rate and OI 4h change.
2. Compute next Funding cashflow per 1000 USDT for SHORT.
3. Compute repeated-current-rate and 2x adverse 24h scenarios only when the
   interval is proven.
4. Keep scenario values separate from realized economic PnL.

## Task 4: Artifact and CLI

1. Add strict governance/package JSON Schema.
2. Rebuild every observation and scenario from raw receipts.
3. Add self-hash and external attestation.
4. Publish immutably through a one-shot credential-free CLI.
5. Expose no URL/header/key/account/order/time overrides.

## Task 5: release

1. Run fixture, mutation, transport and blocked-clock tests.
2. Attempt a real direct official Futures capture.
3. If the host remains unreachable, freeze explicit failure evidence rather
   than substituting another source.
4. Update ADR, implementation status, README and evaluator build.
5. Run focused/full tests and all validators.
6. Merge main and tag v0.21.0.
