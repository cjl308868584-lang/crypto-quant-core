# v0.60 Tail-Blind Operations Projection Design

## 1. Status and authority

This document freezes the v0.60.0 design for the read-only, tail-blind
operations projection. Its Git base is the released `v0.59.0` identity:

- private repository: `cjl308868584-lang/crypto-quant-core`;
- `origin/main`: `3a4283bc06099f821ca72947535748d3e3760180`;
- annotated tag: `v0.59.0`;
- peeled tag commit: `3a4283bc06099f821ca72947535748d3e3760180`.

The release is code and contract work only. System Paper remains
`PLAN_FROZEN_PAPER_NOT_STARTED`; installation, service activation, a start
receipt, runtime evidence, and a 90-day result do not exist.

## 2. Goal

Build one deterministic, canonical, read-only projection that exposes only the
operational facts needed by a later local dashboard. The projection must make
stale or unhealthy evidence obvious while preventing confirmatory Challenger
economics and arbitrary source fields from crossing the observation boundary.

The public entry point is:

```python
build_operations_projection(
    now: str,
    sources: OperationsProjectionSources,
) -> Mapping[str, Any]
```

The strict replay entry point is:

```python
load_operations_projection_bytes(body: bytes) -> Mapping[str, Any]
```

Both functions are pure with respect to the filesystem and network.

## 3. Approaches considered

### 3.1 Selected: typed source snapshots and field-by-field assembly

Each injected adapter returns one frozen, slotted dataclass. The projector
validates the dataclass, calls each adapter exactly once, and constructs every
output field explicitly. Source mappings are never serialized or merged.

This costs more explicit code when a field is added, but it provides the
strongest boundary against accidental PnL, path, credential, or internal-state
leakage. It also makes each source failure and Schema change reviewable.

### 3.2 Rejected: generic mappings plus a recursive allowlist filter

This is shorter but unsafe. Nested source additions can be mishandled by a
filter, key aliases can bypass substring checks, and accepted types remain
ambiguous. A generic filter would turn future source growth into an implicit
public interface.

### 3.3 Rejected: concatenate existing receipt and evaluation artifacts

This retains provenance but couples the dashboard model to multiple large
artifact Schemas, exposes internal paths and economics, and makes missing
sources hard to distinguish from valid not-started states. It is also harder to
keep tail-blind.

## 4. Scope

v0.60.0 includes:

- `operations_projection.py` with typed source snapshots, the projector, and a
  strict canonical-bytes loader;
- one mirrored `operations-projection-v1` JSON Schema;
- deterministic source freshness and overall health rules;
- pre-tail redaction, provenance, Schema, self-hash, and loader tests;
- package/build-manifest/release documentation for v0.60.0.

It does not include:

- a Web server, HTML, JavaScript, HTTP routes, alerts engine, or runbooks;
- filesystem discovery, SQLite access, `launchctl`, subprocesses, or network;
- persistence or publication of a projection artifact;
- System Paper installation, start, Runner, scheduler, or maintenance;
- replacement Challenger design or execution;
- PnL, return, win rate, drawdown values, equity, fees, prices, confidence,
  ranking, intervals, power, or early PASS evidence;
- any operation that can mutate strategy, risk, Broker, order, credential,
  balance, runtime, or evidence state.

The loopback Web, alerts, and runbooks remain v0.61.0 work. Replacement
Challenger remains a separate design with new service, state, log, bundle, and
evidence roots and a permanent binding to the failed legacy cohort.

## 5. Architecture

```text
frozen production loaders
          |
          v
injected zero-argument adapters
          |
          v
frozen typed source snapshots
          |
          v
field-by-field projector ----> canonical projection mapping
                                      |
                                      v
                           strict canonical-bytes loader
                                      |
                                      v
                           future loopback-only Web (v0.61)
```

The projector does not import operational loader modules. A later composition
layer may call production loaders and translate their verified results into the
typed source snapshots. This prevents importing a projection module from
opening a file, invoking a process, or contacting a service.

## 6. Typed source boundary

All dataclasses are `frozen=True, slots=True`. All fields are required; callers
cannot attach arbitrary mappings.

### 6.1 `SourceProvenance`

```python
SourceProvenance(
    source_kind: str,
    source_sha256: str,
    observed_at: str,
)
```

`source_kind` is one of `RELEASE_IDENTITY`, `CHALLENGER_OPERATIONS`, or
`SYSTEM_PAPER_OPERATIONS`. `source_sha256` is exactly 64 lowercase hexadecimal
characters and identifies the canonical verified adapter result. `observed_at`
is canonical UTC with millisecond precision.

### 6.2 `ReleaseOperationsSource`

Required fields:

- `package_version`;
- `main_commit`;
- `release_tag`;
- `tag_commit`;
- `identity_status`, fixed to `VERIFIED` for a buildable projection;
- `provenance`.

