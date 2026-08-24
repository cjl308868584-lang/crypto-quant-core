# Replacement v3 Readiness Evaluator, Observer and Operations Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fixture-qualified operational-readiness policy evaluator, a tail-blind economic-progress observer, and strict operations-projection-v2 integration with the existing loopback-only read-only console without installing, starting or authorizing any trading runtime.

**Architecture:** Reduce strict v0.70/v0.72 opportunity and lifecycle evidence into small frozen fact types, evaluate operational policy and economic tail visibility as pure functions, then compose those results through a read-only observer and a separate v2 operations projection. Preserve operations-projection-v1 byte behavior and reuse the v0.61 HTTP/static console through exact schema dispatch rather than creating another UI.

**Tech Stack:** Python 3.9-compatible standard library, frozen dataclasses, existing canonical JSON/hash/event-root loaders, JSON Schema Draft 2020-12, `unittest`, package-resource static HTML/CSS/JavaScript.

**Spec:** `docs/superpowers/specs/2026-08-25-replacement-v3-readiness-observer-design.md`

## Global Constraints

- Release base is annotated `v0.72.0`, peeled commit `44d294a8fbc55a0fb4f9fe0537bb868824815d80`.
- Exact release claim is `READINESS_EVALUATOR_AND_READ_ONLY_INTEGRATION_VERIFIED_NOT_STARTED`.
- Do not modify committed v0.69-v0.72 artifacts, schemas or fixture bytes, operations-projection-v1 schema, or the v0.61 HTTP route contract.
- No installation, start receipt, production event-root write, market/account request, credential, Broker, venue order, fund movement, Canary authority or wall-clock timer starts in v0.73.
- The 7-day operational policy is implemented exactly; no final 90-day economic status or result is implemented until numerical economic thresholds are separately preregistered.
- The v0.72 strict loader may parse the complete canonical result for schema/hash/identity validation; after the reviewed sanitizer boundary, pre-tail readiness/UI code must not semantically read, branch on, aggregate, serialize or display PnL, return, fee, funding, win rate, drawdown amount, confidence interval, rank, power or early PASS.
- Public production APIs accept typed strict-loader results, not arbitrary paths, times, policies, statuses, PnL values, mappings or callbacks.
- All new JSON is canonical, duplicate-key rejecting, float-free, safe-integer bounded, self-hashed and strict-schema loaded.
- New projection Schema mirrors under `config/` and `src/crypto_quant/schemas/` are byte-identical.
- Every production module is at most 700 physical lines; no generic evaluator, storage, dashboard or Broker framework is added.
- Use exact RED then minimal GREEN for every task; one final full suite only after the final code state.

## File Structure

- `src/crypto_quant/challenger_replacement_readiness.py`: frozen fact/result types, cycle reduction, operational policy and tail-blind economic progress.
- `src/crypto_quant/challenger_replacement_readiness_observer.py`: one-pass read-only conversion from strict event projection to readiness facts and fixture-qualified observation.
- `src/crypto_quant/operations_projection_v2.py`: typed v2 projection builder, strict loader and self-hash validation.
- `src/crypto_quant/operations_alerts.py`: exact v1/v2 dispatch and allowlisted v2 alerts/status response.
- `src/crypto_quant/operations_dashboard.py`: unchanged HTTP semantics; only accepts status bytes produced by strict alert dispatch.
- `src/crypto_quant/dashboard/{index.html,app.js,styles.css}`: existing console labels and read-only rendering for the v2 replacement fields.
- `config/operations-projection-v2.schema.json` and package mirror: exact v2 schema.
- `tests/test_challenger_replacement_readiness.py`: policy, coverage, cycles, safety precedence and tail blindness.
- `tests/test_challenger_replacement_readiness_observer.py`: strict replay conversion, fixed qualification, no-write/error behavior.
- `tests/test_operations_projection_v2.py`: schema, hash, typed-source and semantic validation.
- Existing operations tests: v1 compatibility, alert order, HTTP and DOM security.

---

### Task 1: Freeze Readiness Facts and Exact Coverage Semantics

**Files:**
- Create: `src/crypto_quant/challenger_replacement_readiness.py`
- Create: `tests/test_challenger_replacement_readiness.py`

