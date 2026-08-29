# ADR 0081: v0.78.3 filesystem identity hotfix

## Decision

Release a bounded `v0.78.3` patch that represents every filesystem `device`
and `inode` carried by the replacement v3 activation install contract as a
strict unsigned decimal string. Device permits canonical `"0"`; inode starts
at `"1"`; neither permits a sign, whitespace or a leading zero. The loader
also rejects values above the unsigned 64-bit range.

At an OS boundary, the strict string is decoded to an integer solely for exact
comparison with `stat` or for constructing the existing retained event-root
capability. No identity is truncated, converted through floating point,
ignored or weakened. The global canonical JSON safe-integer rule remains
unchanged.

## Reason

The exact v0.78.2 renderer created its owner-only directories and immutable
snapshot, then failed before publishing its contract or plist. The target
Mac's `/usr/bin/python3` inode was `1152921500312522874`, which is a valid
filesystem identity but exceeds the canonical JSON exact-integer limit
`2^53-1`. Unit fixtures had used only small inode values.

The patch covers snapshot `root_device/root_inode`, event-root `device/inode`,
Python `device/inode`, plist publication identity, canonical event headers and
the start-receipt event-root binding. All loaders restore integers only for
exact OS/capability comparisons. Existing v0.78.2 runtime/snapshot evidence
remains untouched.

## Safety boundary

- `production_activation=false`
- no service installed or started
- no credential created or read
- no private Binance request made
- no order submitted
- no funds moved

This release does not execute renderer, preflight, installer, LaunchAgent or
start-receipt ceremony. Those remain separately authorized post-release
actions against the exact annotated v0.78.3 identity.
