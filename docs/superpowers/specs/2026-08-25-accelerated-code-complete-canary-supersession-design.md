# Accelerated Code-Complete and Canary Supersession Design

**Status:** Draft exact design awaiting written approval
**Target governance release:** v0.75.0
**Predecessor:** annotated v0.74.0, peeled commit
`bfe0080b0a29a74550449a1eb2ac2907a2d2ddac`
**Release class:** plan-only governance; no installation, activation, credential,
account, order or fund authority

## 1. Purpose

This design shortens the engineering critical path without rewriting research
history or weakening the money-safety boundary. It establishes:

1. a 10–14 day target for `CODE_COMPLETE_NOT_ACTIVATED`;
2. a production-like, credential-free 72-hour simulation qualification;
3. a separately approved, minimum-size Binance operational ceremony;
4. the existing E0/E1/E2 engineering-Canary ladder; and
5. an independent, unchanged 90-day economic research track.

The 72-hour qualification and ceremony test operability, recovery and account
integration. They do not test profitability. The v0.74 90-day evaluator remains
the only frozen authority for the replacement-v3 economic research conclusion.

v0.75 itself only preregisters the new boundaries. It does not install or start
a service, create or read a credential, call a private Binance endpoint, submit
an order, move funds, start a 72-hour or 90-day clock, or grant E0 authority.

## 2. Immutable foundation and authority boundary

The following released facts remain immutable:

- v0.69 plan file SHA-256
  `6fae2ae0df4b8402ddc1df1b5bca611e11df41eee8d42f591d5d7b5fb24a31c3`,
  plan ID
  `challenger_replacement_plan_v3_e1b6a4187cb4bb4b371ea503f83284056d4f0c6c504feb7827971869a52f666f`
  and plan hash
  `f29474a1700b0c3cf313047e2d6e85182e68104d9584ec9df7b492aa7ab00486`;
- v0.73 release manifest version `1.67.0`, package `0.73.0`, peeled
  commit `34bd0e9ba96c769b7301c482730a03fb975c24ce` and manifest hash
  `0117d3a17bdea7e2a22004d675175083e9d863722c6c176632d29e3c4c6e62d0`;
- v0.74 economic plan file SHA-256
  `24fba7579ac36c037aaef4fbf34a69b56503358edbd64addbe01f30a70c33297`,
  plan ID
  `challenger_replacement_economic_evaluation_plan_13ba2b74dd8c330732789a3fccd36f017847047f9fd07ea0bcf36b66f54a943e`
  and plan hash
  `7c02267a0895cb3d8ceea79b6a38415140de23fb1cfcf3350c7fddff62089fa4`;
- annotated v0.74.0 tag object
  `86624de8be8d5117e4b4ef6fd825a9eb711c7c38`, peeled to
  `bfe0080b0a29a74550449a1eb2ac2907a2d2ddac`.

The v0.75 formal plan must keep these authority values:

```text
production_activation = false
runtime_install_authorized = false
replacement_start_authorized = false
credentials_allowed = false
account_requests_allowed = false
broker_requests_allowed = false
real_orders_allowed = false
fund_movement_allowed = false
ceremony_authorized = false
e0_activation_authorized = false
market_requests = 0
private_account_requests = 0
production_state_writes = 0
economic_outcome_reads = 0
```

No general approval may be interpreted as any of the separately enumerated
irreversible approvals in section 14.

## 3. Conflict analysis and exact supersession scope

### 3.1 Rules that remain unchanged

The new plan preserves:

- one DecisionOpportunity every four hours;
- terminal `OBSERVED` or `MISSED`, no historical decision backfill;
- one append-only canonical event log as the shared fact source;
- Binance only, ETH/USDT Spot long and ETHUSDT USDⓈ-M perpetual short;
- product mutual exclusion and verified flatness before reversal;
- one-way isolated perpetual mode and technical leverage cap 2×;
- fixed E0/E1/E2 capital and gross-exposure caps;
- withdrawal-disabled, IP-allowlisted, least-privilege, owner-only credentials;
- immutable incident, order, fill, fee, funding, position and reconciliation
  evidence;
