# v0.77 Binance Private Canary Budget Amendment Design

**Status:** approved direction; implementation-plan correction only  
**Date:** 2026-08-27  
**Measured checkpoint:** `baff255a2b7c5e71bd60edd6eb75634a977d0b4b`

## 1. Decision

This amendment supersedes only the numeric production-line budget in
`2026-08-27-binance-private-canary-bundle.md`. All behavioral, authority,
evidence, safety, testing, review and release requirements in the v0.77 design
remain unchanged.

The aggregate v0.77 production-code budget is 6,200 physical lines. This is a
hard ceiling, not a target. A smaller implementation is preferred whenever it
preserves the exact safety contract.

The Task 11 amendment is measured rather than prospective. The measured safety
candidate measures 2,088 controller/fault-runner lines and 6,088 aggregate
lines after adding real private-runtime recovery, protected-stop, isolated
fresh-process, secret-surface, actual-boundary-input, seven-class authority and
truthful semantic-replay evidence. The ceiling retains 112 lines of headroom.
Only the controller/fault-runner group receives additional
capacity; all other component ceilings remain unchanged.

## 2. Why the original 3,000-line ceiling is not executable

At the measured checkpoint, the reviewed implementation has no Canary
controller, fault runner or delivery integration yet, but its required safety
boundaries already occupy 3,486 physical lines:

| Boundary | Physical lines |
|---|---:|
| protocol + fixed-host transport | 529 |
| owner-only credential capability | 220 |
| strict account preflight | 343 |
| private event contract + opportunity projection | 626 |
| order lifecycle + reconciliation + append-only runtime | 1,768 |
| **Total** | **3,486** |

The inventory was produced with `Path.read_text(encoding="utf-8").splitlines()`
over the exact files named below. It excludes schemas, fixtures, tests and
documentation.

The v0.72 lifecycle cannot replace these boundaries: it is intentionally bound
to `*_FIXTURE` events, simulated snapshots and a fixture build identity. Using
it as the Binance private fact source would merge simulated and venue facts.
Removing credential, query-first recovery, raw venue validation, protective
stop or three-way reconciliation code would weaken the approved contract.

## 3. Exact accounting contract

The following new Python files are counted in full:

- `challenger_replacement_binance_private_contract.py`
- `challenger_replacement_binance_private_protocol.py`
- `challenger_replacement_binance_credential.py`
- `challenger_replacement_binance_private_transport.py`
- `challenger_replacement_binance_preflight.py`
- `challenger_replacement_binance_private_lifecycle.py`
- `challenger_replacement_binance_reconciliation.py`
- `challenger_replacement_binance_private_runtime.py`
- `challenger_replacement_canary_controller.py`, when present
- `challenger_replacement_private_fault_matrix.py`, when present

Physical lines are `len(path.read_text(encoding="utf-8").splitlines())`.
Generated files are forbidden in this set. Renaming or moving logic does not
remove it from the count.

Changes to the pre-existing opportunity projection, operations projection,
alerts and dashboard are measured as added physical lines relative to the exact
v0.76 build-input tree
`4d8e9acf8e68c037c8ad274d970bfe67c71d4766`. The v0.77 release gate also
requires the released v0.76 peeled commit to resolve to that tree identity. The
final aggregate is:

```text
full lines of the listed new Python files
+ added production lines in the fixed pre-existing-file allowlist
<= 6,200
```

The fixed pre-existing-file allowlist is:

- `src/crypto_quant/challenger_replacement_opportunity_projection.py`
- `src/crypto_quant/operations_projection_v3.py`
- `src/crypto_quant/operations_alerts.py`
- `src/crypto_quant/dashboard/app.js`

Deleted lines do not create budget credit. Binary or unparseable diff entries
fail closed. Schemas, fixtures, tests, configuration examples and documentation
are not production-line budget inputs, but remain subject to review, package
and release gates.

## 4. Component ceilings

- protocol + transport: at most 600 lines;
- credential capability: at most 220 lines;
- preflight: at most 380 lines;
- private event contract + opportunity-projection additions: at most 650 lines;
- lifecycle + reconciliation + runtime: at most 2,100 lines;
- Canary controller + fixed fault runner: at most 2,200 lines;
- operations and dashboard delivery additions: at most 150 lines; and
- aggregate under section 3: at most 6,200 lines.

Passing the numeric caps is insufficient. Review must still reject generic
exchange, Broker, storage, scheduler or UI frameworks, arbitrary endpoints,
production fault seams, duplicated mutable facts, hidden retries or compressed
formatting used only to game the metric.

## 5. Required executable gates

The architecture test must fail on the pre-amendment 3,000 limit, then pass
only after it encodes the exact file inventory and section 4 ceilings. It must
also prove every named existing file is counted exactly once.

The release test must bind the exact v0.76 released peeled commit and calculate
the delivery additions from that immutable base. Missing tag/commit identity,
an unallowlisted modified production delivery file, a missing counted file, or
any cap violation fails closed.

Static review additionally checks:

- no generic URL, host, product, symbol or Broker injection surface;
- no secret, signature, API key, account response or credential path in durable
  diagnostics;
- no production fault callback, environment switch or command seam;
- no write route or trading control in the read-only operations console; and
- release-time network, mutation, order, fund and production-state counters are
  all zero.

## 6. Non-effects

This amendment does not authorize installation, service start, Binance contact,
credential creation or reading, account inspection, funding, ceremony orders,
E0/E1/E2 activation, Canary promotion or incident unlock. It does not start the
72-hour or 90-day clock and does not support a profitability or AI-advantage
claim.

It also does not change any v0.75 or v0.76 artifact, hash, decision policy,
economic plan, event authority or released identity.

## 7. Acceptance

The amendment is satisfied only when:

1. the original plan cites this document and contains no conflicting 3,000-line
   requirement;
2. the architecture budget test is committed and green;
3. every component and aggregate cap is enforced mechanically;
4. all existing focused behavior tests remain green;
5. independent review finds no Critical or Important safety regression; and
6. the final dossier reports measured lines and explicitly retains
   `CODE_COMPLETE_NOT_ACTIVATED`.
