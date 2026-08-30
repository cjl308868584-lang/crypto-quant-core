# Implementation Status v0.78.7

Status: `PARTIAL_INSTALL_RECOVERY_CODE_RELEASED_NOT_EXECUTED`

## Delivered

v0.78.7 freezes and implements a minimal partial-install recovery protocol. A
closed canonical plan binds the exact v0.78.5 incident evidence and the exact
v0.78.6 release identity. The read-only verifier checks bytes, SHA-256, device,
inode, owner, mode, link count, size, mtime and ctime, full snapshot identity,
empty state/event/start/log roots, both services disabled and unloaded, paused
automation, and absence of the new release-scoped target.

The recovery receipt has deterministic business identity, self-hash and strict
replay. Its publisher is no-overwrite and repeat-safe. The v0.78.7 install
contract and install receipt bind that exact recovery receipt and require fresh
revalidation before any installation command can be reached.

## Preserved history

All v0.78.5 target, contract, candidate, preflight/install receipts, snapshot,
event root and log roots must not be deleted, overwritten, renamed, moved,
chmodded or repaired. The replacement and predecessor Challenger services must
remain disabled and unloaded, and the automation must remain paused throughout
this code release.

## Not executed

This release does not authorize installation or start. It does not run
renderer, recovery qualification, preflight, bootstrap-only installer, wait for
a natural opportunity, or publish an observer/start receipt. Credentials,
private account requests, Broker calls, orders, cancels and funds remain zero.

The only later ceremony order is: renderer, recovery qualification, preflight,
bootstrap-only installer, natural opportunity, observer/start receipt. That
ceremony requires separate explicit authorization after exact v0.78.7 release
identity and preserved evidence are rechecked.
