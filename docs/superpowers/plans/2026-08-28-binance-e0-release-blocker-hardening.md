# Binance E0 Release-Blocker Hardening Implementation Plan

Base: v0.78 candidate commit `047bc49`. Branch:
`codex/v0.78.1-binance-canary-hardening`. No install, live request, credential,
order, fund movement, merge or tag is part of this plan.

## Task 1 — External JSON normalization

Files: lifecycle, reconciliation, official response fixtures and focused tests.

1. RED: prove natural official Query Order/myTrades JSON is rejected today;
   cover optional fields, reordering, duplicates, floats and missing identity.
2. GREEN: split bounded duplicate-safe JSON parsing from endpoint normalization;
   remove only the external-byte canonical equality requirement.
3. Keep canonical equality for every internal artifact/event/capture.
4. Run lifecycle/reconciliation focused tests and commit.

## Task 2 — Spot fees and mark-to-market

Files: reconciliation, runtime capture builder, fixtures and tests.

1. RED: BNB/base/quote commissions, missing conversion mark, nonzero Spot
   unrealized PnL and same-bytes replay.
2. Add closed captured mark map and exact fee conversion.
3. Derive wallet/equity/unrealized values from trusted balances and mark.
4. Run reconciliation/runtime adjacent tests and commit.

## Task 3 — Per-action server time and prepared supersession

Files: private protocol/runtime/event contract and tests.

1. RED: two signed actions currently share one timestamp; prepared-unsent retry
   cannot safely refresh; UNKNOWN must remain no-resend.
2. Persist one time observation per signed action and add the minimal closed
   unsent supersession transition after proven absence.
3. Preserve all existing SENT_STARTED/UNKNOWN idempotency.
4. Run protocol/runtime/event/fault focused tests and commit.

## Task 4 — Emergency perpetual flatten

Files: lifecycle/runtime/protective-stop contract and tests.

1. RED each stop failure boundary with existing exposure.
2. Add the fixed internal authorization and deterministic reduce-only query-first
   close; no public arbitrary flatten API.
3. Verify flat, partial, UNKNOWN, duplicate response and restart behavior.
4. Run protective-stop/runtime/reconciliation tests and commit.

## Task 5 — Final send capital guard

Files: transport/runtime/controller and tests.

1. RED current E0 quantity=1000 acceptance and cross-product exposure.
2. Add pure worst-case post-send exposure calculation using trusted price and
   position and invoke it directly before mutating transport.
3. Verify inclusive 50 USDT/0.5x boundary, no entry above it and unrestricted
   exact reduce-only exits without reversal.
4. Run transport/runtime/controller tests and commit.

## Task 6 — Minimal runnable CLI and orchestration

Files: one Binance-specific orchestration module, one CLI, fixed config/schema,
packaging/build inventory, runbook and tests.

1. RED parser authority, missing/unsafe file, zero-default, redaction and fake
   transport end-to-end tests.
2. Implement fixed-path account-preflight, one-opportunity runtime and emergency
   stop commands by composing existing v0.77 components.
3. No generic service/deployment framework and no inclusion in the v0.78 public
   simulation snapshot.
4. Run focused and adjacent tests and commit.

## Task 7 — Release candidate gates

1. Update patch version/build manifest/ADR/status/dependency and runbook text.
2. Independent complete review; fix Critical/Important findings with targeted
   RED/GREEN and targeted rereview.
3. Run the final affected suite, one full suite, compileall, `make validate` and
   `git diff --check` once for the final code state.
4. Stop with a local release candidate. Do not merge/tag/install/start or use a
   credential/account/order without the separate external approvals.

