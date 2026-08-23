# ADR-0069: Decision Opportunity and Binance Canary Preregistration

## Status

Accepted for v0.69.0. Runtime execution is not authorized.

`PLAN_FROZEN_REPLACEMENT_V3_NOT_STARTED`

## Context

The v0.62/v0.64 replacement design inherited a confirmatory rule in which a
single missing four-hour slot could permanently invalidate a 540-slot cohort.
That rule made missing evidence visible, but it confused an operational outage
with an irreversible research failure and encouraged more scheduler machinery.
The project needs to preserve the valuable part—auditable evidence and
fail-closed behavior—without backfilling observations or pretending elapsed
time can be compressed.

The user also approved a bounded path toward a future first-money Canary. That
path must not replace the independent 90-day economic study and must not grant
credentials, installation, startup or order authority in this release.

## Decision

v0.69.0 explicitly supersedes the pre-start replacement plan with v3. Every
scheduled four-hour boundary becomes a `DecisionOpportunity` whose only
terminal outcomes are `OBSERVED` and `MISSED`. A missed opportunity is appended
with its real detection time and reason, is never reconstructed or backfilled,
and does not prevent a later opportunity from being observed. The append-only
opportunity log remains the future authority.

Two gates remain independent:

- operational qualification requires at least seven real calendar days, 95%
  observed coverage and at least three complete strategy cycles; insufficient
  coverage or anomalies extend the window automatically;
- economic evaluation requires its own 90 real calendar days and its frozen
  evaluator. An operational pass cannot be reported as profitability.

The future Canary is preregistered for Binance only. Position state is mutually
exclusive among flat, unmargined ETH/USDT spot long and ETHUSDT USDⓈ-M
perpetual short. Reversal requires verified flat first. Perpetual configuration
is one-way and isolated, with a technical 2x cap; E0 starts at 100 USDT and
0.5x, E1 at 300 USDT and 1x, and E2 at no more than 1,000 USDT and 2x. Each
stage has its fixed elapsed-time, strategy-cycle and spot/perpetual round-trip
requirements. Promotion is never automatic.

Risk and reconciliation remain fail-closed. Unresolved `UNKNOWN`, a duplicate
economic order, an unrecorded fill, ledger/position disagreement, a missing
disaster stop, insufficient connectivity, or an S0/S1 incident blocks or fails
the relevant stage. Future credentials must be owner-only outside the
repository, withdrawal-disabled, IP-allowlisted and minimally scoped.

## Supersession evidence

The v3 plan was frozen before any v3 runtime start. The ceremony binds the
immutable v0.64 plan, released v0.68 foundation, a machine snapshot reporting
`NO_OBSERVABLE_REPLACEMENT_STATE_AT_COLLECTION`, and the user's accountable
owner attestation. The snapshot proves only what was observable at collection;
the historical never-started statement remains a governance attestation, not
an OS-proven fact.

During C3, production loaders replayed all three new formal artifacts and
recomputed the exact supersession record before commit. The pre-artifact test
set contained an obsolete absence assertion and omitted the intended committed
artifact regression class. No signed artifact or frozen H was modified. At C4,
v0.69 added the permanent exact-byte/loader regression and removed only that
obsolete pre-ceremony assertion. This process correction is recorded rather
than hidden.

Independent release review then found that the original collector checked the
runtime root and plist before its transcript sequence but not again immediately
before publication, and that `assemble-record` relied on the recorded snapshot
without a fresh pre-start gate. The release candidate keeps the immutable
signed artifacts and their governance meaning, but fixes the reusable ceremony:
collection now rechecks root, plist and service after transcript capture and
again immediately before publish; assembly checks before replay and again
immediately before publish. Fixed tests prove that a newly visible event root,
plist or loaded service prevents publication. The signed owner declaration is
still explicitly a governance statement rather than resistance to a malicious
same-UID process, and the artifact is not relabelled as stronger machine proof.

## Authority boundary

This release is plan-only:

- `production_activation=false`
- `runtime_install_authorized=false`
- `replacement_start_authorized=false`
- `real_orders_allowed=false`
- `no seven-day timer started`
- `no 90-day timer started`

It installs no service, reads no credential, starts no runtime, requests no
account or market data, creates no order, and moves no funds. It is not evidence
of profit, AI advantage, Paper completion, Canary eligibility or live-trading
fitness.

## Consequences

v0.70 may implement the DecisionOpportunity event/evaluator/projection layer;
v0.71 may implement deterministic Binance simulation and reconciliation;
v0.72 or later may design a separate credential/install/activation trust chain.
Every later irreversible action retains its own explicit authority gate.
