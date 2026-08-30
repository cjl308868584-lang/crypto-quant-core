# v0.78.5 activation candidate supersession design

## Problem

The exact v0.78.4 renderer created its content-addressed snapshot and then
failed closed with `CHALLENGER_REPLACEMENT_INSTALL_CONTRACT_CONFLICT`.
The fixed deployment directory already contains the immutable v0.78.3
candidate plist and install contract that are bound by the preserved failed
preflight receipt.  Reusing one canonical filename for every release makes a
safe retry impossible: overwriting or moving the v0.78.3 files would break
historical replay, while leaving them in place prevents the next release from
publishing.

This is a pre-install defect.  The replacement target plist is absent, both
replacement and predecessor services are unloaded, and the replacement event,
install-receipt and start-receipt counts are zero.  The v0.78.3 failed receipt
and its referenced candidate bytes remain authoritative historical evidence.

## Decision

Activation candidates become release scoped.  `activation_paths()` derives a
strict release suffix from the frozen release tag and uses these paths:

- contract: `deployment/challenger-replacement-v3-install-contract-v0.78.5.json`
- candidate plist: `deployment/local.crypto-quant.challenger-replacement-v1-v0.78.5.plist`
- preflight receipts: `deployment/preflight-receipts-v0.78.5/`
- install receipts: `deployment/install-receipts-v0.78.5/`

The content-addressed `deployment/snapshots/` directory remains shared because
snapshot names are their full tree hashes.  The event root, log paths,
start-receipt root, service label, target LaunchAgent plist path and six natural
four-hour opportunities remain unchanged.

The renderer creates the two release-scoped receipt directories through the
existing retained-directory, owner-only primitives.  Candidate plist and
contract publication continues to use exact no-overwrite publication.  An
existing exact v0.78.5 candidate is replayed; different or untrusted bytes fail
closed.  No old file is moved, renamed, chmodded, removed or overwritten.

The old v0.78.3 code can still strictly replay its fixed-path failed receipt.
The v0.78.5 loaders only read v0.78.5 paths, so old receipts cannot become
ambiguous current install inputs.  This is path supersession, not evidence
migration.

## Failure and authority boundaries

- Release tags must match `^v[0-9]+\.[0-9]+\.[0-9]+$`; invalid tags fail before
  production-root writes.
- Existing symlink, hardlink, wrong-mode, non-directory or conflicting entries
  at any new release-scoped path fail closed through existing secure primitives.
- A failed renderer may leave a complete content-addressed snapshot, which is
  non-authoritative until an exact contract binds it.  Partial or conflicting
  canonical candidate files never authorize preflight or installation.
- `production_activation=false`; no credentials, account requests, Broker,
  orders or funds are introduced.
- The patch does not install, bootstrap, start, kickstart or invoke runtime.

## Verification

Tests must reproduce the v0.78.4 failure with trusted v0.78.3 files at the old
paths, then prove v0.78.5 renders and strictly replays without changing their
bytes, modes, inode identities, link counts or timestamps.  Tests also cover
exact rerender, current-path conflict, untrusted release-scoped directories,
old receipt isolation, and unchanged target/service/event authority.

The release candidate receives one focused test run, one full local suite,
`compileall`, `make validate`, diff checks, an independent review, public PR
CI, merged-main CI and annotated tag identity verification.  Only after that
release may a new external ceremony run renderer, preflight, bootstrap-only
installer and wait for a natural opportunity.
