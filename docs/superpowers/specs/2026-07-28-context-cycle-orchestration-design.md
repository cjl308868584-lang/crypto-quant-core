# Context-Complete Cycle Orchestration Design

## Goal

Turn the separately verified v0.19–v0.24 components into one recoverable,
one-shot 4h orchestration path:

1. verify a read-only account signer before any network request;
2. open one three-sample Binance server-time gate;
3. capture current account commission before the Paper decision;
4. execute or recover the scheduled Paper cycle;
5. capture perpetual context after the Paper decision;
6. build the account-cost binding;
7. prepare and publish the context-complete sidecar.

The normal path shares one probe and one monotonic trusted clock across all
network stages. It makes exactly 15 requests: 3 time, 3 account, 4 Paper and
5 perpetual. It never reads balances and never submits an order.

## Why a new orchestration state is required

The account snapshot must be observed no later than the Paper decision. A
naive shell pipeline can crash after Paper succeeds and then recapture account
commission after the decision, making the slot permanently PIT-invalid.

v0.25 therefore adds a separate append-only SQLite WAL. It freezes exact
source bytes and trust hashes at stage boundaries:

- `ORCHESTRATION_CLAIMED`;
- `ACCOUNT_PREPARED`;
- `PAPER_REFERENCED`;
- `PERPETUAL_PREPARED`;
- `COST_BINDING_PREPARED`;
- `CONTEXT_SUCCEEDED`;
- `ORCHESTRATION_FAILED`.

Source blobs and events reject update/delete. Every open replays the event
chain, payload hashes, source-byte hashes and legal state transitions.

## Claim, lease and retry semantics

The orchestration uses the same 4h slot policy and a 15-minute lease:

- a completed slot returns `ALREADY_SUCCEEDED` after the three-request clock
  gate, with zero account/Paper/perpetual requests;
- an unexpired claim returns `BUSY`;
- a failed or expired claim can be reclaimed while the slot is active;
- a prepared account source is always reused and never recaptured;
- a referenced Paper run is always reused through the existing Paper
  scheduler;
- prepared perpetual and binding bytes are republished/adopted exactly;
- no slot is backfilled after expiry.

Every retry opens a fresh verified server-time gate before making new network
requests. Therefore a crash-recovery invocation may use a different probe for
unfinished stages. The final orchestration snapshot records all gate hashes
and whether the entire successful path used one shared gate. This is explicit
recovery lineage, not a false same-process claim.

## Shared runtime gate

`VerifiedRuntimeGate` is issued only after:

- exactly three server-time responses;
- a replay-valid probe;
- `HEALTHY_ALIGNED` or `HEALTHY_CORRECTED`;
- construction of one monotonic `TrustedRuntimeClock`.

Account and perpetual capture gain internal shared-gate entry points. Their
standalone APIs retain their existing 6/8-request evidence contracts. The
orchestrator separately reports physical request counts and deduplicates the
shared three-request probe.

## Publication and trust

The orchestration snapshot includes:

- policy and exact slot;
- append-only event chain and source-blob inventory;
- every runtime probe hash;
- account, Paper, perpetual, binding and context trust hashes;
- stage outcomes and physical network counts;
- shared-gate and recovery facts;
- state integrity, self-hash and external attestation hash.

All state, snapshots, generated scheduler files and sensitive source artifacts
use owner-only mode `0600`.

## Local scheduling

v0.25 renders, validates and atomically publishes a macOS LaunchAgent plist:

- fixed UTC-equivalent 4h cadence at minute 6;
- `RunAtLoad=true` for in-window recovery;
- fixed module entry point and explicit state/output paths;
- credential **file paths** only, never credential values;
- stdout/stderr below the selected runtime root;
- no shell, URL, proxy, order or arbitrary command injection;
- no automatic `launchctl` installation.

The generated plist is deployable evidence, but the repository must not claim
that an operating-system scheduler is active until an external installation
receipt proves it.

## Failure boundary

- Missing/unsafe credential files fail before all network access.
- A blocked clock makes only the three allowed time requests.
- Account permission failure prevents Paper and perpetual requests.
- Paper failure prevents perpetual and context completion.
- Perpetual failure preserves the pre-decision account and Paper evidence for
  an in-slot retry.
- Any invalid trust hash, source byte, slot relation or state transition fails
  closed.

## Non-goals

v0.25 does not install a LaunchAgent, create credentials, read balances,
submit orders, run AI, include Funding in realized PnL, wait 90 days, or claim
profitability.
