# ADR 0085: v0.78.7 partial-install recovery protocol

## Decision

Release v0.78.7 as a recovery-only trust-chain increment. It binds the exact
v0.78.5 failed install receipt, preflight receipt, target plist, candidate,
contract, snapshot, empty event/start/log roots, disabled and unloaded service
state, and paused automation to the exact v0.78.6 public release foundation.
Qualification publishes one strict, self-hashed recovery receipt. The new
v0.78.7 installer must replay that receipt and re-observe the same identities
before it can reach its existing target-absent gate.

The new candidate uses a release-scoped target plist. Historical v0.78.5 files
and receipts must not be deleted, overwritten, moved, renamed, chmodded or
repaired. Same bytes on a different inode, time drift, extra links, unexpected
directory entries, loaded services or an unpaused automation fail closed.

## Authority boundary

This release does not authorize installation or start. It does not run the
renderer, recovery qualification, preflight, bootstrap-only installer, natural
opportunity, or observer/start receipt ceremony. It does not authorize
credentials, private account access, Broker calls, orders, cancels or funds.

The separately authorized later sequence is exactly: renderer, recovery
qualification, preflight, bootstrap-only installer, natural opportunity, then
observer/start receipt. There is no kickstart, enable, direct runtime invocation
or historical-evidence mutation in that sequence.

## Consequences

- A fresh release-scoped target avoids overwriting the partial v0.78.5 target.
- Recovery qualification is read-only except for publishing its own immutable
  receipt inside its exact release-scoped receipt root.
- A crash or repeat before receipt publication can only replay exact evidence;
  conflicting or orphan publication state is rejected.
- Operational and economic timers remain unstarted until a later natural
  opportunity and strict start receipt exist.