**Interfaces:**
- Produces: `OpportunityReadinessFact`, `ReplacementReadinessFacts`, `OperationalReadinessResult`; `_ReplacementReadinessBoundary` remains private and fixture-qualified. `EconomicTailObservation` is introduced by Task 3.
- Produces: `evaluate_challenger_replacement_operational_readiness(facts, boundary) -> OperationalReadinessResult`.
- Consumes: canonical UTC helper and fixed v0.69 policy constants only; no event-root or filesystem API.

- [x] **Step 1: Add RED tests for exact types, time and coverage**

Add tests that construct frozen facts explicitly and prove bool/int substitution,
noncanonical timestamps, negative counts, count inconsistencies, duplicate or
out-of-order opportunity IDs and arbitrary mappings are rejected before a
result is returned:

```python
def test_operational_coverage_uses_exact_integer_cross_multiplication(self):
    facts = fixture_facts(due=20, terminal=20, observed=19)
    result = evaluate_challenger_replacement_operational_readiness(
        facts, fixture_boundary(elapsed_days=7)
    )
    self.assertEqual(result.observed_coverage_numerator, 19)
    self.assertEqual(result.observed_coverage_denominator, 20)
    self.assertTrue(result.meets_minimum_observed_coverage)

def test_operational_rejects_boolean_count(self):
    with self.assertRaisesRegex(
        ChallengerReplacementReadinessError,
        "CHALLENGER_REPLACEMENT_READINESS_FACTS_INVALID",
    ):
        ReplacementReadinessFacts(due_opportunity_count=True, **valid_fact_fields())
```

- [x] **Step 2: Run the focused RED**

Run:

```bash
python -m unittest tests.test_challenger_replacement_readiness -v
```

Expected: import failure because the readiness module does not exist.

- [x] **Step 3: Implement minimal frozen types and validators**

Use exact frozen dataclasses with explicit slots and tuple-only ordered facts:

```python
@dataclass(frozen=True)
class OpportunityReadinessFact:
    __slots__ = (
        "opportunity_id", "scheduled_for", "outcome",
        "terminal_recorded_at", "observed_at_or_null",
        "missed_reason_or_null", "detected_at_or_null",
        "result_evidence_sha256_or_null",
        "position_before", "position_after", "product_or_null",
        "lifecycle_status_or_null", "risk_state",
        "protective_stop_status", "economic_gap_locked",
        "unresolved_reason_codes",
    )
    opportunity_id: str
    scheduled_for: str
    outcome: str
    terminal_recorded_at: str
    observed_at_or_null: Optional[str]
    missed_reason_or_null: Optional[str]
    detected_at_or_null: Optional[str]
    result_evidence_sha256_or_null: Optional[str]
    position_before: str
    position_after: str
    product_or_null: Optional[str]
    lifecycle_status_or_null: Optional[str]
    risk_state: str
    protective_stop_status: str
    economic_gap_locked: bool
    unresolved_reason_codes: Tuple[str, ...]

@dataclass(frozen=True)
class _ReplacementReadinessBoundary:
    __slots__ = (
        "qualification", "start_opportunity_id_or_null",
        "start_scheduled_for_or_null", "start_observed_at_or_null",
        "observed_at",
    )
    qualification: str
    start_opportunity_id_or_null: Optional[str]
    start_scheduled_for_or_null: Optional[str]
    start_observed_at_or_null: Optional[str]
    observed_at: str

@dataclass(frozen=True)
class ReplacementReadinessFacts:
    __slots__ = (
        "qualification", "plan_id", "plan_hash",
        "event_evidence_identity_hash", "release_provenance_hash",
        "event_chain_end_hash_or_null", "opportunities",
        "terminal_opportunity_count", "observed_opportunity_count",
        "missed_opportunity_count", "current_consecutive_missed",
        "maximum_consecutive_missed", "last_missed_reason_or_null",
        "active_opportunity_present", "current_position",
        "gross_exposure", "open_order_count", "unknown_order_count",
        "reconciliation_status", "protective_stop_status", "risk_state",
        "daily_loss_boundary_state", "drawdown_boundary_state",
        "incident_count", "evidence_failure_kind_or_null",
    )
    qualification: str
    plan_id: str
    plan_hash: str
    event_evidence_identity_hash: str
    release_provenance_hash: str
    event_chain_end_hash_or_null: Optional[str]
    opportunities: Tuple[OpportunityReadinessFact, ...]
    terminal_opportunity_count: int
    observed_opportunity_count: int
    missed_opportunity_count: int
    current_consecutive_missed: int
    maximum_consecutive_missed: int
    last_missed_reason_or_null: Optional[str]
    active_opportunity_present: bool
    current_position: str
    gross_exposure: str
    open_order_count: int
    unknown_order_count: int
    reconciliation_status: str
    protective_stop_status: str
    risk_state: str
    daily_loss_boundary_state: str
    drawdown_boundary_state: str
    incident_count: int
    evidence_failure_kind_or_null: Optional[str]

@dataclass(frozen=True)
class OperationalReadinessResult:
    __slots__ = (
        "evidence_qualification", "policy_status", "authority_status",
        "elapsed_complete_days", "due_opportunity_count",
        "terminal_opportunity_count", "observed_opportunity_count",
        "missed_opportunity_count", "observed_coverage_numerator",
        "observed_coverage_denominator",
        "meets_minimum_observed_coverage", "terminal_coverage_complete",
        "strategy_cycle_count", "spot_roundtrip_count",
        "perpetual_roundtrip_count", "reason_codes",
    )

@dataclass(frozen=True)
class EconomicTailObservation:
    __slots__ = (
        "evidence_qualification", "status", "elapsed_complete_days",
        "minimum_calendar_days", "due_opportunity_count",
        "terminal_opportunity_count", "observed_opportunity_count",
        "missed_opportunity_count", "meets_minimum_observed_coverage",
        "terminal_coverage_complete", "lifecycle_complete",
        "unresolved_safety_failure", "next_boundary_or_null",
    )
```

