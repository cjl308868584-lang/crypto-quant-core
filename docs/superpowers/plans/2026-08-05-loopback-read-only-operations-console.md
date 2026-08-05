# Loopback-Only Read-Only Operations Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic alert projection, four-route loopback-only read-only Web console, and exact operator runbooks on top of the strict v0.60 operations projection.

**Architecture:** `operations_alerts.py` is the only component that turns canonical v0.60 projection bytes into alerts and canonical dashboard status bytes. `operations_dashboard.py` injects a bytes provider into a standard-library HTTP server, serves packaged static assets, and has no operational discovery or mutation capabilities. Human procedures remain separate Markdown runbooks, and the release does not install or start anything.

**Tech Stack:** Python 3.9+ standard library, existing `jsonschema>=4.25,<5`, `http.server.ThreadingHTTPServer`, static HTML/CSS/JavaScript, `unittest`, GitHub Actions.

## Global Constraints

- Release base is private `cjl308868584-lang/crypto-quant-core` `origin/main` and annotated `v0.60.0`, both peeled to `7cb3dc47984581e2c5873d7ece8417b137168303`.
- Freeze `docs/superpowers/specs/2026-08-05-loopback-read-only-operations-console-design.md` without widening its capabilities.
- Web binds exactly `127.0.0.1`, exposes only four GET routes, emits no CORS, accepts no request body, and provides no write API, operation button, WebSocket, external asset, or polling loop.
- Projection input must pass `load_operations_projection_bytes`; errors collapse to fixed non-secret reason codes.
- Alerts may inspect only the existing v0.60 allowlisted projection and may not send external messages or control execution.
- Challenger economics remain structurally absent before and after the confirmatory tail; do not add any PnL, return, win-rate, price, fee, rank, interval, power, or early-PASS field.
- System Paper stays `PLAN_FROZEN_PAPER_NOT_STARTED`; do not install/start services or call Runner, scheduler, maintenance, market network, Broker, orders, credentials, balance, or production state.
- Use TDD for every behavior: observe the intended red failure before adding production code.
- Run the full local suite exactly once for the final code state. Use one complete independent review and only targeted re-review after fixes. Retain PR Python 3.9/3.12 CI, main CI, and annotated tag identity verification.

---

## File structure

- `src/crypto_quant/operations_alerts.py`: strict projection replay, deterministic alert records, risk observation, canonical status body.
- `src/crypto_quant/operations_dashboard.py`: provider adapter, loopback server, route/method/Host/path/security handling, CLI.
- `src/crypto_quant/dashboard/index.html`: static accessible four-region shell.
- `src/crypto_quant/dashboard/app.js`: one-shot same-origin fetch and `textContent` rendering.
- `src/crypto_quant/dashboard/styles.css`: local responsive status styling.
- `tests/test_operations_alerts.py`: alert condition, ordering, risk, validation, and determinism tests.
- `tests/test_operations_dashboard.py`: real loopback HTTP, route, method, Host, failure, asset, CLI, and import-boundary tests.
- `tests/fixtures/operations-projection-healthy.json`: canonical strict-loader fixture for local smoke.
- `docs/runbooks/system-paper-operations.md`: future authorized operation and failure-evidence procedure.
- `docs/runbooks/operations-dashboard.md`: exact local console procedure and exposure boundary.
- `docs/adr/0061-loopback-read-only-operations-console.md`: accepted decision and consequences.
- `docs/implementation-status-v0.61.0.md`: exact delivered and not-delivered state.
- `pyproject.toml`, `setup.py`, `src/crypto_quant/__init__.py`, `src/crypto_quant_core.egg-info/PKG-INFO`: package/script/resource/version identity.
- `src/crypto_quant/build.py`, `scripts/refresh_evaluator_build_manifest.py`, `config/evaluator-build-manifest-v1.json`: v0.61 build identity.

---

### Task 1: Deterministic alert and status bytes boundary

**Files:**
- Create: `tests/test_operations_alerts.py`
- Create: `src/crypto_quant/operations_alerts.py`
- Reference: `src/crypto_quant/operations_projection.py`

