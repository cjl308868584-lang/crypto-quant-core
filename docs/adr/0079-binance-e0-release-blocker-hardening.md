# ADR 0079: Binance E0 release-blocker hardening

## Decision

Release v0.78.1 as a patch on the v0.78 line. It normalizes natural Binance
JSON, reconciles non-USDT Spot fees and marked Spot equity, refreshes signed
time evidence, adds a reduce-only emergency flatten, rechecks the E0 capital
envelope immediately before every mutating send, and exposes one fixed-shape
Binance-only command boundary.

The command boundary accepts only `account-preflight`, `private-runtime` for an
already committed ETHUSDT opportunity, and `emergency-stop` for such an
opportunity. Runtime and authority paths, venue, products, endpoints and risk
limits are release-fixed. This is not a generic broker or deployment service.

## Safety boundary

`production_activation=false`

`no service installed or started`

`no credential created or read`

`no private Binance request made`

`no order submitted`

`no funds moved`

The release candidate uses only fixtures and patched transports. Real account
approval, a repository-external owner-only credential reference, activation,
funding and any order remain separate external actions. v0.78.1 does not
create v0.79 and does not modify the public v0.78 simulation service snapshot.