Keep constructors strict inside evaluator validation. The only v0.73 boundary
qualification is `COMMITTED_FIXTURE_BOUNDARY_NOT_OPERATIONAL`; no public
constructor or CLI accepts its individual fields.

- [x] **Step 4: Implement exact coverage representation**

Compare `observed * 100 >= due * 95` and `terminal == due`; never convert to
float or Decimal. Return numerator, denominator,
`meets_minimum_observed_coverage` and `terminal_coverage_complete`. UI later
renders `numerator / denominator`; no rounded value participates in policy.

- [x] **Step 5: Run GREEN and commit**

Run the focused test and `git diff --check`. Commit:

```bash
git add src/crypto_quant/challenger_replacement_readiness.py tests/test_challenger_replacement_readiness.py
git commit -m "feat: define replacement readiness facts"
```

---

### Task 2: Implement Cycle Reduction and Operational Policy

**Files:**
- Modify: `src/crypto_quant/challenger_replacement_readiness.py`
- Modify: `tests/test_challenger_replacement_readiness.py`

**Interfaces:**
- Consumes: ordered `OpportunityReadinessFact` tuple and fixed boundary from Task 1.
- Produces: immutable `OperationalReadinessResult` with `policy_status`, `authority_status`, coverage/cycle counts and ordered reason codes.

- [x] **Step 1: Add RED for state-machine cycle counting**

Cover Spot open/HOLD/close, perpetual open/HOLD/close, MISSED while flat,
permanently gap-locked MISSED while exposed, cross-product reversal, non-flat terminal, failed
lifecycle and duplicate transition:

```python
def test_three_cycles_with_both_products_meet_cycle_gate(self):
    facts = facts_for_cycles(("SPOT", "PERPETUAL", "SPOT"))
    result = evaluate_challenger_replacement_operational_readiness(
        facts, fixture_boundary(elapsed_days=7)
    )
    self.assertEqual(result.strategy_cycle_count, 3)
    self.assertEqual(result.spot_roundtrip_count, 2)
    self.assertEqual(result.perpetual_roundtrip_count, 1)

def test_missed_while_exposed_does_not_create_or_complete_cycle(self):
    result = evaluate_challenger_replacement_operational_readiness(
        facts_with_exposed_gap(), fixture_boundary(elapsed_days=8)
    )
    self.assertEqual(result.policy_status, "OPERATIONAL_QUALIFICATION_DID_NOT_PASS")
    self.assertIn("ECONOMIC_GAP_LOCKED", result.reason_codes)
```

- [x] **Step 2: Add RED for status precedence**

Test day 6 versus day 7, 94% versus exact 95%, missing terminal, two versus
three cycles, single-product coverage, every v0.69 frozen failure reason,
S0/S1 and incident precedence. Separately test a readable hash/parent/
attachment/identity mismatch versus a missing/unreadable/qualification-unknown
source. Require exact order:

