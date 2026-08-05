# v0.61 Loopback-Only Read-Only Operations Console Design

## 1. Status and authority

This document freezes the v0.61.0 design for the local read-only operations
console, deterministic alerts, and operator runbooks. Its only release base is:

- private repository: `cjl308868584-lang/crypto-quant-core`;
- `origin/main`: `7cb3dc47984581e2c5873d7ece8417b137168303`;
- annotated tag: `v0.60.0`;
- peeled tag commit: `7cb3dc47984581e2c5873d7ece8417b137168303`.

System Paper remains `PLAN_FROZEN_PAPER_NOT_STARTED`. This release is code,
static assets, tests, and documentation only. It does not install or start a
service and does not create runtime evidence.

## 2. Goal

Provide a small local console that lets an operator see the already allowlisted
v0.60 operational state without granting the presentation layer access to
SQLite, logs, LaunchAgents, strategy state, credentials, market endpoints, a
Broker, or orders. Derive stable local alert records from that same verified
projection and document exact fail-closed operating procedures.

The public boundaries are:

```python
derive_operations_alerts(projection_body: bytes) -> Mapping[str, Any]
build_operations_status_body(projection_body: bytes) -> bytes
create_operations_server(
    projection_provider: Callable[[], bytes],
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> ThreadingHTTPServer
```

The server exposes only:

```text
GET /
GET /app.js
GET /styles.css
GET /api/v1/status
```

## 3. Approaches considered

### 3.1 Selected: verified bytes, pure alerts, injected provider, stdlib HTTP

The alerts layer accepts canonical projection bytes and calls the v0.60 strict
loader before inspecting any field. The Web layer receives an injected
zero-argument bytes provider, calls it exactly once for each status request,
and builds a field-by-field response. Static assets ship as package resources.
The server uses only the Python standard library and binds exactly
`127.0.0.1`.

This preserves the narrowest trust boundary: the console cannot discover
operational roots or accidentally serialize a larger source artifact. It is
also independently testable and cannot become a prerequisite for Runner,
scheduler, maintenance, or evidence generation.

### 3.2 Rejected: Web server reads SQLite, logs, and receipts directly

Direct discovery would duplicate production-loader logic, widen filesystem and
process authority, couple UI availability to runtime state, and make it easy to
leak Challenger economics or private paths.

### 3.3 Rejected: external Web framework or hosted dashboard

A framework adds dependencies and middleware behavior without improving this
four-route service. Hosting introduces authentication, exposure, network, and
data-retention questions that are outside the local observation goal.

## 4. Scope

v0.61.0 includes:

- deterministic alerts derived only from a strict v0.60 projection replay;
- one canonical status response containing the exact verified projection, a
  fixed alert summary, and field-by-field alert records;
- a `ThreadingHTTPServer` bound only to `127.0.0.1`;
- packaged HTML, CSS, and JavaScript for four read-only views;
- an explicit projection-file CLI for local inspection and fixtures;
- fail-closed HTTP, Host, method, route, path, body, and header behavior;
- System Paper and dashboard runbooks;
- package/build-manifest/release documentation for v0.61.0.

It does not include:

- operational source discovery or direct reads of SQLite, logs, LaunchAgents,
  receipts, archives, evaluation roots, or environment variables;
- any POST, PUT, PATCH, DELETE, OPTIONS, TRACE, WebSocket, write API, action
  button, auto-refresh loop, email, SMS, Slack, webhook, or external network;
- authentication, cookies, sessions, analytics, telemetry, or a hosted mode;
- install, bootstrap, kickstart, Runner, scheduler, maintenance, Broker,
  credential, balance, order, or production-state capability;
- Challenger PnL, return, win rate, drawdown, price, fee, confidence interval,
  rank, power, or early PASS information;
- replacement Challenger design or execution.

## 5. Trust and data flow

```text
explicit projection bytes provider
              |
              v
load_operations_projection_bytes (v0.60 strict replay)
              |
              +--> deterministic allowlisted alerts
              |
              v
canonical status bytes
              |
              v
127.0.0.1-only four-route HTTP server
              |
              v
static DOM rendering with textContent
```

The provider is called once per `GET /api/v1/status`. Provider exceptions,
non-bytes values, malformed bytes, Schema failures, hash failures, or semantic
replay failures are collapsed to `OPERATIONS_STATUS_UNAVAILABLE`; exception
text and input bytes never enter an HTTP response. A successfully verified
projection returns HTTP 200 even when its operational status is `DEGRADED` or
`FAILED_CLOSED`, because the observation itself succeeded. Only an unavailable
or invalid observation returns HTTP 503.

The command-line adapter reads only the exact path passed with
`--projection-file`. It performs no path discovery and the strict loader makes
arbitrary file content ineligible for display. The server and alerts modules
do not import production Runner, scheduler, maintenance, installer, Broker,
SQLite, subprocess, or market-network modules.

## 6. Deterministic alert contract

`derive_operations_alerts` returns:

