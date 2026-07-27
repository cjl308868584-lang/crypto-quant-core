# Context-Complete Paper Cycle Design

## Goal

Create a crash-recoverable 4h sidecar cycle that freezes the exact
Paper/account-cost binding and contemporaneous perpetual context belonging to
one existing Paper scheduler slot.

The legacy Paper run remains immutable. A legacy `SUCCEEDED` slot is not
silently upgraded: only a separately prepared and published context bundle is
`CONTEXT_COMPLETE`.

## Why a sidecar state

v0.19/v0.20 already freeze the Paper scheduler event chain and PREPARED blob
shape. Mutating that state or its v1 Artifact would invalidate the evidence that
crash recovery publishes the exact originally prepared run bytes.

v0.24 therefore uses a new append-only SQLite WAL:

- `CONTEXT_CLAIMED`;
- `CONTEXT_PREPARED`;
- `CONTEXT_SUCCEEDED`;
- `CONTEXT_FAILED`.

Its PREPARED blob contains the complete context-bundle bytes, SHA-256, bundle
hash, bundle trust hash, all source trust hashes and output-root binding. Update
and delete triggers make events and blobs immutable.

## Context bundle inputs

1. a replay-verified `paper-account-cost-binding-v1`;
2. its external binding attestation;
3. the two independently retained source attestations required by that
   binding;
4. a replay-verified `perpetual-context-snapshot-v1`;
5. its external attestation;
6. a UTC creation time.

The Paper run embedded in the cost binding must be the exact scheduled run for
the inferred `ETHUSDT_YYYYMMDDTHH0000Z` slot.

## Time and role boundary

- Paper decision must occur from slot `due_at` through `expires_at`.
- Perpetual source time and recorded time must fall in the same active slot.
- Perpetual source time must be within 15 minutes of the Paper decision.
- Bundle creation must follow both sources and remain before slot expiry.

The current baseline signal does not consume perpetual fields. A source at or
before decision is `PRE_DECISION_AVAILABLE_NOT_CONSUMED`; a source after
decision is `POST_DECISION_OBSERVATIONAL_NOT_SIGNAL`. Neither role permits
rewriting the already frozen decision.

## Bundle outputs

The bundle embeds both complete sources and freezes:

- schedule policy and exact slot;
- source hashes and trust lineage;
- PIT relationship;
- Spot account-costed liquidation change;
- Mark/Index basis, OI change and Funding scenarios;
- explicit `funding_realized=false`;
- explicit `perpetual_used_in_signal=false`;
- self-hash and external bundle attestation;
- research-only, not-production, insufficient-duration eligibility.

Semantic validation rebuilds the bundle from embedded sources.

## Runner and recovery

The runner performs no network request. On a new claim it builds and atomically
prepares exact bundle bytes before publishing. Faults after prepare or after
publish are recoverable:

- a later worker reclaims only after the lease expires;
- it loads and validates the PREPARED blob;
- it makes zero source reads and zero network requests;
- it publishes/adopts the exact bytes;
- a different output root is rejected.

Missing context, an invalid source, slot mismatch or PIT failure records
`CONTEXT_FAILED`; it cannot create a context-complete Artifact.

## Non-goals

v0.24 does not configure an OS scheduler, capture a real account snapshot,
repair the unavailable Futures network, enable SHORT, insert Funding into
realized PnL, run AI, submit an order or claim 90-day profitability.