```text
confirmed safety or evidence durability/identity violation -> DID_NOT_PASS
missing/unreadable/qualification-unknown evidence -> INCONCLUSIVE_INSUFFICIENT_EVIDENCE
no start -> NOT_STARTED
pre-seven-day -> COLLECTING_BEFORE_MINIMUM_DURATION
insufficient evidence -> PENDING_AUTOMATIC_EXTENSION
all gates -> OPERATIONAL_QUALIFICATION_PASS
```

Here `insufficient evidence` in the extension row means valid evidence whose
coverage/cycles can improve with future opportunities; it does not include
unavailable, unreadable, ambiguous or unqualified evidence. Flat MISSED may recover the ratio through
later opportunities. Exposed MISSED never clears its gap/stage failure in the
current stream.

Add a combination regression: when a confirmed readable durability/identity
violation and an unavailable secondary source coexist, DID_NOT_PASS wins over
INCONCLUSIVE.

Also assert `authority_status` remains
`FIXTURE_POLICY_RESULT_NOT_OPERATIONAL` even when `policy_status` is PASS.

- [x] **Step 3: Run RED and record the exact failing assertions**

Run:

```bash
python -m unittest tests.test_challenger_replacement_readiness -v
```

Expected: cycle/status assertions fail while Task 1 validation tests remain
green.

- [x] **Step 4: Implement the minimum single-pass reducer**

Track only verified position state and open-cycle product. Do not create a
general order state machine. Count a cycle only for:

```text
FLAT -> SPOT_LONG -> FLAT
FLAT -> PERP_SHORT -> FLAT
```

Any direct product switch, unknown state, unresolved reason or failed lifecycle
enters the ordered reason set and prevents PASS. Derive all counts; callers
cannot supply them separately.

- [x] **Step 5: Implement status selection and immutable result**

Calculate elapsed complete days from canonical UTC times with integer seconds.
Keep `policy_status` distinct from `authority_status`. Never publish a result
file in this module.

- [x] **Step 6: Run GREEN, adjacent opportunity tests and commit**

Run:

```bash
python -m unittest tests.test_challenger_replacement_readiness tests.test_challenger_replacement_opportunities tests.test_challenger_replacement_binance_lifecycle -v
git diff --check
```

Commit:

```bash
git add src/crypto_quant/challenger_replacement_readiness.py tests/test_challenger_replacement_readiness.py
git commit -m "feat: evaluate replacement operational readiness"
```

---

### Task 3: Enforce the 90-Day Tail-Blind Economic Boundary

**Files:**
- Modify: `src/crypto_quant/challenger_replacement_readiness.py`
- Modify: `tests/test_challenger_replacement_readiness.py`

**Interfaces:**
- Consumes: Task 1 facts/boundary but only structural counts, lifecycle-complete boolean and unresolved-safety reasons.
- Produces: `EconomicTailObservation`; no economic-final result type or publisher.

- [x] **Step 1: Add RED at no-start/day-89/day-90 boundaries**

```python
def test_day_89_withholds_economics(self):
    value = observe_challenger_replacement_economic_tail(
        fixture_facts(), fixture_boundary(elapsed_days=89)
    )
    self.assertEqual(value.status, "WITHHELD_PRE_TAIL")
    self.assertFalse(hasattr(value, "pnl"))

def test_day_90_reports_missing_preregistered_final_evaluator(self):
    value = observe_challenger_replacement_economic_tail(
        fixture_facts(), fixture_boundary(elapsed_days=90)
    )
    self.assertEqual(
        value.status,
        "TAIL_REACHED_FINAL_EVALUATOR_NOT_PREREGISTERED",
    )
```

- [x] **Step 2: Add post-sanitizer semantic-access RED**

Use a test-only object whose PnL/fee/funding/drawdown/return attributes raise
and count semantic access after strict-loader validation. Pass only the
sanitized structural fact object to readiness functions; assert all counters
remain zero and no economic token occurs in `repr`, dataclass fields or
canonical observer output. Do not claim the strict JSON loader avoided parsing
the complete v0.72 document.

- [x] **Step 3: Add static API RED**

Assert no function/class matching `economic.*result`, `profit.*gate`,
`publish.*economic`, or a public parameter named `pnl`, `fee`, `funding`,
`return`, `drawdown`, `threshold` exists in the new module.

- [x] **Step 4: Implement four exact tail statuses**

Implement only:

```text
NOT_STARTED
WITHHELD_PRE_TAIL
TAIL_REACHED_FINAL_EVALUATOR_NOT_PREREGISTERED
FAILED_CLOSED
```

