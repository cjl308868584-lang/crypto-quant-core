# ADR 0083: v0.78.5 activation candidate supersession

## Decision

Release `v0.78.5` with release-scoped replacement-v3 activation candidates.
The contract, candidate plist, preflight-receipt directory and install-receipt
directory use the exact `v0.78.5` suffix. Content-addressed snapshots, event
root, target plist path, service identity and natural schedule remain shared.

## Evidence and reason

The observed v0.78.4 renderer conflict was
`CHALLENGER_REPLACEMENT_INSTALL_CONTRACT_CONFLICT`: its fixed candidate path
collided with the immutable v0.78.3 candidate files bound by the failed
preflight receipt. That v0.78.3 evidence must not be deleted, overwritten,
moved, renamed or chmodded. Supersession creates distinct v0.78.5 paths; it is
not evidence migration and it does not reinterpret old receipts as current
inputs.

## Safety boundary

- `production_activation=false`
- no replacement service installed or started
- no credential created or read
- no private Binance request made
- no order submitted
- no funds moved

This code release does not run renderer, preflight, installer, bootstrap,
LaunchAgent, observer or runtime. A separately authorized ceremony must bind
the exact annotated v0.78.5 release and preserve all historical evidence.