```json
{
  "schema_version": "1.0.0",
  "status": "HEALTHY",
  "new_risk_allowed": false,
  "counts": {"INFO": 0, "WARNING": 0, "CRITICAL": 0},
  "alerts": []
}
```

Every alert is assembled explicitly with exactly these fields:

- `alert_id`: one fixed identifier for one condition;
- `severity`: `INFO`, `WARNING`, or `CRITICAL`;
- `stream`: `CHALLENGER`, `SYSTEM_PAPER`, or `SYSTEM`;
- `reason_code`: a stable machine-readable code;
- `risk_effect`: `NO_CHANGE` or `BLOCK_NEW_RISK`.

Alerts use a fixed evaluation order, so repeated identical projection bytes
produce byte-identical output. The allowlisted conditions are:

- source freshness `STALE`;
- service `DEGRADED` or `FAILED_CLOSED`;
- evidence `INCIDENT_DETECTED` or `FAILED_CLOSED`;
- non-zero incident count;
- System Paper timeout/UNKNOWN orders;
- reconciliation `FAILED_CLOSED`;
- risk `WARNING`, `REDUCE`, `HALT`, or `HARD_BOUNDARY`;
- overall `FAILED_CLOSED`.

`CRITICAL` always has `risk_effect=BLOCK_NEW_RISK`. The summary boolean
`new_risk_allowed` is advisory and is true only while System Paper is
`COLLECTING`, reconciliation is `RECONCILED`, risk is `NORMAL`, the overall
projection is not failed closed, and there is no critical System Paper or
system alert. It is false for System Paper not-installed, not-started, final,
stale, warning/reduce, unknown-order, incident, or failed-closed states.
Challenger-only warnings do not change this independent Paper observation;
an overall `FAILED_CLOSED` state does. The boolean never grants installation,
start, production activation, Canary, or real-order authority.

## 7. HTTP contract and failure closure

The bind host must equal the literal `127.0.0.1`; aliases, hostnames, IPv6,
wildcards, and external interfaces are rejected before socket creation. Port
must be an integer from 0 through 65535, with 0 allowed only for ephemeral test
binding.

Requests must carry a Host header equal to `127.0.0.1` with the actual bound
port. No CORS header is emitted. Suspicious paths containing percent escapes,
backslashes, control characters, or dot segments return 400. Unknown clean GET
paths return 404. Every non-GET method returns 405 with `Allow: GET`, including
HEAD, POST, PUT, PATCH, DELETE, OPTIONS, CONNECT, and TRACE.

All responses set:

- `Content-Security-Policy: default-src 'self'; connect-src 'self'; img-src
  'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'`;
- `X-Content-Type-Options: nosniff`;
- `X-Frame-Options: DENY`;
- `Referrer-Policy: no-referrer`;
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`;
- `Cache-Control: no-store`.

The handler has no request body parser and disables default access logging. A
503 body contains only a fixed reason code and `new_risk_allowed=false`.

## 8. Read-only presentation

The HTML has stable regions `project-summary`, `challenger-timeline`,
`paper-runtime`, and `risk-alerts`. JavaScript performs one same-origin fetch
of `/api/v1/status` after document load. It creates nodes and assigns all
source-derived values through `textContent`; it never uses `innerHTML`,
`outerHTML`, `document.write`, dynamic script creation, or remote assets.

The page displays release identity, overall health, Challenger continuity,
System Paper phase and simulated lifecycle counts, reconciliation, risk, final
gate status, and alerts. It contains no PnL or other prohibited economics and
no controls capable of invoking an operation. Loader failure replaces the
status regions with a fixed failed-closed message.

## 9. Runbooks

`docs/runbooks/system-paper-operations.md` records the current not-started
state, future authorization gates, preflight interpretation, natural-start
observation, daily read-only checks, incident evidence capture, prohibited
remediation, recovery acceptance, and one-shot 90-day final evaluation. It
never instructs an operator to backfill, manually trigger a natural slot,
change thresholds, or retry for a better outcome.

`docs/runbooks/operations-dashboard.md` records exact fixture startup, local
health check, shutdown, stale/degraded/failed-closed interpretation, Host and
loopback boundaries, projection replacement behavior, and the prohibition on
public exposure. The dashboard remains optional and may be stopped without
affecting either evidence stream.

## 10. Verification and release

TDD covers alert rules, stable ordering and IDs, risk closure, provider call
count, strict loader enforcement, loopback binding, Host checks, all methods
and routes, path attacks, headers, media types, 503 redaction, packaged assets,
CLI behavior, and forbidden imports. A local socket smoke uses only
`127.0.0.1` and a committed canonical fixture.

For the final code state, run focused and adjacent tests, then exactly one local
full suite, `compileall`, build-manifest validation, and `make validate`. Obtain
one independent complete review; after any code fix, perform only targeted
re-review. Retain PR Python 3.9/3.12 CI, merged-main CI, and exact annotated tag
identity verification. Do not repeat the full local suite on an unchanged
commit.

Release as v0.61.0 only if all gates pass. The release does not authorize an
installation or start, does not prove Paper completion, profitability, an AI
advantage, Canary readiness, or live-trading fitness.