Return counts, coverage health, elapsed/minimum days, lifecycle completeness,
unresolved-safety boolean and next boundary only.

- [x] **Step 5: Run GREEN and commit**

Run focused readiness tests and `git diff --check`. Commit:

```bash
git add src/crypto_quant/challenger_replacement_readiness.py tests/test_challenger_replacement_readiness.py
git commit -m "feat: enforce replacement economic tail blindness"
```

---

### Task 4: Build the One-Pass Read-Only Fixture Observer

**Files:**
- Create: `src/crypto_quant/challenger_replacement_readiness_observer.py`
- Create: `tests/test_challenger_replacement_readiness_observer.py`

**Interfaces:**
- Consumes: a reviewed replay-only façade, private fixture boundary, frozen v0.72 fixture event-evidence identity and separate real release-provenance identity.
- Produces: `ReplacementReadinessObservation` containing typed facts, operational result, economic tail observation and provenance hash.
- Does not produce: receipt, artifact, event, export, path discovery or mutable state.

Use this exact immutable composition type:

```python
@dataclass(frozen=True)
class ReplacementReadinessObservation:
    __slots__ = (
        "authority_status", "service_health", "evidence_health",
        "observed_at", "event_evidence_identity_hash",
        "release_provenance_hash", "provenance_hash", "facts",
        "operational", "economic",
    )
    authority_status: str
    service_health: str
    evidence_health: str
    observed_at: str
    event_evidence_identity_hash: str
    release_provenance_hash: str
    provenance_hash: str
    facts: ReplacementReadinessFacts
    operational: OperationalReadinessResult
    economic: EconomicTailObservation
```

- [x] **Step 1: Add RED for strict ordered projection conversion**

Rebuild the committed v0.72 Spot and perpetual fixture streams in owner-only
temporary event roots. Verify one replay call yields ordered facts and exact
position transitions, lifecycle status, stop status and unresolved reasons.

```python
def test_observer_reduces_strict_v2_projection_once(self):
    replay_source = committed_spot_and_perp_replay_facade()
    with mock.patch.object(replay_source, "replay", wraps=replay_source.replay) as replay:
        observed = observe_challenger_replacement_readiness(
            replay_source=replay_source,
            boundary=_fixture_boundary_for_tests(),
            release_provenance=fixture_release_provenance(),
        )
    self.assertEqual(replay.call_count, 1)
    self.assertEqual(observed.authority_status, "FIXTURE_NOT_OPERATIONAL")
```

- [x] **Step 2: Add RED for failure closure and zero writes**

Patch event append/publish, `open` write modes, `Path.write_*`, chmod, rename,
network, subprocess and runtime discovery. Assert counts stay zero. Malformed
v1 result in v0.72 identity, mixed build, parent mismatch, bad lifecycle,
orphan staging, replay failure and arbitrary boundary mapping return/raise only
fixed reason codes without input/exception bytes.

Add a static assertion that the observer module imports no event append/publish
symbol and that the façade exposes only `replay()`.

- [x] **Step 3: Run RED**

Run:

```bash
python -m unittest tests.test_challenger_replacement_readiness_observer -v
```

Expected: module import failure.

- [x] **Step 4: Implement minimal conversion using the strict projection**

Call `replay_source.replay()` once. Require its exact public projection shape
and frozen v0.72 fixture event-evidence identity. Iterate terminal opportunities
in schedule order. For OBSERVED, pass already strict-loaded v2 evidence through
one reviewed sanitizer that extracts only lifecycle/position/stop/risk-boundary
facts; for MISSED, create no economic transition. Bind real release provenance
separately. Never compare release provenance to fixture event identity and do
not serialize nested evidence into output.

- [x] **Step 5: Collapse expected loader failures without catching control-flow exceptions**

Map a readable proof of hash, parent, attachment, durability or identity
violation to `CONFIRMED_EVIDENCE_DURABILITY_OR_IDENTITY_FAILURE`, which the
policy maps to DID_NOT_PASS. Map missing/unreadable sources and qualifications
that cannot be established to
`EVIDENCE_SOURCE_UNAVAILABLE_OR_QUALIFICATION_UNKNOWN`, which maps to
INCONCLUSIVE. Preserve unexpected `KeyboardInterrupt`, `SystemExit` and memory
errors. Never include raw exception text in reason codes.

- [x] **Step 6: Run GREEN, v0.70/v0.72 adjacent tests and commit**