- no profitability or AI-advantage claim from operational evidence; and
- a separate approval for every money-bearing activation.

### 3.2 Rules explicitly superseded for operational Canary eligibility

| Released rule | New rule | Scope |
|---|---|---|
| v0.69/v0.73 require at least seven days, three natural strategy cycles and both product roundtrips before E0 discussion | 72 qualified hours plus the full frozen fault matrix, followed by a separately approved operational ceremony | Operational Canary eligibility only |
| v0.73 makes an exposed `MISSED` a permanent stream lock | The current operational stage block fails and must flatten; after immutable incident acceptance, a new block may start | Operational stage projection only |
| v0.73 treats a broad list of conditions as terminal operational failure | Only the four section 9 hard-stop classes permanently fail the current stage block; recoverable conditions extend or restart qualification | Operational stage projection only |
| v0.69 requires Spot and perpetual roundtrips inside the pre-E0 natural simulation window | The minimum-size ceremony supplies operational product coverage but is explicitly excluded from strategy and economic evidence | Operational integration proof only |

### 3.3 Rules not superseded

The v0.74 economic population, start receipt, 90-day half-open window, metrics,
thresholds, missingness treatment and first-final-result semantics are unchanged.
In particular:

- exposed `MISSED` remains visible and is evaluated exactly as v0.74 specifies;
- no 90-day reset, alternate start, selective deletion or rerun is allowed;
- ceremony activity is never a strategy opportunity or economic strategy cycle;
- an operational stage may resume while the independent 90-day evaluator may
  still later return `DID_NOT_PASS` or `INCONCLUSIVE`; and
- E0/E1 engineering operation cannot be described as profitability validation.

This is therefore a supersession of operational eligibility and incident
recovery, not a retrospective amendment of the economic research hypothesis.

## 4. Selected architecture

### 4.1 Dual projections over one fact source

The append-only canonical DecisionOpportunity/event log remains the sole
authority for what happened. Two deterministic, read-only projections consume
it:

1. `EconomicResearchProjectionV1`, fixed by v0.74; and
2. `OperationalCanaryProjectionV2`, introduced by this supersession.

The second projection adds qualification blocks, ceremony blocks, stage blocks,
incidents and approval bindings. It cannot delete, rewrite or hide an event used
by the economic projection. Neither projection may write facts or become an
alternative order/position authority. UI and exports consume strict projections
and remain non-authoritative.

### 4.2 Rejected alternatives

**Rewrite v0.74 in place.** Rejected because it would be a post-release change
to a preregistered economic question.

**Reset replacement v3 as a new research generation.** Rejected because the
operational acceleration does not require discarding research history. A new
research generation is required only for a future changed economic hypothesis.

**Use ceremony fills as strategy evidence.** Rejected because deliberately
forced trades do not represent the strategy's natural decision distribution.

## 5. Minimal version plan and 10–14 day critical path

The default release split is deliberately limited to three reviewable releases:

### v0.75 — governance supersession

- exact accelerated plan schema, parameterless builder and strict loader;
- immutable supersession record binding v0.69, v0.73 and v0.74;
- no runtime, deployment, account or order behavior.

### v0.76 — public simulation and research bundle

- final v0.74 90-day evaluator and strict result loader;
- public-market replacement-v3 service, four-hour scheduler, immutable event
  projection and crash/restart recovery;
- deployment/install contract, preflight, read-only observer and start-receipt
  code, without performing installation;
- 72-hour qualification evaluator and full fixture-driven fault matrix;
- retained v0.61 loopback-only read-only console integration.

### v0.77 — Binance private boundary and Canary bundle

- private Binance Spot/perpetual adapters tested only with fixtures, mocks and
  protocol contracts;
- signing, least-privilege credential capability, one-way/isolated/2× checks,
  stable client order IDs, ACK/partial fill/cancel/UNKNOWN, reduce-only,
  protective-stop, fee/funding/position/balance reads and reconciliation;
- operational ceremony controller;
- E0/E1/E2 stage controller, loss/drawdown gates, promotion and incident-block
  recovery;