**Interfaces:**
- Consumes: `load_operations_projection_bytes(body: bytes) -> Mapping[str, Any]`.
- Produces: `derive_operations_alerts(projection_body: bytes) -> Mapping[str, Any]`; `build_operations_status_body(projection_body: bytes) -> bytes`.

- [ ] **Step 1: Write the strict input and healthy-state tests**

Create a canonical projection fixture in the test with literal source values and assert:

```python
alerts = derive_operations_alerts(canonical_json(projection).encode("utf-8"))
self.assertEqual(alerts["schema_version"], "1.0.0")
self.assertEqual(alerts["status"], "HEALTHY")
self.assertTrue(alerts["new_risk_allowed"])
self.assertEqual(alerts["counts"], {"INFO": 0, "WARNING": 0, "CRITICAL": 0})
self.assertEqual(alerts["alerts"], [])
```

Also assert noncanonical bytes, duplicate keys, a mismatched hash, a float, an unknown field, and a mapping instead of bytes raise `OperationsAlertsError` with only `OPERATIONS_ALERTS_PROJECTION_INVALID`.

- [ ] **Step 2: Run the new tests and verify the missing-module red failure**

Run: `PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_operations_alerts -v`

Expected: `ModuleNotFoundError: No module named 'crypto_quant.operations_alerts'`.

- [ ] **Step 3: Implement minimal strict replay and empty alert output**

Implement:

```python
class OperationsAlertsError(ValueError):
    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def derive_operations_alerts(projection_body: bytes) -> Mapping[str, Any]:
    try:
        projection = load_operations_projection_bytes(projection_body)
    except Exception as error:
        raise OperationsAlertsError(
            "OPERATIONS_ALERTS_PROJECTION_INVALID"
        ) from error
    return _derive_verified_operations_alerts(projection)
```

Use a fresh literal dict for counts and alerts. Do not return or retain mutable input objects.

- [ ] **Step 4: Run the focused tests and verify green**

Run: `PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_operations_alerts -v`

Expected: the strict-input and healthy-state tests pass.

- [ ] **Step 5: Add one failing table-driven alert-classification test**

Use independent literal expected records for these mutations:

```text
overall FAILED_CLOSED                    -> SYSTEM/CRITICAL/BLOCK_NEW_RISK
Challenger service FAILED_CLOSED         -> CHALLENGER/CRITICAL/BLOCK_NEW_RISK
Challenger evidence FAILED_CLOSED        -> CHALLENGER/CRITICAL/BLOCK_NEW_RISK
Challenger service DEGRADED              -> CHALLENGER/WARNING/NO_CHANGE
Challenger freshness/evidence STALE      -> CHALLENGER/WARNING/NO_CHANGE
Challenger incident                      -> CHALLENGER/WARNING/NO_CHANGE
Paper service FAILED_CLOSED              -> SYSTEM_PAPER/CRITICAL/BLOCK_NEW_RISK
Paper evidence FAILED_CLOSED             -> SYSTEM_PAPER/CRITICAL/BLOCK_NEW_RISK
Paper reconciliation FAILED_CLOSED       -> SYSTEM_PAPER/CRITICAL/BLOCK_NEW_RISK
Paper timeout_unknown_order_count > 0    -> SYSTEM_PAPER/CRITICAL/BLOCK_NEW_RISK
Paper risk HALT or HARD_BOUNDARY          -> SYSTEM_PAPER/CRITICAL/BLOCK_NEW_RISK
Paper service DEGRADED                    -> SYSTEM_PAPER/WARNING/BLOCK_NEW_RISK
Paper freshness/evidence STALE            -> SYSTEM_PAPER/WARNING/BLOCK_NEW_RISK
Paper incident                            -> SYSTEM_PAPER/WARNING/BLOCK_NEW_RISK
Paper risk WARNING or REDUCE              -> SYSTEM_PAPER/WARNING/BLOCK_NEW_RISK
```

Assert exact stable IDs, severities, streams, reason codes, risk effects, fixed ordering, no duplicate alert for the two stale representations, exact counts, and byte-identical repeated status bodies.

