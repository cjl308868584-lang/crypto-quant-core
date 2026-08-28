# Binance E0 Release-Blocker Hardening Design (v0.78.1)

Status: frozen local candidate. This patch does not install a service, read a
credential, contact an account, submit an order, or authorize capital.

## 1. Purpose and boundary

This patch closes the smallest Binance-only blockers between the already
published private contract and a separately approved E0 operational ceremony.
It is a patch on the v0.78 release line, not v0.79. Gate.io, strategy changes,
the replacement simulation snapshot, generic exchange abstractions and any UI
work are excluded.

The default authority remains zero. The runnable CLI is useful only with an
owner-only activation artifact, owner-only credential files and an explicit
subcommand. Tests use fixtures and fake transports only. No live endpoint is
called by release validation.

## 2. Venue JSON boundary

Binance response bytes are external evidence, not our canonical artifacts.
The boundary accepts 1..1 MiB UTF-8 JSON, rejects duplicate keys, floats,
invalid JSON and the wrong top-level type, but does not require source key
order or whitespace to equal `canonical_json`. After parsing, each supported
endpoint is normalized into one closed internal model.

Required keys are endpoint-specific. Documented optional keys are ignored by
the normalizer; identity and economic keys may not be absent or have the wrong
type. Spot Query Order and Account Trade List accept their official response
shapes, including Query Order's `time`, `updateTime`, `workingTime`,
`selfTradePreventionMode`, `origQuoteOrderQty` and optional conditional fields,
and myTrades' `isMaker`, `isBestMatch` and `isBuyer`. The normalized model keeps
only the fixed internal fields used by lifecycle and reconciliation.

## 3. Spot economics

Spot fees may be charged in BNB, ETH (base), or USDT (quote).
Every trade retains fee amount and asset. Reconciliation converts fees into
USDT using a fixed-query, capture-bound conversion price: USDT=1; ETH uses the
current ETHUSDT bid; BNB requires the current BNBUSDT ask in the captured venue
input. Any other asset or a missing conversion
fails closed; it is never treated as zero.

Spot signed quantity is the trusted ETH account balance. Wallet equity is
`USDT total + ETH total * trusted mark`; unrealized PnL is
`ETH position * (current bid - average entry)`. Available balance is free
USDT. The fixed public `bookTicker` query supplies the current ETHUSDT bid/ask;
the normalized pair is captured in the immutable reconciliation inputs and
must be positive and bound to ETHUSDT and the opportunity. This is exact
replay evidence, not a claim that a public response is cryptographically
authenticated beyond the fixed TLS endpoint and released query boundary.

The only permitted ancillary balance is an unlocked BNB fee reserve from zero
through `0.001 BNB`; locked BNB, a larger BNB balance, or any nonzero unlisted
asset fails preflight and the final capital snapshot. The reserve is not
strategy gross exposure, but its captured mark and full balance are included
in wallet/equity accounting. A BNB commission consumes that pre-existing
reserve and is converted to USDT exactly once.

## 4. Time and crash recovery

Each signed request gets a distinct durable server-time observation. A
timestamp is never borrowed from an earlier query, create, cancel, stop or
flatten action. The action records the server-time evidence identity before
the prepared signed request.

If a process crashes after preparing but before transport, a fresh process
first queries the deterministic client/order identity using fresh server-time
evidence. Only a proven-absent result permits superseding the unsent prepared
request with a new timestamp. SENT_STARTED or UNKNOWN is never superseded and
remains query-first. The old prepared record stays immutable and the
supersession event binds both identities.

This binding applies independently to the main economic order, protective-stop
create, emergency flatten and flat-position stop cleanup. Every prepared record
binds its own server-time response hash; a prepared-unsent replacement also
binds the old request id/hash/timestamp/time hash and the query that proved the
old deterministic venue identity absent. Stop-replacement cancellation binds
the fresh server-time evidence used for that one mutating request.

## 5. Protective stop and emergency flatten

A perpetual short may not return as managed exposure without a reconciled
reduce-only protective stop. If stop creation/query/reconciliation fails, the
runtime enters a separate `EMERGENCY_FLATTEN_AUTHORIZED` transition derived
from the already active activation, exact exposed position and fixed reason.
It builds a deterministic reduce-only BUY market close, uses a separate client
order id namespace, obtains fresh server time, queries first, sends at most
once per deterministic generation, and reconciles until flat or UNKNOWN. If a
terminal emergency order leaves a short remainder, a new durable generation
binds the previous order response, position response, quantity and client id
before the remainder can enter its own query-first path. It cannot open or
reverse a position. UNKNOWN remains a hard stop.

This is not a general manual flatten API: callers cannot provide product,
side, quantity, price, client id or reason.

## 6. Final send-boundary capital gate

Immediately before every mutating transport call, an independent pure guard
replays the activation and evaluates trusted current position, trusted
mark/ask, proposed quantity, side and reduce-only flag. Risk-increasing sends
must satisfy all of:

- `capital_usdt == 100`, `max_gross_exposure_usdt == 50`,
  `max_leverage == 0.5` for E0;
- post-order worst-case gross notional is at most 50 USDT;
- gross/capital is at most 0.5;
- Spot and perpetual exposure remain mutually exclusive;
- quantity is positive and already filter-valid.

Reduce-only exits may exceed the entry cap only up to the exact trusted
position and may not reverse. The guard runs after signing preparation and
again at the final send boundary; failure makes zero mutating requests. This
closes the current `quantity=1000` bypass.

## 7. Runnable local boundary

The patch provides three minimal parameterless/fixed-shape entrypoints:

1. account preflight: read fixed owner-only activation/config/credential paths,
   perform only the frozen permission/account/configuration queries, publish a
   redacted owner-only preflight receipt;
2. private runtime: consume one exact observed opportunity and its retained
   event root, replay preflight/activation/build identity, execute the existing
   query-first lifecycle with the final send guard;
3. emergency stop: query/reconcile only, block new risk, and invoke the fixed
   emergency flatten path only when an already exposed position requires it.

CLI arguments may select only one fixed operation and an already committed
opportunity id. No endpoint, URL, host, symbol, side, quantity, leverage,
timestamp, secret, output path or reason override is accepted. Runtime roots
and credential paths are fixed by the released contract. Logging is redacted.

## 8. Acceptance criteria

- Natural-order official Spot Query Order and myTrades samples normalize and
  reordered/extra documented fields do not fail.
- Duplicate keys, floats, missing economic identity and malformed types fail.
- BNB/base/quote fees convert through captured trusted marks; missing marks
  fail; Spot unrealized PnL changes with mark and replays exactly.
- Every signed action has a unique fresh time evidence binding; unsent recovery
  supersedes only after proven absence; UNKNOWN never resends.
- Stop failure executes only the fixed reduce-only emergency flatten state
  machine and never opens/reverses exposure.
- A 1000 ETH E0 entry is rejected at the final boundary with zero mutating
  request; 50 USDT gross boundary is inclusive; exits remain possible.
- CLI/static tests prove zero defaults, no secret output, no generic endpoint or
  order selectors and no network in the test suite.
- Focused, adjacent and one final full suite, compileall, `make validate`,
  diff-check and independent review pass before any release action.