`main_commit` and `tag_commit` must be the same 40-character lowercase Git
object id. `release_tag` must equal `v` plus `package_version`.

### 6.3 `ChallengerOperationsSource`

Required fields:

- `phase`: `LEGACY_FAILED_REPLACEMENT_NOT_STARTED`,
  `REPLACEMENT_NOT_STARTED`, `COLLECTING`, or `FINAL`;
- `service_health`: `NOT_LOADED`, `HEALTHY`, `DEGRADED`, or `FAILED_CLOSED`;
- `evidence_health`: `VERIFIED`, `STALE`, `INCIDENT_DETECTED`,
  `FAILED_CLOSED`, or `NOT_AVAILABLE`;
- `verified_slot_count` and `completed_episode_count`, non-negative integers;
- `active_episode_present`, a boolean;
- `next_required_slot`, canonical UTC or `None`;
- `gate_status`: `NOT_AVAILABLE`, `WITHHELD_PRE_TAIL`,
  `RESEARCH_CONTINUATION_GATE_PASS`,
  `RESEARCH_CONTINUATION_GATE_DID_NOT_PASS`, or
  `INCONCLUSIVE_INSUFFICIENT_EVIDENCE`;
- `incident_count`, a non-negative integer;
- `provenance`.

For `COLLECTING`, `gate_status` must be `WITHHELD_PRE_TAIL`. The projector never
accepts an economic metric, even after `FINAL`; only the immutable gate status
may cross the boundary. A legacy cohort failure is an operational continuity
fact and must not be interpreted as a profitability result.

### 6.4 `SystemPaperOperationsSource`

Required fields:

- `phase`: `NOT_INSTALLED`, `INSTALLED_NOT_STARTED`, `COLLECTING`, or `FINAL`;
- `service_health`: `NOT_LOADED`, `HEALTHY`, `DEGRADED`, or `FAILED_CLOSED`;
- `evidence_health`: `VERIFIED`, `STALE`, `INCIDENT_DETECTED`,
  `FAILED_CLOSED`, or `NOT_AVAILABLE`;
- `elapsed_days`, `verified_slot_count`, and `incident_count`, non-negative
  integers;
- `next_required_slot`, canonical UTC or `None`;
- simulated lifecycle counts: `submitted_order_count`, `filled_order_count`,
  `partially_filled_order_count`, `cancelled_order_count`,
  `rejected_order_count`, and `timeout_unknown_order_count`;
- `reconciliation_status`: `NOT_AVAILABLE`, `RECONCILED`, or
  `FAILED_CLOSED`;
- `risk_state`: `NOT_AVAILABLE`, `NORMAL`, `WARNING`, `REDUCE`, `HALT`, or
  `HARD_BOUNDARY`;
- `gate_status`: `NOT_EVALUATED`, `SYSTEM_PAPER_GATE_PASS`,
  `SYSTEM_PAPER_GATE_DID_NOT_PASS`, or
  `INCONCLUSIVE_INSUFFICIENT_EVIDENCE`;
- `provenance`.

`NOT_INSTALLED` requires zero counts, `NOT_AVAILABLE` reconciliation and risk,
`NOT_EVALUATED` gate status, and `next_required_slot=None`. `COLLECTING`
requires `NOT_EVALUATED`; only `FINAL` may expose a terminal gate status.
Lifecycle counts are explicitly simulated and do not imply exchange orders.

### 6.5 `OperationsProjectionSources`

```python
OperationsProjectionSources(
    release_loader: Callable[[], ReleaseOperationsSource],
    challenger_loader: Callable[[], ChallengerOperationsSource],
    system_paper_loader: Callable[[], SystemPaperOperationsSource],
)
```

The projector calls the three loaders in the fixed order above, exactly once
each. A loader exception, wrong return type, invalid dataclass, or release
identity mismatch raises `OperationsProjectionError` with a bounded reason
code. No partial projection is returned.

## 7. Projection contract

The top-level mapping has exactly these fields:

```text
$schema
schema_version
projected_at
status
release
challenger
system_paper
projection_hash
```

`status` is derived, never supplied:

- `FAILED_CLOSED` if either operational source has `FAILED_CLOSED` service or
  evidence health, or System Paper reconciliation is `FAILED_CLOSED`;
- `DEGRADED` if no failed-closed condition exists and either source is stale,
  degraded, incident-bearing, or at `HALT`/`HARD_BOUNDARY` risk;
- `HEALTHY` otherwise, including the legitimate not-started state.

Each of `release`, `challenger`, and `system_paper` contains a `provenance`
object with `source_kind`, `source_sha256`, `observed_at`, and derived
`freshness`. This provenance applies to every displayed value in that section.
No source path is exposed.