- [ ] **Step 6: Run the classification test and verify the intended red failure**

Run: `PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_operations_alerts -v`

Expected: literal alert records are absent from the minimal implementation.

- [ ] **Step 7: Implement field-by-field conditions and risk closure**

Add a private `_alert(...)` constructor and a fixed sequence of condition checks. Compute `new_risk_allowed` as true only for Paper `COLLECTING`, `RECONCILED`, `NORMAL`, no Paper/system critical alert, Paper evidence/service `HEALTHY`/`VERIFIED`, Paper provenance `FRESH`, and zero Paper incidents/UNKNOWN orders. Challenger-only warnings do not alter it; overall `FAILED_CLOSED` does.

Implement status bytes as:

```python
def build_operations_status_body(projection_body: bytes) -> bytes:
    projection = _load_projection(projection_body)
    value = {
        "schema_version": "1.0.0",
        "projection": projection,
        "alert_summary": _derive_verified_operations_alerts(projection),
    }
    return canonical_json(value).encode("utf-8")
```

- [ ] **Step 8: Run focused and adjacent projection tests**

Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_operations_alerts tests.test_operations_projection -v
```

Expected: all pass with no filesystem, subprocess, socket, or network fixture.

- [ ] **Step 9: Commit the independently testable alert boundary**

```bash
git add tests/test_operations_alerts.py src/crypto_quant/operations_alerts.py
git commit -m "feat: derive deterministic operations alerts"
```

### Task 2: Loopback HTTP security boundary

**Files:**
- Create: `tests/test_operations_dashboard.py`
- Create: `src/crypto_quant/operations_dashboard.py`
- Consume: `src/crypto_quant/operations_alerts.py`

**Interfaces:**
- Consumes: `Callable[[], bytes]`, `build_operations_status_body(bytes) -> bytes`.
- Produces: `create_operations_server(projection_provider, *, host="127.0.0.1", port=8765) -> ThreadingHTTPServer`; `main(argv=None) -> int`.

- [ ] **Step 1: Write failing bind/provider/API tests**

Assert that `localhost`, `::1`, `0.0.0.0`, empty host, non-string host, booleans/floats/negative/out-of-range ports, and non-callable providers raise fixed `OperationsDashboardError` reason codes before any external bind. Use a real ephemeral loopback server for a valid provider and assert one `GET /api/v1/status` calls the provider exactly once, returns the literal canonical status body, uses `application/json; charset=utf-8`, and sends correct `Content-Length`.

- [ ] **Step 2: Run and observe the missing-module red failure**

Run: `PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_operations_dashboard -v`

Expected: missing `crypto_quant.operations_dashboard`.

- [ ] **Step 3: Implement the minimal server and API route**

Subclass `BaseHTTPRequestHandler`, attach the provider to a `ThreadingHTTPServer` subclass, set `daemon_threads=True`, and implement exact response bytes. Do not accept a server class or handler override from callers.

- [ ] **Step 4: Run API tests and verify green**

Run: `PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_operations_dashboard -v`

- [ ] **Step 5: Add failing method, Host, route, path, header, and failure tests**

With real `http.client.HTTPConnection`, assert:

- exact GET routes are `/`, `/app.js`, `/styles.css`, `/api/v1/status`;
- clean unknown GET is 404;
- queries, `%`, backslash, dot segments, and control-character request targets fail 400 without invoking the provider;
- missing/mismatched/`localhost`/external Host values fail 400;
- HEAD, POST, PUT, PATCH, DELETE, OPTIONS, CONNECT, and TRACE return 405, `Allow: GET`, and never invoke the provider;
- every response has the exact CSP, no-store, nosniff, DENY, no-referrer, and Permissions-Policy headers and has no `Access-Control-Allow-Origin` or cookie;
- provider exception, non-bytes result, invalid canonical projection, and secret-bearing exception all return the exact generic 503 JSON body without the secret or input;
- malformed requests cannot produce a Python traceback in the response.

- [ ] **Step 6: Run and observe failures for the unimplemented security branches**

Run: `PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_operations_dashboard -v`

Expected: at least the static routes, Host mismatch, non-GET method, and 503 redaction cases fail.

- [ ] **Step 7: Implement all fail-closed branches and headers**

Parse only the raw request target needed for exact route matching. Treat control characters, `%`, `\\`, query/fragment delimiters, and `.`/`..` segments as suspicious. Override `do_HEAD`, `do_POST`, `do_PUT`, `do_PATCH`, `do_DELETE`, `do_OPTIONS`, `do_CONNECT`, and `do_TRACE` to one 405 path. Override `log_message` to perform no output.

Set the fixed 503 body to canonical bytes equivalent to:

```json
{"error":"OPERATIONS_STATUS_UNAVAILABLE","new_risk_allowed":false}
```

- [ ] **Step 8: Run focused HTTP tests**

Run: `PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_operations_dashboard -v`

Expected: all server security tests pass using loopback only.

- [ ] **Step 9: Commit the HTTP boundary**

```bash
git add tests/test_operations_dashboard.py src/crypto_quant/operations_dashboard.py
git commit -m "feat: enforce loopback dashboard boundary"
```

### Task 3: Packaged read-only UI, CLI, and fixture

**Files:**
- Create: `src/crypto_quant/dashboard/index.html`
- Create: `src/crypto_quant/dashboard/app.js`
- Create: `src/crypto_quant/dashboard/styles.css`
- Create: `tests/fixtures/operations-projection-healthy.json`
- Modify: `tests/test_operations_dashboard.py`
- Modify: `pyproject.toml`
- Modify: `setup.py`

**Interfaces:**
- Consumes: four-route server and exact canonical projection file.
- Produces: packaged assets and `crypto-quant-operations-dashboard` CLI.

- [ ] **Step 1: Add failing real asset and CLI tests**

Assert the three static GETs return non-empty packaged bytes with exact media types. Assert the HTML provides `project-summary`, `challenger-timeline`, `paper-runtime`, and `risk-alerts`; contains no form, button, external URL, or economics field name. Assert JavaScript calls only `/api/v1/status`, creates nodes and uses `textContent`, contains no `innerHTML`, `outerHTML`, `document.write`, `WebSocket`, `setInterval`, `setTimeout`, or external URL. Assert the CLI parser has only `--projection-file` and `--port`, rejects a relative projection path, rejects any host option, and serves canonical fixture bytes through the strict loader.

- [ ] **Step 2: Run and verify missing-resource failures**

Run: `PYTHONPATH=src /usr/bin/python3 -m unittest tests.test_operations_dashboard -v`

Expected: static assets, fixture, and CLI assertions fail.

- [ ] **Step 3: Implement the accessible four-region shell**

Use plain semantic HTML with a fixed page title and status placeholders. Include only `styles.css` and deferred `app.js` from the same origin. Do not embed projection values in HTML.

- [ ] **Step 4: Implement one-shot DOM rendering**

On `DOMContentLoaded`, fetch `/api/v1/status` once with `cache: "no-store"`. Build definition lists and alert list items with `document.createElement`; set source-derived strings only through `textContent`. On a non-OK response or JSON error, render fixed `FAILED_CLOSED` text and `new_risk_allowed=false` without echoing the exception.

- [ ] **Step 5: Add responsive local CSS and package data**

Use system fonts, visible focus defaults, severity classes, and no remote imports. Extend package data to:

```toml
crypto_quant = [
  "schemas/*.json",
  "dashboard/*.html",
  "dashboard/*.js",
  "dashboard/*.css",
]
```

Register:

```toml
crypto-quant-operations-dashboard = "crypto_quant.operations_dashboard:main"
```

Mirror the package-data/script behavior in `setup.py` where needed by its existing compatibility surface.

- [ ] **Step 6: Create the exact healthy fixture from literals**

Use `build_operations_projection` only in a one-off controlled command to create a canonical fixture whose release is `v0.60.0`, Challenger is `REPLACEMENT_NOT_STARTED` with zero incidents, and System Paper is `COLLECTING`, fresh, reconciled, normal, and has internally consistent simulated lifecycle counts. Immediately replay the written bytes with `load_operations_projection_bytes` and record its SHA-256 in the commit message body or implementation status later.

- [ ] **Step 7: Run focused and adjacent tests plus a local socket smoke**

Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_operations_alerts tests.test_operations_dashboard \
  tests.test_operations_projection -v
```

