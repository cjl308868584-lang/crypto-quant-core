# Implementation Status v0.78.6

Status: `INSTALL_RECEIPT_TIME_HOTFIX_RELEASED_NOT_RECOVERED`

## Delivered

The replacement-v3 activation install receipt now truncates only
`installed_at` to canonical UTC whole seconds (`.000Z`) before computing its
business ID and self-hash. Schema validation, deterministic reconstruction and
strict loader replay use the same bytes. Tests cover a real-shaped `.101Z`
input and the current partial-install failure boundary.

Package v0.78.6 and manifest v1.78.0 bind a new release-scoped activation
candidate. This release does not execute that candidate.

## Preserved partial state

- the replacement service remains disabled and unloaded;
- the automatic task remains paused;
- the existing target plist remains present;
- the v0.78.5 install and preflight receipts remain byte-exact;
- the snapshot, event root and log directories remain in place;
- event and log evidence remains empty;
- no 04:02 natural opportunity is started.

All v0.78.5 evidence must not be deleted, overwritten, modified or repaired.
Because the target plist already exists while the historical install receipt
cannot strictly replay, the normal installer correctly fails closed.

## Remaining gate

Installation recovery requires a separately approved recovery protocol that
binds the preserved v0.78.5 evidence, proves the service disabled/unloaded,
compares the existing target plist with the v0.78.6 candidate, and performs no
replacement unless an exact atomic and rollback-safe transition is frozen.

No renderer, preflight, installer, enable, bootstrap, kickstart, start, runtime,
credential, private account, Broker, order, cancel or fund movement action is
authorized by this release.
