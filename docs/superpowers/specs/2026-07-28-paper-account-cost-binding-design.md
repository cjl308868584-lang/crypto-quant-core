# Paper Account-Cost Binding Design

## Goal

Bind a replay-verified current ETHUSDT account commission snapshot to the
existing offline Paper run, then recompute the Paper run's fee-only economic
effect without changing its signal, fill, slippage, quantity, price or market
observations.

This closes the code-path gap between v0.22 account commission evidence and
v0.18 Paper economics. It does not turn a current rate into historical data,
does not create a new fill, and does not prove profitability.

## Inputs and trust

The builder accepts:

1. a complete `offline-paper-run-v1` object;
2. the externally retained trust hash for that Paper run;
3. a complete `account-commission-snapshot-v1` object;
4. the externally retained trust hash for that account snapshot;
5. a caller-supplied UTC creation time.

Both source objects must pass their existing Schema, self-hash, semantic replay
and external-attestation validation before any cost result is emitted. Copies
of source trust hashes are lineage fields only; callers must still retain and
provide the trusted values outside the Artifact.

## Point-in-time boundary

The account commission `observed_at` must be no later than the Paper
`decision_time`, and its `valid_until` must be no earlier than the Paper
`run_end`. This proves the current rate was available before the decision and
remained valid through the simulated execution window.

A later current rate may never be applied backward. An expired or post-decision
snapshot fails closed. The symbol must be ETHUSDT and the bound context must be
Spot no-discount account commission.

## Fee-only replay

For a filled baseline Spot BUY:

- entry notional is replayed from quantity × fill price;
- conservative exit notional is replayed from the final economic equity point;
- the original 15-bps entry and exit fees are independently reconstructed;
- account entry fee uses the authoritative `taker_buy` rate;
- account exit fee uses the authoritative `taker_sell` rate;
- rebased ending liquidation equity equals original ending liquidation equity
  minus `(account total fee - assumed total fee)`.

All business arithmetic uses exact Decimal. A binary float, noncanonical
decimal, inconsistent notional, unexpected side, extra fill, modified source
or fee mismatch fails closed.

For a valid no-trade baseline cycle, both assumed and account fees are zero and
ending equity is unchanged. The AI arm remains explicitly not run.

## Artifact

`paper-account-cost-binding-v1` embeds both complete replayable sources and
stores:

- source hashes and lineage attestations;
- PIT validity facts;
- the frozen fee policy and no-discount account rates;
- original versus account-costed entry/exit/total fees;
- fee delta;
- original and rebased liquidation equity/net change;
- a strict self-hash and external binding attestation hash;
- explicit research-only and insufficient-duration eligibility.

The strict top-level Schema is mirrored in package resources. Semantic
validation rebuilds the entire binding from the two embedded sources.

## Security and non-goals

The binding performs no network request, reads no credential and submits no
order. It never adds account balances, positions, fills or secrets. It cannot:

- authorize production or live trading;
- infer BNB payment balance;
- backfill historical commission;
- alter signal, slippage, fill probability or market observations;
- count fixture validation as real account evidence;
- claim AI superiority or 90-day profitability.

## Release evidence

Because the repository has no real account commission snapshot, v0.23 freezes a
`NOT_RUN_FAIL_CLOSED` integration evidence record. Deterministic fixtures prove
the builder, mutation rejection and exact fee math, but are not stored as real
account evidence.