Start the CLI on an ephemeral or selected free loopback port with the committed fixture, issue the four GET requests and one POST using `curl --noproxy '*'`, then terminate the server. Confirm no external listener exists and no response contains a prohibited economics key.

- [ ] **Step 8: Commit UI, fixture, and CLI**

```bash
git add src/crypto_quant/dashboard tests/fixtures/operations-projection-healthy.json \
  tests/test_operations_dashboard.py src/crypto_quant/operations_dashboard.py \
  pyproject.toml setup.py
git commit -m "feat: add read-only operations console"
```

### Task 4: Exact operator runbooks

**Files:**
- Create: `docs/runbooks/system-paper-operations.md`
- Create: `docs/runbooks/operations-dashboard.md`

**Interfaces:**
- Consumes: released v0.58 deployment/preflight/loaders, v0.59 evaluator, v0.60 projection, and v0.61 console.
- Produces: human-only fail-closed procedures; no executable automation.

- [ ] **Step 1: Write System Paper operations procedure**

Document these states in order: current `PLAN_FROZEN_PAPER_NOT_STARTED`; authorization prerequisites; owner/time/disk/restart/network preflight interpretation; install receipt verification; waiting for the first natural slot; start receipt verification; daily read-only continuity; incident capture; prohibited remediation; recovery acceptance; tail gate; single final evaluator execution; exact artifact preservation. Explicitly prohibit manual Runner/scheduler/maintenance, slot backfill, source substitution, threshold change, repeated evaluation for a better result, credentials, account access, Broker calls, and real orders.

