# ADR 0078: Replacement v3 simulation activation trust chain

## Status

Accepted for the v0.78 code release with status
`V3_SIMULATION_ACTIVATION_TRUST_CHAIN_CODE_RELEASED_NOT_INSTALLED`.

`production_activation=false`

`no service installed or started`

`no credentials`

`no real orders`

`no funds moved`

## Decision

v0.78 is the final code release required to install and naturally start the
replacement-v3 public-market simulation. It binds the v0.78 release to a
minimal immutable snapshot, owner-only runtime and event roots, a fixed
LaunchAgent plist, a 30-minute preflight receipt, a bootstrap-only installer,
an install receipt, a read-only observer and a first-natural-opportunity start
receipt. Existing secure publication, event-log and v0.76 runtime primitives
remain authoritative; no generic deployment or scheduler layer was added.

The renderer creates the trusted runtime/snapshot/event directory structure.
Preflight therefore requires those exact contract-bound directories to exist,
while the target plist, service and stdout/stderr files must remain absent.
Installation selects exactly one currently valid preflight; later replay uses
the immutable preflight binding stored in the install receipt.

The target `/usr/bin/python3 -s` resolves the six exact versions frozen in
`requirements.lock` only from release-bound wheels and extracted arm64 `rpds`
native files inside the immutable snapshot. Complete wheel/native bytes are
part of the snapshot inventory; `PYTHONNOUSERSITE=1` excludes mutable user-site
code and the Python identity check rejects distribution-version drift.

System Paper is non-blocking. Its independent 90-day evidence stream may start
later and cannot delay the replacement 72-hour operational qualification.
There is no v0.79 activation-code split: after this release the remaining
activation work is one separately authorized, no-credential external ceremony
and a wait for the next natural four-hour opportunity.

## Authority boundary

The code release performs no renderer, preflight network call, installation,
bootstrap, runtime invocation or start-receipt publication. It contains no
private Binance module and grants no account, Broker, order or funding
authority. A future ceremony must preserve failures and may never kickstart,
backfill or synthesize a natural opportunity.