```bash
python -m unittest tests.test_challenger_replacement_readiness_observer tests.test_challenger_replacement_opportunities tests.test_challenger_replacement_fixture_simulation -v
git diff --check
git add src/crypto_quant/challenger_replacement_readiness_observer.py tests/test_challenger_replacement_readiness_observer.py
git commit -m "feat: observe replacement readiness evidence"
```

---

### Task 5: Add Strict Operations Projection v2

**Files:**
- Create: `src/crypto_quant/operations_projection_v2.py`
- Create: `config/operations-projection-v2.schema.json`
- Create: `src/crypto_quant/schemas/operations-projection-v2.schema.json`
- Create: `tests/test_operations_projection_v2.py`

**Interfaces:**
- Consumes: `OperationsProjectionV2Sources`, which contains existing typed `ReleaseOperationsSource`, existing typed `ChallengerOperationsSource` for immutable legacy failure, `ReplacementReadinessObservation`, and existing typed `SystemPaperOperationsSource`.
- Produces: `build_operations_projection_v2(sources, *, boundary) -> bytes`, where `boundary` is a private fixture-qualified typed boundary rather than a public arbitrary timestamp.
- Produces: `load_operations_projection_v2_bytes(body) -> Mapping[str, Any]`.

Define the exact source container:

```python
@dataclass(frozen=True)
class OperationsProjectionV2Sources:
    __slots__ = (
        "release", "legacy_challenger", "replacement_v3", "system_paper"
    )
    release: ReleaseOperationsSource
    legacy_challenger: ChallengerOperationsSource
    replacement_v3: ReplacementReadinessObservation
    system_paper: SystemPaperOperationsSource

@dataclass(frozen=True)
class _OperationsProjectionV2Boundary:
    __slots__ = ("qualification", "observed_at")
    qualification: str
    observed_at: str
```

Only `COMMITTED_FIXTURE_BOUNDARY_NOT_OPERATIONAL` is accepted in v0.73; no
public CLI or constructor accepts its fields.

- [x] **Step 1: Add RED for mirrored schema and canonical output**

Test exact mirror bytes, Draft 2020-12 validity, exact top-level keys,
self-hash, deterministic output and one fixture-qualified valid projection.
Require replacement fields from the spec, with `daily_loss_boundary_state` and
`drawdown_boundary_state` enums instead of economic amounts.

- [x] **Step 2: Add RED for semantic invariants**

Reject count contradictions, terminal greater than due, observed+missed not
equal terminal, incorrect numerator/denominator/threshold boolean, PASS with insufficient cycles/products,
non-flat without confirmed stop, unknown order with risk advisory, stale source
marked healthy, economic final status, bool/int substitution and extra fields.

- [x] **Step 3: Add RED for typed-source and strict-byte boundary**

Reject plain dictionaries passed as sources, non-bytes, empty/oversize input,
duplicate keys, float, noncanonical JSON, unsafe integer, wrong schema/version,
unknown enum and self-hash mismatch.

- [x] **Step 4: Run RED**

```bash
python -m unittest tests.test_operations_projection_v2 -v
```

Expected: module/schema absence failures.

- [x] **Step 5: Implement schema, typed builder and strict loader**

Follow the v1 canonical/self-hash pattern without importing or mutating v1
private state. Build every output field explicitly. v2 `new_risk_advisory` is
always false for `FIXTURE_NOT_OPERATIONAL`, NOT_STARTED, stale, failed,
unreconciled, unknown, stop-unconfirmed or incident states.

- [x] **Step 6: Run GREEN, v1 regression and commit**

```bash
python -m unittest tests.test_operations_projection_v2 tests.test_operations_projection -v
cmp config/operations-projection-v2.schema.json src/crypto_quant/schemas/operations-projection-v2.schema.json
git diff --check
git add src/crypto_quant/operations_projection_v2.py config/operations-projection-v2.schema.json src/crypto_quant/schemas/operations-projection-v2.schema.json tests/test_operations_projection_v2.py
git commit -m "feat: add replacement operations projection v2"
```

---

### Task 6: Integrate v2 Alerts and the Existing Read-Only Console

**Files:**
- Modify: `src/crypto_quant/operations_alerts.py`
- Modify: `src/crypto_quant/operations_dashboard.py` only if strict dispatch cannot stay entirely in alerts.
- Modify: `src/crypto_quant/dashboard/index.html`
- Modify: `src/crypto_quant/dashboard/app.js`
- Modify: `src/crypto_quant/dashboard/styles.css`
- Modify: `tests/test_operations_alerts.py`
- Modify: `tests/test_operations_dashboard.py`