- [ ] **Step 2: Write dashboard procedure**

Document an exact `git worktree`/tag identity check, projection strict replay, loopback CLI command, `curl --noproxy '*'` status check, interpretation of `HEALTHY`/`DEGRADED`/`FAILED_CLOSED`, generic 503 response, browser access, clean shutdown, and confirmation that stopping the console has no effect on evidence streams. Prohibit `0.0.0.0`, `localhost`, port forwarding, reverse proxies, tunnels, cloud hosting, authentication material, and editing runtime evidence.

- [ ] **Step 3: Self-review for unsafe ambiguity**

Read both documents end-to-end. Remove any command that could install, start, kickstart, write, backfill, retry a final evaluation, or contact an external endpoint in the current release. Replace vague language with a fixed gate, status, reason code, or exact read-only check.

- [ ] **Step 4: Commit runbooks**

```bash
git add docs/runbooks/system-paper-operations.md docs/runbooks/operations-dashboard.md
git commit -m "docs: add fail-closed operations runbooks"
```

### Task 5: v0.61 release identity and documentation

**Files:**
- Create: `docs/adr/0061-loopback-read-only-operations-console.md`
- Create: `docs/implementation-status-v0.61.0.md`
- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `setup.py`
- Modify: `src/crypto_quant/__init__.py`
- Modify: `src/crypto_quant_core.egg-info/PKG-INFO`
- Modify: `src/crypto_quant/build.py`
- Modify: `scripts/refresh_evaluator_build_manifest.py`
- Modify: `config/evaluator-build-manifest-v1.json`

**Interfaces:**
- Consumes: completed v0.61 code, assets, tests, fixture, and runbooks.
- Produces: package `0.61.0`, manifest `1.55.0`, and exact release status.

- [ ] **Step 1: Write ADR, status, and README delta**

Record selected architecture, HTTP and alert boundaries, code-only release state, actual local fixture SHA-256, absent production roots/service, and every remaining milestone. State explicitly that dashboard health is not evidence of profitability, AI advantage, Paper completion, Canary eligibility, or live-trading fitness.

- [ ] **Step 2: Bump all package identities**