- alerts, runbooks, secret-absence tests, install/config templates, fault
  injection and the `CODE_COMPLETE_NOT_ACTIVATED` dossier.

The target schedule, measured from 2026-08-25 and contingent on zero unresolved
P0/P1 findings, is:

| Date | Milestone |
|---|---|
| Aug 25–26 | v0.75 exact spec, plan-only implementation and release |
| Aug 27–Sep 1 | v0.76 TDD, independent review and release |
| Sep 2–8 | v0.77 TDD, independent review, final verification and dossier |

The estimated `CODE_COMPLETE_NOT_ACTIVATED` date is 2026-09-04 through
2026-09-08. This is an engineering estimate, not permission to skip a test,
review or approval gate. A real defect extends the date rather than lowering the
gate.

## 6. Definition of CODE_COMPLETE_NOT_ACTIVATED

The milestone is reached only when all v0.75–v0.77 requirements are mapped to
code and tests or an explicit N/A, Critical/Important review findings are zero,
the final code state has one full local suite plus release validation, supported
remote CI identities are green, annotated tags match main, and the dossier
contains:

- architecture and canonical-requirement mapping;
- exact versions, commits, tag objects, manifests and dependency hashes;
- deterministic fixtures and protocol conformance evidence;
- fault-injection, restart, reconciliation and secret-absence results;
- read-only operations-console acceptance;
- install, recovery, incident and rollback runbooks; and
- the precise external actions still awaiting user approval or wall time.

At this milestone production activation is still false. No real service has
been installed, no 72-hour or 90-day clock has started, no secret has been read,
and no Binance account request, order or fund movement has occurred.

## 7. Exact 72-hour qualification state machine

The operational qualification record is append-only and block-scoped:

```text
CODE_COMPLETE_NOT_ACTIVATED
  -> INSTALL_APPROVAL_REQUIRED
  -> PREFLIGHT_PENDING
  -> SIM_72H_READY
  -> SIM_72H_ACTIVE
  -> SIM_72H_QUALIFIED
  -> CEREMONY_APPROVAL_REQUIRED
```

The 72-hour clock starts only from a future immutable start receipt bound to the
first naturally scheduled, production-qualified `OBSERVED` opportunity after a
successful installation and preflight. Release, install and preflight times do
not start it.

One qualification block may retain multiple attempted healthy segments, but
PASS is based only on its final uninterrupted segment. Qualification requires
all of the following:

- at least 72 real wall-clock hours after the bound start;
- service, scheduler, clock and canonical evidence continuity for the entire
  qualified interval;
- every due opportunity has a terminal `OBSERVED` or `MISSED` outcome;
- no unresolved order/fill/position/reconciliation or evidence identity state;
- the complete frozen offline fault-injection matrix passes against the exact
  released build; and
- current health and replay from a fresh process are verified.

No fixture time counts toward 72 hours. A flat `MISSED` remains canonical and
is never backfilled. It does not permanently fail the project, but it closes the
current healthy segment as `INTERRUPTED_RECOVERABLE`. A short service/network
interruption while flat has the same effect. After reconciliation, a new
healthy segment begins at the next naturally scheduled production-qualified
`OBSERVED` opportunity. Earlier segments and their exact duration remain
visible but do not contribute seconds to the new segment. This restarts the
72-hour continuity requirement without failing the whole qualification block.
Time with untrusted clock, missing service health or unresolved evidence never
counts. Thus “extend” means the real eligible date moves later; it never means
adding disconnected healthy intervals together.

If the system was exposed during a missed opportunity or could not safely
manage an existing position, it must first reject new risk and flatten through
the safest reconciled path. The qualification/stage block ends failed. After an
immutable incident record is accepted through a separate incident-unlock
approval, a new block may start; the old block and missed event remain visible.

No automatic restart may erase elapsed failure, select a better block for the
90-day evaluator or change the economic start.

## 8. Operational ceremony state machine

After `SIM_72H_QUALIFIED`, four separate external approvals are still required:
credential provisioning, funding boundary, ceremony activation and exact order
limits. The ceremony then uses the venue's verified minimum permissible amount
and the fixed label:

```text
OPERATIONAL_CEREMONY_NOT_STRATEGY_EVIDENCE
```

State order is:

```text
CEREMONY_READY_FLAT
  -> SPOT_BUY_SUBMITTED
  -> SPOT_LONG_RECONCILED
  -> SPOT_SELL_SUBMITTED
  -> FLAT_RECONCILED_AFTER_SPOT
  -> PERP_SHORT_SUBMITTED
  -> PERP_SHORT_AND_PROTECTIVE_STOP_CONFIRMED
  -> PERP_CLOSE_REDUCE_ONLY_SUBMITTED
  -> FLAT_RECONCILED_AFTER_PERP
  -> CEREMONY_QUALIFIED
```

Every transition requires stable client order identity, venue query, fills,
fees, local ledger and position reconciliation. The perpetual leg must verify
one-way mode, isolated margin, leverage not above 2×, protective stop validity
while exposed and reduce-only closure. Spot and perpetual exposure remain
mutually exclusive.

Ceremony events are retained for operational audit but excluded by schema from
DecisionOpportunity strategy cycles, 72-hour simulated performance, 90-day
economic returns and E0/E1/E2 strategy-cycle counts. A failure cannot be hidden
by rerunning: the block closes with its true result, the account is flattened
when safely possible, and a new ceremony requires incident acceptance and a new
explicit approval.

## 9. Hard stops and recoverable conditions

The only four absolute stage-block hard stops are:

1. an unresolved economic order `UNKNOWN`;
2. venue and authoritative local position disagreement;
3. perpetual exposure without a valid, confirmed protective stop; and
4. an attempt to add risk after the applicable stage loss limit has fired.

Each hard stop rejects new risk, requires reconciliation and safe flattening,
and permanently fails the current block. It does not erase history or
permanently abandon the whole project. A later block requires an immutable
incident report, proof of flatness and a separately approved incident unlock.

Duplicate economic order, unrecorded/conflicting fill and evidence-integrity
failure map into the first two hard-stop classes according to the unresolved
order/position they create; they are never downgraded to warnings.

The following are recoverable only while no unsafe exposure or unresolved
economic state exists: short network interruption, flat missed opportunity,
insufficient sample, incomplete product coverage and negative short-window
return. They are recorded and extend qualification or stage duration. They do
not authorize guessing account state, backfill, automatic promotion or an
economic claim.

## 10. E0/E1/E2 state and limits

E0 still requires a separate exact activation approval after ceremony success.
The ladder remains:

| Stage | Capital limit | Gross exposure limit | Minimum wall time | Minimum natural strategy cycles |
|---|---:|---:|---:|---:|
| E0 | 100 USDT | 0.5× / 50 USDT | 7 days | 3 |
| E1 | 300 USDT | 1× | 14 days | 5 |
| E2 | 1000 USDT | 2× hard cap | 30 days | 10 |

Each stage requires at least one natural Spot complete cycle and one natural
perpetual complete cycle. Ceremony cycles do not count. Promotion is never
automatic and requires a new exact activation artifact and approval.

Risk limits preserve v0.69:

- E0 and E1: net daily loss of 2 USDT stops new risk until the next UTC day;
  high-water drawdown of 5 USDT flattens and fails the current stage block;
- E2: net daily loss of 2% of stage capital stops new risk until the next UTC
  day; high-water drawdown of 7.5% flattens and fails the current stage block.

Loss includes realized and unrealized PnL, fees and funding using conservative
marks. A daily stop cannot be bypassed by changing product, restarting the
process or opening a new block. A drawdown failure ends the current stage; a
future retry is a new, explicitly approved block and does not count the failed
block's duration or cycles toward promotion.

## 11. Binance and credential boundary

Only Binance ETHUSDT Spot long and ETHUSDT USDⓈ-M perpetual short are in scope.
Gate.io remains out of scope. The private adapter must prove with fixtures and
protocol mocks before code-complete:

- canonical request signing and clock-skew rejection;
- owner-only, repository-external credential capability with no value logging;
- withdrawal disabled, exact IP allowlist and least required read/trade
  permissions;
- Spot unmarginated long only;
- perpetual one-way, isolated and configured no higher than 2×;
- stable client order IDs and query-before-retry semantics;
- ACK, reject, partial fill, cancel, late fill and UNKNOWN handling;
- reduce-only closure and protective-stop create/replace/reconcile;
- fee, funding, balance, order, fill and position reads; and
- three-way venue/fill-stream/local-ledger reconciliation.

Mocks never qualify a real account. The released code must default to no secret,
no account access and no order authority.

## 12. Verification and delivery discipline

Every behavior change follows exact RED, minimal GREEN and refactor. Each
release receives one independent full review and targeted re-review after fixes.
The final unchanged code state receives one local full suite, compile checks and
release validation; duplicate full runs without code change are forbidden.
Supported PR CI, merged-main CI and annotated-tag identity remain release gates.

The fault matrix must include at least: process kill at durable boundaries,
fresh-process replay, network loss before/after send, timestamp drift, duplicate
request, ACK loss, partial fill, late fill, cancel race, UNKNOWN resolution,
protective-stop loss/replace, stream/REST disagreement, fee/funding replay,
position mismatch, daily loss, drawdown, disk/fsync failure and read-only UI
source failure.

No implementation may broaden this plan without a new written spec. General
trading-engine, generic exchange, generic broker, generic scheduler or generic
control-UI expansion remains out of scope.

## 13. Earliest E0 estimate

If code-complete occurs between 2026-09-04 and 2026-09-08, the mathematical
earliest E0 is approximately 2026-09-07 through 2026-09-11, plus the time needed
for explicit approvals, install/preflight, any recoverable extension and the
operational ceremony. This is not a promised activation date.

No E0 clock can start before all of these are true:

1. v0.75–v0.77 are released and identity-verified;
2. installation/start has separate approval and preflight passes;
3. the real 72-hour qualification passes;
4. credentials, funding and ceremony have separate approvals;
5. the ceremony ends flat and reconciled; and
6. E0 activation has its own exact approval.

## 14. Irreversible approval ledger

The following actions remain separately user-authorized. Design approval,
source-code release or a previous general approval does not execute them:

1. install the production-like simulation service and write its owner-only root;
2. bootstrap/start the service and create start receipts;
3. create/read a real Binance API key and verify account permissions;
4. fund or transfer the exact ceremony/E0 capital;
5. activate and submit the Spot ceremony orders;
6. activate and submit the perpetual ceremony orders;
7. activate E0;
8. promote separately to E1 and E2;
9. unlock any failed qualification, ceremony or stage block after incident
   review; and
10. any future Gate.io, higher leverage, larger capital, withdrawal permission
    or production-scope expansion.

Approvals must bind exact released build, configuration, account, capital,
expiry and risk limits. They cannot be inferred from chat shorthand.

## 15. Falsifiable acceptance criteria for v0.75

The later plan-only implementation is acceptable only if:

1. v0.69, v0.73 and v0.74 released bytes and identities remain unchanged;
2. a strict schema, parameterless builder and loader encode this exact
   supersession and reject unknown fields or caller-supplied policy values;
3. the supersession record says explicitly that only operational eligibility
   and recovery changed, while v0.74 economic authority remains unchanged;
4. all authority flags and request/write counters remain false or zero;
5. the formal artifact contains no outcome, PnL, account, credential, order,
   fill or runtime evidence;
6. tests prove ceremony events cannot enter strategy/economic cycle counts;
7. tests prove a new operational block cannot erase an old failure or alter the
   economic start/window;
8. tests prove the four hard-stop classes fail the current block and that only
   an explicit incident-unlock binding permits a later block;
9. focused, adjacent and final validation plus independent review have no open
   Critical or Important finding; and
10. no statement claims profitability, AI advantage, Paper completion, Canary
    activation or live-trading qualification.

Until this exact design is approved and implemented as a released plan-only
artifact, v0.69/v0.73/v0.74 remain the active authority.