`projection_hash` is the repository `business_hash` of the complete mapping
without `projection_hash`, using purpose
`TAIL_BLIND_OPERATIONS_PROJECTION_V1`.

## 8. Time and freshness

`now` and every `observed_at` must be canonical UTC timestamps with millisecond
precision. Binary floats, local timestamps, offsets other than `Z`, leap-second
text, and non-canonical equivalents are rejected.

An operational source is:

- `FRESH` when `0 <= now - observed_at <= 20 minutes`;
- `STALE` when it is older than 20 minutes;
- invalid when it is more than 5 minutes in the future.

Release provenance is identity evidence rather than liveness evidence and is
always projected as `IDENTITY_VERIFIED` after its commit/tag invariant passes.
The 20-minute window intentionally covers the daily 08:10 maintenance to 08:25
coordination interval while still making missed observation obvious.

## 9. Tail-blind policy

Before Challenger `FINAL`, the only gate value is `WITHHELD_PRE_TAIL`. At all
phases, the Challenger output and canonical encoded bytes must not contain any
case-insensitive occurrence of:

```text
pnl, profit, return, win_rate, drawdown, equity, price, fee,
confidence, ranking, interval, power
```

The policy is structural, not merely a post-serialization string replacement:
none of these concepts exists in the source dataclass or Schema. Tests also
seed hostile adapter objects and verify that arbitrary attributes and mappings
cannot cross the boundary.

System Paper exposes operational counts, reconciliation state, risk state, and
the final gate only. It never exposes the economic measurements behind the
gate.

## 10. Strict loader and Schema

`load_operations_projection_bytes`:

1. bounds input before decoding;
2. requires UTF-8 canonical JSON with no duplicate keys, binary floats,
   non-finite values, or unknown fields;
3. validates the packaged JSON Schema;
4. recomputes and verifies `projection_hash`;
5. returns a newly decoded mapping without filesystem, subprocess, or network
   access.

`config/operations-projection-v1.schema.json` and
`src/crypto_quant/schemas/operations-projection-v1.schema.json` must be exact
byte mirrors. Both set `additionalProperties=false` at every object boundary.

## 11. Errors

All public failures use `OperationsProjectionError` and one of these bounded
reason codes:

- `OPERATIONS_PROJECTION_TIME_INVALID`;
- `OPERATIONS_PROJECTION_SOURCES_INVALID`;
- `OPERATIONS_PROJECTION_SOURCE_LOAD_FAILED`;
- `OPERATIONS_PROJECTION_SOURCE_INVALID`;
- `OPERATIONS_PROJECTION_RELEASE_IDENTITY_MISMATCH`;
- `OPERATIONS_PROJECTION_FUTURE_SOURCE`;
- `OPERATIONS_PROJECTION_SCHEMA_INVALID`;
- `OPERATIONS_PROJECTION_BYTES_INVALID`;
- `OPERATIONS_PROJECTION_HASH_MISMATCH`.

Exceptions do not include source mappings, paths, economic values, or arbitrary
adapter exception text.

## 12. Testing

Focused tests must prove:

- all three loaders are called once in fixed order;
- wrong types, loader exceptions, duplicate keys, floats, unknown fields,
  oversized bytes, and hash changes fail closed;
- release main/tag/package identity is exact;
- fresh, stale, future, degraded, incident, failed-closed, and risk-boundary
  states derive the correct overall status;
- legacy-failed/replacement-not-started, replacement collecting, and final
  Challenger states are valid without economics;
- not-installed, installed-not-started, collecting, and final System Paper
  states are valid;
- pre-tail and final projections contain none of the forbidden economic terms;
- hostile extra source attributes and nested mappings never appear;
- mirrored Schema bytes are exact;
- canonical projection bytes and `projection_hash` are deterministic;
- source objects and output mappings are not mutated;
- import and execution perform zero filesystem, subprocess, launchctl, network,
  credential, Broker, order, or state-write operations.

Adjacent tests cover canonical hashing, packaged Schema loading, v0.59 System
Paper evaluator outputs, and Challenger final status enums. The final code state
receives one local full test run, one complete independent review, targeted
re-review only for changed findings, PR Python 3.9/3.12 CI, one main CI, and an
annotated tag identity check. The same commit is not given a duplicate local
full run, and an unchanged branch is not re-reviewed.

## 13. Release and safety gates

The v0.60 release updates package version, build inputs, manifest, README,
implementation status, and an ADR. It does not install or start anything.

Release is blocked by any Critical or Important review finding, test or CI
failure, Schema mirror mismatch, manifest mismatch, Git identity mismatch,
unexpected runtime/plist/service presence, or any path that could expose
economics or write operational state.

Even a healthy projection means only that the allowlisted observation is
internally consistent. It is not proof of profitability, AI advantage, Paper
completion, Canary eligibility, or live-trading readiness.
