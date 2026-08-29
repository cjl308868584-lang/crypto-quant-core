# ADR 0080: v0.78.2 activation release rebind

## Decision

Release a bounded `v0.78.2` patch that binds the replacement v3 simulation
renderer, install contract and packaged schema to the exact current public
release identity: package `0.78.2`, build manifest `1.74.0`, annotated tag
`v0.78.2`, and its identical `origin/main` peeled commit.

The v0.78.0 renderer correctly failed closed after v0.78.1 advanced
`origin/main`, but that made the frozen v0.78.0 installation ceremony
unreachable. The defect was discovered before renderer publication, preflight,
installation or service start. Moving `origin/main` backwards, forging a remote
reference, weakening the equality gate, or installing from an untagged tree is
forbidden. The patch changes release identity only; it does not add a new
scheduler, strategy, Broker, venue abstraction or UI.

## Safety boundary

- `production_activation=false`
- no service installed or started
- no credential created or read
- no private Binance request made
- no order submitted
- no funds moved

The renderer and installer remain separate post-release actions. This release
does not execute them and does not start the 72-hour qualification clock.
