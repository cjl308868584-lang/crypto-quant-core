# V1 Code Complete — Not Activated Dossier

结论：`CODE_COMPLETE_NOT_ACTIVATED`

本档案把 v0.75、v0.76、v0.77 的冻结要求映射到代码、测试和不可变
证据。它证明软件与模拟安全证据达到候选发布门，不证明盈利、AI 优势、
实盘可用性或真实交易质量。

## Release identity

- v0.76 predecessor main merge commit:
  `8ebcb07ab2c1ffe2b5f78e19626bfbdaba131867`；
- v0.76 predecessor main CI run `33132350975`：Python 3.9、Python 3.12、
  macOS arm64 全部成功；
- annotated `v0.76.0` tag object：
  `62d3611eb5c7b1bf197bc0f03d5d3871eaa23aff`，peeled commit 精确为
  `8ebcb07ab2c1ffe2b5f78e19626bfbdaba131867`；
- v0.77 executable checkpoint:
  `bd8cb5dd43c469cb28bcfd0fe75d8d997625c1e7`；
- v0.77 executable tree:
  `5fe797538ca3bd27ded323d6e5483685fb00caa9`；
- exact fault receipt:
  `artifacts/challenger-replacement/challenger-replacement-private-fault-matrix-v0.77.0.json`；
- receipt SHA-256:
  `0223b124515dc4b1ce688e2681b31cc3f596be0575a09c91641584aaf8eba4f9`；
- build manifest: `config/evaluator-build-manifest-v1.json`，最终版本
  `1.71.0`，package `0.77.0`。

## Canonical requirements map

| Requirement | Implementation | Executable evidence |
|---|---|---|
| v0.75 ceremony and E0/E1/E2 limits | `src/crypto_quant/challenger_replacement_canary_controller.py` | `tests/test_challenger_replacement_canary_controller.py` |
| v0.75 four hard stops and no automatic promotion | Canary controller plus strict private projection | controller and private-runtime tests |
| v0.76 public-market simulation and 72-hour qualification | released v0.76 public runtime, deployment and qualification modules | v0.76 release/fault tests and frozen v0.76 receipt |
| v0.76 independent 90-day evaluator | released economic evaluator and strict loader | v0.76 economic evaluation tests |
| closed Binance endpoint/signing contract | private contract and protocol modules | private contract/protocol tests and known-answer fixtures |
| repository-external credential capability | credential module; no secret-bearing template | credential and secret-surface fault tests |
| server-time and account preflight authority | protocol/preflight capability objects | preflight, protocol and fault tests |
| ACK/partial fill/cancel/UNKNOWN lifecycle | `src/crypto_quant/challenger_replacement_binance_private_runtime.py` | private runtime/lifecycle tests |
| query-before-retry and client-order-id idempotency | runtime plus fixed 36-character IDs | runtime/protocol/fault tests |
| perpetual stop and reduce-only safety | lifecycle/runtime protection state | protective-stop and fault tests |
| fee, funding, balance, position and ledger reconciliation | reconciliation module and canonical capture event | reconciliation/events tests |
| read-only console acceptance | operations v3 projection, alerts and existing loopback console | delivery/dashboard/alerts tests |
| immutable failure evidence | strict receipt loader and historical executable identity | `tests/test_challenger_replacement_private_fault_matrix.py` |
| package and release identity | package metadata, build inventory and manifest | `tests/test_challenger_replacement_v077_release.py` |

## Architecture and threat model

The architecture and threat model separate five authorities: canonical event
state, strict artifact loaders, private request construction, an explicit
short-lived activation capability and future operator approval. No imported
module, config file, UI route or caller-authored Boolean grants order authority.
The adapter fails closed on malformed or ambiguous exchange observations and
never treats a timeout as proof that an economic mutation did not occur.

The local same-UID adversary limitation remains explicit: owner-only files,
no-follow checks, inode/link/mode binding and hash chains detect boundary
violations and accidental inconsistency, but do not claim authenticity against
a continuously malicious process with the same OS UID. Stronger resistance
requires an independent UID/sandbox or secret-backed external anchor.

## Dependency, license and endpoint inventory

Runtime dependencies remain the Python standard library and
`jsonschema>=4.25,<5`; no Binance SDK, `requests`, `aiohttp`, `ccxt` or generic
broker was added. Existing project dependency/license records remain
authoritative. The exact 30 endpoint IDs are frozen in the private contract and
cover only Binance Spot and USDⓈ-M Futures server time, metadata, account,
orders/trades, income, position/configuration and the explicitly gated order,
algo-stop, leverage and isolated-margin mutations. Arbitrary hosts, paths,
methods and parameters are rejected.

## Fault, restart, reconciliation and secret-absence evidence

The single replacement campaign contains 59 primary cases plus an independent
semantic replay. It covers signature mutation, clock skew, DNS/TLS/redirect,
disconnect windows, UNKNOWN recovery, duplicate and conflicting economic
events, restart replay, mutual exclusion, Futures configuration, protective
stop gaps, reconciliation mismatches, loss gates, ceremony exclusion,
read-only UI loader failure and secret surfaces. Both seven-class authority
maps are zero. The receipt loader binds exact bytes, case hashes, semantic
hashes, build inventory and the historical executable checkpoint without
re-executing probes.

## Read-only console acceptance

The v0.61 loopback-only console remains the reused UI. v0.77 adds only
read-only Canary/private health fields through operations projection and
deterministic alerts. There is no credential form, order button, mutation API,
external asset or dependency of the core runtime on Web availability.

## Known limitations and residual risks

- No real Binance account, latency, rate-limit regime, fee tier, funding debit,
  liquidation path or real protective order has been observed.
- Frozen fixtures and mocks prove contract behavior, not exchange availability.
- Exchange API changes require a new documented compatibility/preflight review.
- The 72-hour operational qualification and independent 90-day economic study
  require real wall-clock evidence and cannot be compressed or backfilled.
- A PASS at either later gate does not prove durable profitability.
- The same-UID threat limitation described above remains.

## Remaining external actions

The following remain outside this code release: installation; start;
credential creation/read; IP/account binding; Futures configuration;
funding; Spot ceremony; Futures ceremony; E0 activation; E1 promotion;
E2 promotion; and incident unlock. Every action must bind the exact released
build, current account/configuration, limits, expiry and health evidence at the
time it is executed.

## Final invariant

`CODE_COMPLETE_NOT_ACTIVATED`

`production_activation=false`

`no service installed or started`

`no production root or start receipt created`

`no real or production Binance credential created or read`

`no private Binance request made`

`no real order submitted`

`no funds moved`

`no 72-hour or 90-day timer started`

`no profitability or AI-advantage conclusion`
