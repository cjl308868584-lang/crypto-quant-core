# ADR 0084: v0.78.6 install receipt time hotfix

## Decision

Release v0.78.6 with one behavioral correction: replacement-v3 activation
install receipts encode `installed_at` as canonical UTC whole seconds ending in
`.000Z`, matching their existing schema and strict replay contract. The global
datetime encoder and unrelated receipts are unchanged.

The release uses v0.78.6-scoped contract, candidate plist, preflight receipt and
install receipt paths. It does not authorize renderer, preflight, installation,
LaunchAgent mutation, runtime execution or trading activity.

## Existing partial installation

The v0.78.5 target plist and its install/preflight receipts, snapshot, event
root and log directories are historical evidence and must not be deleted,
overwritten, renamed, moved, chmodded or repaired. The replacement service is
disabled and unloaded; the event and log roots are empty. The v0.78.5 install
receipt contains a nonzero millisecond and cannot pass its own strict schema.

Existing-target detection remains fail closed. v0.78.6 deliberately does not
adopt, overwrite or replace the target plist. A separate reviewed recovery protocol
is required before any later installation attempt.

## Consequences

- Receipt schema, self-hash, business ID, deterministic rebuild and strict
  replay agree for nonzero-millisecond input times.
- `first_eligible_scheduled_for` already used whole-second boundary arithmetic;
  no other time field in this receipt needs correction.
- The automatic task remains paused and no 04:02 natural execution is possible.
- No credential, private account, Broker, order or funds authority is added.