Set `pyproject.toml`, `setup.py`, `src/crypto_quant/__init__.py`, and `PKG-INFO` to exactly `0.61.0`. Set the refresh script expected manifest version to `1.55.0` and package version to `0.61.0`.

- [ ] **Step 3: Extend deterministic build inputs**

Add both v0.61 Python modules automatically through the existing source glob. Explicitly include the three dashboard resources, both v0.61 tests, fixture, design, plan, runbooks, ADR, implementation status, and README in the frozen release path set. Do not remove historical inputs.

- [ ] **Step 4: Refresh and validate manifest**

Run:

```bash
PYTHONPATH=src /usr/bin/python3 scripts/refresh_evaluator_build_manifest.py
PYTHONPATH=src /usr/bin/python3 scripts/validate_evaluator_build.py
```

Expected: manifest `1.55.0`, package `0.61.0`, and a valid exact input tree.

- [ ] **Step 5: Run focused release tests and commit**

Run:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_operations_alerts tests.test_operations_dashboard \
  tests.test_operations_projection tests.test_release -v
```

Commit:

```bash
git add README.md pyproject.toml setup.py src/crypto_quant/__init__.py \
  src/crypto_quant_core.egg-info/PKG-INFO src/crypto_quant/build.py \
  scripts/refresh_evaluator_build_manifest.py config/evaluator-build-manifest-v1.json \
  docs/adr/0061-loopback-read-only-operations-console.md \
  docs/implementation-status-v0.61.0.md
git commit -m "release: bind read-only operations console v0.61.0"
```

### Task 6: Independent review, one final local verification, and GitHub release

**Files:**
- Modify only files required by evidence-backed review findings.

**Interfaces:**
- Consumes: final v0.61 branch and user verification policy.
- Produces: reviewed PR, green PR/main CI, annotated `v0.61.0` aligned to remote main.

- [ ] **Step 1: Run one independent complete review**

Review the full branch against `origin/main`, emphasizing Host/DNS-rebinding defense, method closure, projection strictness, status-body leakage, JavaScript injection, risk semantics, forbidden authority, fixture integrity, and package resources. Record actionable findings by severity.

- [ ] **Step 2: Resolve actionable findings with TDD and targeted re-review**

For every Critical/Important or valid correctness finding: add one red regression test, observe the expected failure, implement the smallest fix, and run focused tests. Request only a targeted re-review of changed code; do not repeat the complete branch review without code changes.

- [ ] **Step 3: Execute final local verification exactly once**

On the final code commit run, in order:

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -q
PYTHONPATH=src /usr/bin/python3 -m compileall -q src tests scripts
PYTHONPATH=src /usr/bin/python3 scripts/validate_evaluator_build.py
make validate
git diff --check
git status --short
```

Do not repeat the full suite on the same commit. Confirm focused/adjacent tests already covered fault branches and local socket behavior.

- [ ] **Step 4: Recheck production boundary read-only**

Confirm the System Paper root and plist are absent and `gui/501/local.crypto-quant.system-paper-v1` is not loaded. Do not install, bootstrap, kickstart, or create any receipt.

- [ ] **Step 5: Push and open a Draft PR**

Reverify private target repository, `origin`, remote main/tag identity, and ADMIN permission. Push `codex/v0.61-read-only-operations-console`, create a Draft PR containing design, scope, review, test, and safety evidence, and verify its exact head commit.

- [ ] **Step 6: Verify PR CI, merge, and verify main CI**

Wait for both Python 3.9 and 3.12 PR jobs. Mark ready and merge only when required checks pass. Verify the merge commit is exact `origin/main`, then wait for both main CI jobs. Do not rerun local full tests for the unchanged content.

- [ ] **Step 7: Create and verify annotated release tag**

Create annotated `v0.61.0` at the exact green main merge commit, push it, and verify the remote tag object is annotated and its peeled commit equals remote main. Do not move or recreate an existing tag.

- [ ] **Step 8: Update the existing daily automation in place**

Keep exactly one daily 08:25 automation and update its authority to exact v0.61 main/tag/CI evidence. Advance only to the next separately frozen project milestone; retain all safety and reduced-mechanical-verification rules.