**Interfaces:**
- Consumes: exact v1 or v2 canonical projection bytes.
- Produces: existing `derive_operations_alerts` and `build_operations_status_body` APIs with strict schema dispatch.
- Preserves: existing four routes, loopback binding, headers, method denial and v1 response bytes.

- [x] **Step 1: Freeze v1 compatibility with committed bytes**

Add a golden SHA assertion for the existing v1 healthy fixture and exact status
response before changing dispatch. Re-run current v1 alerts/dashboard tests as
the RED baseline guard; they must remain green.

- [x] **Step 2: Add v2 RED for deterministic alerts**

Test fixed alert ordering for terminal gaps, MISSED/coverage warning,
automatic extension, UNKNOWN, stop missing, reconciliation mismatch,
stage-failed lock, S0/S1 and release identity failure. Assert every critical
condition yields `new_risk_allowed=false` and no economic value appears.

- [x] **Step 3: Add v2 RED for DOM and HTTP safety**

Assert v2 labels exist for opportunities, elapsed days, cycle/product
coverage, reconciliation and boundary states. Require `textContent`, no
`innerHTML`, no action form/button, no extra fetch/route/WebSocket/external URL,
and no PnL/return/drawdown amount/credential/path tokens.

- [x] **Step 4: Run RED**

```bash
python -m unittest tests.test_operations_alerts tests.test_operations_dashboard -v
```

Expected: v2 schema dispatch and labels fail while v1 tests remain green.

- [x] **Step 5: Implement exact schema dispatch and allowlisted response**

Read only `$schema` and `schema_version` through the existing duplicate-key
rejecting bounded decoder, then call exactly one strict loader. Do not catch a
v2 loader error and retry as v1. Build the status body field-by-field and keep
all fixed HTTP behavior unchanged.

- [x] **Step 6: Update the four existing read-only views**

Reuse existing DOM regions. Render replacement-v3 opportunity/readiness values
without adding navigation, controls or a second server. Keep presentation
labels neutral: fixture policy PASS must display `NOT OPERATIONAL`.

- [x] **Step 7: Run GREEN, static asset checks and commit**

```bash
python -m unittest tests.test_operations_projection tests.test_operations_projection_v2 tests.test_operations_alerts tests.test_operations_dashboard -v
git diff --check
git add src/crypto_quant/operations_alerts.py src/crypto_quant/operations_dashboard.py src/crypto_quant/dashboard tests/test_operations_alerts.py tests/test_operations_dashboard.py
git commit -m "feat: display replacement readiness read only"
```

If `operations_dashboard.py` has no necessary diff, omit it from `git add` and
record that the HTTP boundary required no modification.

---

### Task 7: Close Fault, Compatibility and Authority Gates

**Files:**
- Modify only the Task 1-6 test files unless a RED proves a production defect.
- Add: `tests/test_v073_authority_boundaries.py`

**Interfaces:**
- Consumes: all v0.73 public modules and released v0.69-v0.72/v0.60-v0.61 artifacts.
- Produces: one focused cross-component acceptance suite and static authority scan.

- [x] **Step 1: Add cross-component RED**

Rebuild both v0.72 complete-cycle fixtures, observe them, evaluate policy,
create projection-v2, derive alerts and build dashboard status bytes. Assert
the entire flow is deterministic and remains fixture/not-started authority.

- [x] **Step 2: Add failure-flow RED**

Inject an unresolved UNKNOWN, missing stop, ledger mismatch, MISSED gap and
stale provenance through existing private fixture boundaries. Assert each
flows to failed/extension state without changing event bytes or exposing
economics.

Require exposed MISSED to stay DID_NOT_PASS/gap-locked even after later valid
fixtures; only a flat MISSED coverage deficit may move from extension to the
coverage threshold. Require a proved hash/identity/durability violation to be
DID_NOT_PASS, while unavailable/unreadable/qualification-unknown evidence is
INCONCLUSIVE.

- [x] **Step 3: Add frozen-byte and forbidden-authority scans**

Hash every committed v0.69-v0.72 artifact/fixture and the v1 projection fixture
against the release baseline. AST-scan new modules for forbidden imports and
public parameter names. Patch network, subprocess, launchctl, keyring,
filesystem-write, event publish, Broker and venue-order boundaries and require
all counts zero.

