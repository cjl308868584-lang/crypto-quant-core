# ADR 0077: Binance private Canary bundle

## Status

Accepted for the local v0.77 release candidate. The only permitted conclusion
is `CODE_COMPLETE_NOT_ACTIVATED`. This ADR publishes code, fixtures, strict
loaders, disabled templates and offline fault evidence; it does not install or
start a service and grants no Binance or funding authority.

## Decision

The project retains the append-only replacement event log as the sole durable
authority. The Binance boundary is a closed adapter for `ETHUSDT` only: Spot
long and USDⓈ-M perpetual short are mutually exclusive; Futures is one-way,
isolated-margin and capped at 2×. Private intent, send boundary, response,
fill, fee, funding, position, balance, protective-stop and reconciliation facts
must be expressed by the fixed v0.77 schemas and replayed before a subsequent
mutation is considered.

The adapter uses the Python standard library plus the already frozen
`jsonschema>=4.25,<5` dependency. No Binance SDK, generic exchange library,
broker framework or generic UI was added. Thirty exact endpoint identities are
allowlisted by host, method, path, parameter set and mutation class. API keys
remain repository-external, owner-only, non-withdrawal and IP-allowlisted by
future ceremony contract; no credential exists in this release.

The E0/E1/E2 controller does not accept caller-authored progress, PnL, loss,
equity, ceremony or hard-stop claims. It derives them from strict activation,
canonical private events and exact reconciliation publications. Promotion is
never automatic. Unresolved UNKNOWN, venue/local position disagreement,
unprotected perpetual exposure and post-limit attempts to add risk remain the
four absolute hard-stop classes.

## Evidence identity

- v0.76 predecessor main merge commit:
  `8ebcb07ab2c1ffe2b5f78e19626bfbdaba131867`;
- v0.76 predecessor main CI run `33132350975`: success on Python 3.9,
  Python 3.12 and macOS arm64;
- annotated `v0.76.0` tag object:
  `62d3611eb5c7b1bf197bc0f03d5d3871eaa23aff`, peeled exactly to
  `8ebcb07ab2c1ffe2b5f78e19626bfbdaba131867`;
- reviewed v0.77 executable checkpoint:
  `bd8cb5dd43c469cb28bcfd0fe75d8d997625c1e7`;
- reviewed executable tree:
  `5fe797538ca3bd27ded323d6e5483685fb00caa9`;
- exact private fault receipt SHA-256:
  `0223b124515dc4b1ce688e2681b31cc3f596be0575a09c91641584aaf8eba4f9`;
- receipt ID:
  `challenger_replacement_private_fault_matrix_619910c14defa46d3f953254c414ef4aa47f1435c8552d79c43f9ccac26a8c32`;
- 59 primary cases and one independent semantic replay; both seven-class
  release-authority maps are all zero and `semantic_match=true`.

The receipt proves deterministic fixture conformance and failure behavior for
the reviewed bytes. It is not live-market, live-account, execution-quality or
profitability evidence. Receipt-only and release-metadata-only commits may
advance HEAD, while the loader still requires every current executable
inventory byte to equal the historical checkpoint blob.

## Operational boundary

`production_activation=false`

`no service installed or started`

`no production root or start receipt created`

`no real or production Binance credential created or read`

`no private Binance request made`

`no real order submitted`

`no funds moved`

`no 72-hour or 90-day timer started`

`no profitability or AI-advantage conclusion`

Installation, start, credential creation/read, IP/account binding, account
configuration, funding, Spot ceremony, Futures ceremony, E0, E1, E2 and
incident unlock remain external actions. Their later execution requires the
then-current exact build, configuration, account, limits, expiry and health
evidence; this release does not perform them.