- [x] **Step 4: Run focused and adjacent acceptance tests**

```bash
python -m unittest \
  tests.test_challenger_replacement_readiness \
  tests.test_challenger_replacement_readiness_observer \
  tests.test_operations_projection_v2 \
  tests.test_operations_projection \
  tests.test_operations_alerts \
  tests.test_operations_dashboard \
  tests.test_challenger_replacement_opportunities \
  tests.test_challenger_replacement_binance_lifecycle \
  tests.test_challenger_replacement_fixture_simulation \
  tests.test_v073_authority_boundaries -v
python -m compileall -q src tests
git diff --check
```

- [x] **Step 5: Enforce line budgets and commit**

```bash
wc -l \
  src/crypto_quant/challenger_replacement_readiness.py \
  src/crypto_quant/challenger_replacement_readiness_observer.py \
  src/crypto_quant/operations_projection_v2.py \
  src/crypto_quant/operations_alerts.py \
  src/crypto_quant/operations_dashboard.py
```

Every value must be at most 700. Commit:

```bash
git add tests/test_v073_authority_boundaries.py
git commit -m "test: close v073 readiness authority gates"
```

---

### Task 8: Independent Review, Release Metadata and Final Verification

**Files:**
- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `src/crypto_quant/__init__.py`
- Modify: `config/crypto-quant-build-manifest-v1.json`
- Add: `docs/adr/0073-replacement-v3-readiness-and-tail-blind-observation.md`.
- Add: `docs/implementation-status-v0.73.0.md`
- Modify: this plan only to check completed boxes after evidence exists.

**Interfaces:**
- Consumes: final reviewed code and exact test evidence.
- Produces: v0.73 candidate metadata and public release evidence; no runtime artifact.

- [ ] **Step 1: Request one independent complete review**

Give the reviewer the spec, plan, full diff from `v0.72.0^{}` and focused test
evidence. Require Critical and Important zero. Fix findings through targeted
RED/GREEN commits and request only targeted rereview.

- [ ] **Step 2: Write ADR and implementation status**

Record the selected split, rejected post-hoc economic evaluator, exact
authority zeros, fixture-only qualification, economic preregistration gap and
next milestone. Do not claim Paper started, operational PASS, economic PASS,
Canary eligibility or live readiness.

- [ ] **Step 3: Update package/build identity once**

Set package version `0.73.0` in `pyproject.toml` and
`src/crypto_quant/__init__.py`, set manifest version `1.67.0`,
and enumerate every changed production/schema/static/doc/test file. Recompute
the manifest through the repository's canonical build command only after all
other candidate bytes are final.

- [ ] **Step 4: Run one final local full verification**

Run exactly once for the final code state:

```bash
python -m unittest discover -s tests
python -m compileall -q src tests
make validate
git diff --check
git status --short
```

Record exact executed/pass/skip/failure counts, manifest hash, build-input-tree
hash, module line counts and authority scan. Any failure stops release.

- [ ] **Step 5: Commit the final candidate**

```bash
git add README.md pyproject.toml config src docs tests
git commit -m "feat: release replacement readiness integration"
git status --short
```

Require a clean worktree. Do not amend signed v0.69-v0.72 artifacts.

- [ ] **Step 6: Publish through the approved public GitHub workflow**

After local gates and review are green:

1. verify PUBLIC repository, exact origin, `main`, ADMIN permission and clean
   candidate;
2. push only `codex/v0.73-lifecycle-readiness-integration`;
3. create a Draft PR and wait for Python 3.9, Python 3.12 and macOS arm64 CI;
4. mark ready/merge only if exact head CI is green;
5. wait for exact merged-main CI;
6. create annotated `v0.73.0` at exact `origin/main` and push only that tag;
7. verify tag object type, annotation, peeled commit and `origin/main` equality.

Healthy completion proves only
`READINESS_EVALUATOR_AND_READ_ONLY_INTEGRATION_VERIFIED_NOT_STARTED`.

---

## Completion Check

v0.73 is complete only when all eight tasks are checked, independent review is
Critical/Important zero, final local validation and all three remote CI jobs
are green, and annotated `v0.73.0` peels exactly to `origin/main`. The release
must still show no install/start/credential/network/Broker/order/fund authority,
no operational or economic wall-clock start, no final economic evaluator and
no profitability, AI-advantage, Canary or live-readiness claim.
