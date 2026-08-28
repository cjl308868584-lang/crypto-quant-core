"""Fixed credential-free v0.77 private-runtime fault evidence campaign."""
from copy import deepcopy
from collections.abc import Mapping
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import fields, is_dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import http.client
from importlib import resources
import io
import json
import os
from pathlib import Path
import ssl
import socket
import stat
import subprocess
import sys
import tempfile
from types import MappingProxyType, SimpleNamespace
import venv
from unittest.mock import patch

from jsonschema import Draft202012Validator
import jsonschema

from .canonical import canonical_json
from .challenger_replacement_accelerated_canary_plan import (
    build_challenger_replacement_accelerated_canary_plan,
)
from .challenger_replacement_binance_credential import (
    BinanceCredentialIdentity, open_binance_credential_capability,
)
from .challenger_replacement_binance_preflight import (
    evaluate_binance_account_preflight, open_binance_account_preflight_capability,
)
from .challenger_replacement_binance_private_contract import (
    BinanceAccountApproval, load_binance_private_activation_bytes,
)
from .challenger_replacement_binance_private_lifecycle import (
    apply_binance_order_observation, derive_binance_client_order_id,
    build_binance_order_intent_from_opportunity,
    prepare_binance_order_attempt, prepare_binance_protective_stop,
    reconcile_binance_protective_stop,
)
from .challenger_replacement_binance_private_protocol import (
    BinancePrivateRequest, build_binance_private_request,
    classify_binance_private_response, compute_binance_hmac_sha256,
    observe_binance_server_time, sign_binance_private_request,
    validate_binance_request_time,
)
from .challenger_replacement_binance_private_transport import (
    BinancePrivateTransportResult, execute_binance_private_request,
)
from . import challenger_replacement_binance_private_runtime as private_runtime
from .challenger_replacement_binance_reconciliation import (
    reconcile_binance_private_state,
)
from .challenger_replacement_canary_controller import (
    _project_challenger_replacement_canary,
)
from .challenger_replacement_events import (
    ChallengerReplacementEventRootIdentity, build_challenger_replacement_event,
    open_challenger_replacement_event_root, publish_challenger_replacement_event,
    replay_challenger_replacement_events,
)
from .challenger_replacement_fault_matrix import (
    load_challenger_replacement_fault_matrix_bytes,
)
from .challenger_replacement_economic_plan import (
    build_challenger_replacement_economic_plan,
)
from .challenger_replacement_evidence import (
    _strict_json_bytes as _strict_artifact_json_bytes,
)
from .challenger_replacement_plan import _strict_json_bytes
from .challenger_replacement_plan_v3 import load_challenger_replacement_plan_v3
from .challenger_replacement_opportunities import ChallengerReplacementOpportunityState
from .challenger_replacement_public_market_capture import (
    load_challenger_replacement_public_market_capture_bytes,
)
from .challenger_replacement_public_simulation_contract import (
    build_challenger_replacement_public_simulation_contract,
)
from .challenger_replacement_simulation_contract import (
    build_challenger_replacement_simulation_contract,
)
from . import challenger_replacement_v3_runtime as public_runtime
from .challenger_replacement_public_http import PublicHttpResponse
from .evidence import artifact_self_hash
CASE_IDS = (
    "SIGNATURE_KNOWN_ANSWER", "SIGNATURE_PARAMETER_ORDER_MUTATION",
    "SIGNATURE_PERCENT_ENCODING_MUTATION", "CLOCK_AHEAD", "CLOCK_BEHIND",
    "SERVER_TIME_EXPIRED", "SERVER_TIME_PRODUCT_DISAGREEMENT", "DNS_FAILURE",
    "TLS_FAILURE", "REDIRECT_REJECTED", "PROXY_ENV_IGNORED", "HOST_REJECTED",
    "PATH_REJECTED", "DISCONNECT_BEFORE_SEND", "DISCONNECT_DURING_SEND",
    "DISCONNECT_AFTER_SEND", "ACK_LOSS_QUERY_RECOVERY", "VENUE_MINUS_1007_UNKNOWN",
    "VENUE_5XX_UNKNOWN", "MALFORMED_2XX_UNKNOWN", "RATE_LIMIT_418",
    "RATE_LIMIT_429", "DUPLICATE_CLIENT_ID", "QUERY_BEFORE_RETRY",
    "PROVEN_ABSENT_ONLY_BEFORE_FIRST_SEND", "PARTIAL_FILL", "CANCEL_FILL_RACE",
    "LATE_FILL", "OVERFILL", "CONFLICTING_FILL", "DUPLICATE_FEE",
    "FEE_CORRECTION_CONFLICT", "DUPLICATE_FUNDING", "FUNDING_CORRECTION_CONFLICT",
    "SAME_BYTES_DIFFERENT_IDENTITY", "PRIVATE_FRESH_PROCESS_UNKNOWN_REPLAY",
    "PRIVATE_FRESH_PROCESS_STOP_REPLAY", "SPOT_PERPETUAL_MUTUAL_EXCLUSION",
    "WRONG_POSITION_MODE", "WRONG_MULTI_ASSET_MODE", "WRONG_MARGIN_TYPE",
    "LEVERAGE_ABOVE_TWO", "PARTIAL_SHORT_REQUIRES_STOP_BEFORE_RETURN",
    "STOP_REJECTED", "STOP_LOST", "STOP_CANCEL_RACE", "STOP_REPLACEMENT_NO_GAP",
    "STOP_QUERY_MISMATCH", "BALANCE_DISAGREEMENT", "POSITION_DISAGREEMENT",
    "ORDER_DISAGREEMENT", "LEDGER_DISAGREEMENT", "DAILY_STOP",
    "DRAWDOWN_FLATTEN", "RESTART_PRESERVES_STOP",
    "UTC_ROLLOVER_ONLY_RESETS_DAILY_GATE", "CEREMONY_EXCLUDED_FROM_ECONOMICS",
    "READ_ONLY_UI_LOADER_FAILURE", "SECRET_ABSENT_FROM_LOGS_EXCEPTIONS_EVENTS_ARTIFACTS",
)
_SCHEMA = "challenger-replacement-private-fault-receipt-v1.schema.json"
_ZERO = {name: 0 for name in (
    "credential_reads", "public_network_requests", "private_network_requests",
    "mutating_requests", "economic_orders", "fund_movement",
    "production_state_writes",
)}
_ACTIVITY = tuple("fixture_credential_reads fixture_transport_requests fixture_mutating_requests fixture_order_intents fixture_reconciliations fresh_processes".split())
_ACTIVE_LEDGER = None
_FIXTURE_AUTHORITY = object()
_BUILD = {
    "release_tag": "v0.77.0", "peeled_commit": "1" * 40,
    "package_version": "0.77.0", "manifest_version": "v0.77.0",
    "build_input_tree_hash": "2" * 64, "manifest_hash": "3" * 64,
    "manifest_file_sha256": "4" * 64,
}
_NOW = "2026-08-27T12:00:00.000Z"
_ROOT = Path(__file__).resolve().parents[2]
_V076_ARTIFACT_SHA256 = "98c900ca8cba6afb8c79c06be2487baa52ea6d2a113dbcffc5d9bb961bf96226"
_V076_RECEIPT_ID = "challenger_replacement_fault_matrix_receipt_84e312e68d6a59e7d8d2eeb8de08e215947cd021004eea65aea921b88ed763d3"
_V076_RECEIPT_HASH = "3bf68ea91394ef06b297575220810aa6773ba381787d0c63a5a96e565166b4f7"
EXECUTABLE_INVENTORY_PATHS = tuple(sorted({
    "src/crypto_quant/challenger_replacement_binance_credential.py",
    "src/crypto_quant/challenger_replacement_binance_preflight.py",
    "src/crypto_quant/challenger_replacement_binance_private_contract.py",
    "src/crypto_quant/challenger_replacement_binance_private_lifecycle.py",
    "src/crypto_quant/challenger_replacement_binance_private_protocol.py",
    "src/crypto_quant/challenger_replacement_binance_private_runtime.py",
    "src/crypto_quant/challenger_replacement_binance_private_transport.py",
    "src/crypto_quant/challenger_replacement_binance_reconciliation.py",
    "src/crypto_quant/challenger_replacement_canary_controller.py",
    "src/crypto_quant/challenger_replacement_events.py",
    "src/crypto_quant/challenger_replacement_opportunity_projection.py",
    "src/crypto_quant/challenger_replacement_private_fault_matrix.py",
    "src/crypto_quant/operations_alerts.py",
    "src/crypto_quant/operations_projection_v3.py",
    "src/crypto_quant/dashboard/app.js",
    "src/crypto_quant/schemas/challenger-replacement-binance-private-event-v1.schema.json",
    "src/crypto_quant/schemas/challenger-replacement-binance-account-approval-v1.schema.json",
    "src/crypto_quant/schemas/challenger-replacement-binance-account-preflight-v1.schema.json",
    "src/crypto_quant/schemas/challenger-replacement-binance-credential-reference-v1.schema.json",
    "src/crypto_quant/schemas/challenger-replacement-binance-private-activation-v1.schema.json",
    "src/crypto_quant/schemas/challenger-replacement-binance-private-request-v1.schema.json",
    "src/crypto_quant/schemas/challenger-replacement-binance-reconciliation-v1.schema.json",
    "src/crypto_quant/schemas/challenger-replacement-canary-authority-approval-v1.schema.json",
    "src/crypto_quant/schemas/challenger-replacement-canary-projection-v1.schema.json",
    "src/crypto_quant/schemas/challenger-replacement-private-fault-receipt-v1.schema.json",
    "src/crypto_quant/schemas/operations-projection-v3.schema.json",
    "src/crypto_quant/fixtures/challenger-replacement-v077/account-preflight-flat.json",
    "src/crypto_quant/fixtures/challenger-replacement-v077/futures-request-known-answers.json",
    "src/crypto_quant/fixtures/challenger-replacement-v077/private-order-observations.json",
    "src/crypto_quant/fixtures/challenger-replacement-v077/private-runtime-seeds-v1.json",
    "src/crypto_quant/fixtures/challenger-replacement-v077/spot-hmac-known-answer.json",
    "artifacts/challenger-replacement/challenger-replacement-plan-v0.69.0.json",
}))
class _ReleaseAuthorityGuard:
    __slots__ = ("_counts",)
    def __init__(self): self._counts = dict(_ZERO)
    def snapshot(self): return dict(self._counts)
    def block(self, name):
        if name not in _ZERO: raise RuntimeError("PRIVATE_FAULT_RELEASE_BOUNDARY_INVALID")
        self._counts[name] += 1
        raise RuntimeError("PRIVATE_FAULT_RELEASE_AUTHORITY_BLOCKED:" + name)
    def authorize_fixture(self, name, token):
        if token is not _FIXTURE_AUTHORITY: self.block(name)

class _BoundaryLedger:
    __slots__ = ("_guard", "_activity", "_inputs", "scratch_root")
    def __init__(self, scratch_root=None):
        self._guard = _ReleaseAuthorityGuard()
        self._activity = {key: 0 for key in _ACTIVITY}
        self._inputs = []
        self.scratch_root = None if scratch_root is None else Path(scratch_root)
    def snapshot(self): return self._guard.snapshot()
    def block(self, name): return self._guard.block(name)
    def activity(self): return dict(self._activity)
    def input_mark(self): return len(self._inputs)
    def inputs_since(self, mark): return deepcopy(self._inputs[mark:])
    def delta(self, before):
        current = self.snapshot()
        return {key: current[key] - before[key] for key in _ZERO}
    def activity_delta(self, before):
        return {key: self._activity[key] - before[key] for key in _ACTIVITY}
    def authorize_request(self, endpoint, token):
        if any(name in endpoint for name in ("WITHDRAW", "TRANSFER", "CAPITAL")):
            self._guard.block("fund_movement")
        self._guard.authorize_fixture("private_network_requests", token)
        if endpoint.endswith("CREATE"):
            self._guard.authorize_fixture("mutating_requests", token)
            self._guard.authorize_fixture("economic_orders", token)
def _observe(name):
    if _ACTIVE_LEDGER is None or name not in _ACTIVITY: raise RuntimeError("PRIVATE_FAULT_LEDGER_INACTIVE")
    for authority in {"fixture_credential_reads": ("credential_reads",)}.get(name, ()):
        _ACTIVE_LEDGER._guard.authorize_fixture(authority, _FIXTURE_AUTHORITY)
    _ACTIVE_LEDGER._activity[name] += 1
def _authorize_fixture(name):
    if _ACTIVE_LEDGER is None: raise RuntimeError("PRIVATE_FAULT_LEDGER_INACTIVE")
    _ACTIVE_LEDGER._guard.authorize_fixture(name, _FIXTURE_AUTHORITY)
def _observe_input(boundary, value):
    if _ACTIVE_LEDGER is None: raise RuntimeError("PRIVATE_FAULT_LEDGER_INACTIVE")
    _ACTIVE_LEDGER._inputs.append({"boundary": boundary, "input": deepcopy(value)})
def _safe_input(value):
    if isinstance(value, bytes):
        return {"bytes_utf8": value.decode(), "sha256": _digest(value), "size": len(value)}
    if is_dataclass(value):
        return {field.name: ({"opaque_authority_present":
                              getattr(value, field.name) is not None}
                             if field.name.startswith("_") else
                             _safe_input(getattr(value, field.name)))
                for field in fields(value)}
    if isinstance(value, Mapping): return {key: _safe_input(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)): return [_safe_input(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)): return value
    raise ValueError("PRIVATE_FAULT_INPUT_UNSUPPORTED")
def _call(boundary, function, *args, **kwargs):
    _observe_input(boundary, _safe_input({"args": args, "kwargs": kwargs}))
    return function(*args, **kwargs)
def _digest(value):
    return hashlib.sha256(value if isinstance(value, bytes)
                          else canonical_json(value).encode()).hexdigest()
def _error(call, reason):
    try:
        call()
    except Exception as error:  # direct fixed boundary, exact reason below
        if reason not in str(error):
            raise ValueError("PRIVATE_FAULT_PROBE_WRONG_FAILURE") from error
        return {"outcome": "REJECTED", "reason_code": reason}
    raise ValueError("PRIVATE_FAULT_PROBE_DID_NOT_FAIL")
def _request(mutating=True):
    endpoint = "SPOT_ORDER_CREATE" if mutating else "SPOT_ACCOUNT"
    parameters = ({"symbol": "ETHUSDT", "side": "BUY", "type": "MARKET",
                   "quantity": "0.001", "newClientOrderId": "cq77" + "9" * 32,
                   "newOrderRespType": "FULL"} if mutating else {})
    return build_binance_private_request(
        endpoint, parameters, timestamp_ms=1_787_788_800_000)
def _protocol_probe(case_id):
    if case_id == "SIGNATURE_KNOWN_ANSWER":
        fixture = json.loads(resources.files("crypto_quant").joinpath(
            "fixtures", "challenger-replacement-v077",
            "spot-hmac-known-answer.json").read_text())
        _observe_input("signature_known_answer", _safe_input(fixture))
        value = compute_binance_hmac_sha256(
            fixture["payload_ascii"].encode(),
            fixture["illustrative_public_hmac_key_ascii"].encode())
        if value != fixture["expected_hmac_sha256_lowerhex"]: raise ValueError
        return value
    if case_id == "SIGNATURE_PARAMETER_ORDER_MUTATION":
        client = "cq77" + "1" * 32
        a = _call("request_encoding", build_binance_private_request, "SPOT_ORDER_QUERY",
            {"symbol": "ETHUSDT", "origClientOrderId": client}, timestamp_ms=7)
        b = _call("request_encoding", build_binance_private_request, "SPOT_ORDER_QUERY",
            {"origClientOrderId": client, "symbol": "ETHUSDT"}, timestamp_ms=7)
        if a != b: raise ValueError
        return a.encoded_parameters.decode()
    if case_id == "SIGNATURE_PERCENT_ENCODING_MUTATION":
        bad = replace(_request(), encoded_parameters=_request().encoded_parameters + b"%")
        _observe_input("signature_rejection", {"request": _safe_input(bad),
            "secret_sha256": _digest(b"B" * 32)})
        return _error(lambda: sign_binance_private_request(bad, b"B" * 32),
                      "BINANCE_REQUEST_INVALID")
    if case_id in {"CLOCK_AHEAD", "CLOCK_BEHIND", "SERVER_TIME_EXPIRED"}:
        pair = {"CLOCK_AHEAD": (11_001, 10_000), "CLOCK_BEHIND": (4_999, 10_000),
                "SERVER_TIME_EXPIRED": (10_000, 15_001)}[case_id]
        return _error(lambda: _call("request_time", validate_binance_request_time,
            timestamp_ms=pair[0], server_time_ms=pair[1]), "TIMESTAMP_INVALID")
    if case_id == "SERVER_TIME_PRODUCT_DISAGREEMENT":
        _observe_input("server_time_products", {"SPOT": 10_000, "PERPETUAL": 12_001,
            "local_clock_samples": [9_999, 10_001]})
        def observe(product, server_time):
            _authorize_fixture("public_network_requests")
            clocks = iter((9_999, 10_001))
            transport = lambda _request: SimpleNamespace(
                response_class="QUERY_SUCCEEDED",
                body=_body({"serverTime": server_time}))
            return observe_binance_server_time(
                product=product, transport=transport,
                local_clock=lambda: next(clocks))
        spot = observe("SPOT", 10_000)
        perpetual = _error(lambda: observe("PERPETUAL", 12_001),
                           "SERVER_TIME_INVALID")
        return {"checked_products": ["SPOT", "PERPETUAL"],
                "spot_server_time_ms": spot.server_time_ms,
                "perpetual": perpetual}
    if case_id in {"HOST_REJECTED", "PATH_REJECTED"}:
        altered = replace(_request(False), **({"host": "evil.invalid"}
                          if case_id == "HOST_REJECTED" else {"path": "/evil"}))
        _observe_input("signature_rejection", {"request": _safe_input(altered),
            "secret_sha256": _digest(b"B" * 32)})
        return _error(lambda: sign_binance_private_request(altered, b"B" * 32),
                      "BINANCE_REQUEST_INVALID")
    statuses = {
        "VENUE_MINUS_1007_UNKNOWN": (504, b'{"code":-1007,"msg":"timeout"}', "UNKNOWN"),
        "VENUE_5XX_UNKNOWN": (500, b'{"code":-1000,"msg":"error"}', "UNKNOWN"),
        "MALFORMED_2XX_UNKNOWN": (200, b"not-json", "UNKNOWN"),
        "RATE_LIMIT_418": (418, b'{"code":-1003,"msg":"banned"}', "RATE_LIMITED"),
        "RATE_LIMIT_429": (429, b'{"code":-1003,"msg":"slow"}', "RATE_LIMITED"),
    }
    status, body, expected = statuses[case_id]
    value = _call("response_classification", classify_binance_private_response,
                                               _request(), status=status,
                                               body=body, headers={})
    if value["response_class"] != expected: raise ValueError
    return value
class _Response:
    def __init__(self, status=200, body=b"{}"):
        self.status, self.body = status, body
    def read(self, _limit): return self.body
    def getheaders(self): return ()
class _Connection:
    def __init__(self, response=None, request_error=None, response_error=None,
                 pre_send_error=None):
        self.response = response or _Response(); self.request_error = request_error
        self.response_error = response_error; self.pre_send_error = pre_send_error
        self.sent = 0; self.attempts = 0
    def request(self, method, *_args, **_kwargs):
        _ACTIVE_LEDGER.authorize_request(
            "ORDER_CREATE" if method == "POST" else "PRIVATE_READ",
            _FIXTURE_AUTHORITY)
        _observe("fixture_transport_requests")
        if method == "POST": _observe("fixture_mutating_requests")
        self.attempts += 1
        if self.pre_send_error: raise self.pre_send_error
        self.sent += 1
        if self.request_error: raise self.request_error
    def getresponse(self):
        if self.response_error: raise self.response_error
        return self.response
    def close(self): pass
def _activation():
    value = {
        "$schema": "./challenger-replacement-binance-private-activation-v1.schema.json",
        "schema_version": "1.0.0", "activation_id": "binance_private_activation_" + "5" * 64,
        "build_identity": _BUILD, "configuration_sha256": "6" * 64,
        "account_approval_sha256": "7" * 64, "block_id": "e0-block-" + "8" * 64,
        "stage": "E0", "capital_usdt": "100", "max_gross_exposure_usdt": "50",
        "max_leverage": "0.5", "expires_at": "2026-08-28T00:00:00.000Z",
        "production_activation": True,
    }
    return load_binance_private_activation_bytes(
        (canonical_json(value) + "\n").encode(), build_identity=_BUILD, now=_NOW)
def _credential(directory):
    _observe("fixture_credential_reads")
    parent = Path(directory) / "credential"; parent.mkdir(mode=0o700)
    path = parent / "binance-hmac.json"
    body = (canonical_json({"api_key": "A" * 32, "hmac_secret": "B" * 32}) + "\n").encode()
    path.write_bytes(body); path.chmod(0o600); pstat, fstat = parent.stat(), path.stat()
    reference = {"$schema": "./challenger-replacement-binance-credential-reference-v1.schema.json",
        "schema_version": "1.0.0", "absolute_path": str(path),
        "parent_device": pstat.st_dev, "parent_inode": pstat.st_ino,
        "file_device": fstat.st_dev, "file_inode": fstat.st_ino,
        "file_sha256": _digest(body)}
    return open_binance_credential_capability(
        reference=reference, expected_owner_uid=os.getuid()), path, body

def _transport_probe(case_id):
    if case_id == "ACK_LOSS_QUERY_RECOVERY":
        return _runtime_spot_ack_recovery()
    with tempfile.TemporaryDirectory(prefix="cq-v077-private-transport-") as directory:
        credential, path, body = _credential(directory)
        request = _request(False) if case_id == "SAME_BYTES_DIFFERENT_IDENTITY" else _request()
        _observe_input("fixture_transport", {"case_id": case_id,
            "request": _safe_input(request), "credential_file_sha256": _digest(body)})
        try:
            if case_id == "SAME_BYTES_DIFFERENT_IDENTITY":
                replacement = path.with_suffix(".new"); replacement.write_bytes(body)
                replacement.chmod(0o600); os.replace(replacement, path)
                return _error(lambda: credential.authorize(request),
                              "ATTACHMENT_CHANGED")
            connection = _Connection()
            if case_id in {"DNS_FAILURE", "TLS_FAILURE"}:
                factory = OSError("dns") if case_id == "DNS_FAILURE" else ssl.SSLError("tls")
                expected = "CONNECT_FAILED"
            else:
                factory = connection; expected = None
                if case_id == "DISCONNECT_BEFORE_SEND":
                    connection.pre_send_error = ConnectionResetError()
                elif case_id == "DISCONNECT_DURING_SEND": connection.request_error = TimeoutError()
                elif case_id == "DISCONNECT_AFTER_SEND": connection.response_error = TimeoutError()
                elif case_id == "REDIRECT_REJECTED": connection.response = _Response(302)
                elif case_id == "PROXY_ENV_IGNORED": pass
            with patch.object(http.client, "HTTPSConnection",
                              side_effect=factory if isinstance(factory, Exception) else None,
                              return_value=None if isinstance(factory, Exception) else factory), \
                    patch.dict(os.environ, {"HTTPS_PROXY": "http://secret@evil.invalid"}):
                if expected:
                    return _error(lambda: execute_binance_private_request(
                        request, credential=credential, activation=_activation(),
                        expected_build_identity=_BUILD, now=_NOW), expected)
                result = execute_binance_private_request(
                    request, credential=credential, activation=_activation(),
                    expected_build_identity=_BUILD, now=_NOW)
            wanted = {"REDIRECT_REJECTED": "RESPONSE_INVALID",
                      "PROXY_ENV_IGNORED": "ACKNOWLEDGED",
                      "DISCONNECT_BEFORE_SEND": "UNKNOWN",
                      "DISCONNECT_DURING_SEND": "UNKNOWN",
                      "DISCONNECT_AFTER_SEND": "UNKNOWN"}[case_id]
            expected_sent = 0 if case_id == "DISCONNECT_BEFORE_SEND" else 1
            if (result.response_class != wanted or connection.sent != expected_sent
                    or connection.attempts != 1): raise ValueError
            if case_id == "DISCONNECT_BEFORE_SEND":
                return {"class": wanted, "request_attempts": connection.attempts,
                        "bytes_sent": connection.sent}
            return {"class": wanted, "sent": connection.sent}
        finally:
            credential.close()
def _private_context():
    activation = _activation()
    preflight = {"status": "BINANCE_ACCOUNT_PREFLIGHT_VERIFIED_FLAT",
        "preflight_id": "binance_account_preflight_" + "4" * 64,
        "configuration": {"position_mode": "ONE_WAY", "asset_mode": "SINGLE_ASSET",
            "symbol": "ETHUSDT", "margin_type": "ISOLATED", "leverage": 1,
            "auto_add_margin": False}}
    projection = {"plan_hash": "1" * 64, "active_product_or_null": None,
        "unresolved_client_order_ids": [], "proven_absent_client_order_ids": []}
    intent = {"opportunity_id": "ETHUSDT@2026-08-27T12:00:00.000Z",
        "intent_id": "replacement_intent_" + "3" * 64,
        "block_id": "e0-block-" + "8" * 64, "product": "SPOT",
        "action": "OPEN_LONG", "quantity": "0.025", "attempt_ordinal": 1,
        "unsigned_intent_sha256": "8" * 64}
    return activation, preflight, projection, intent

def _prepare_attempt(**values):
    _observe("fixture_order_intents")
    return _call("order_intent", prepare_binance_order_attempt, **values)

def _reconcile_fixture(**values):
    _observe("fixture_reconciliations")
    return _call("reconciliation", reconcile_binance_private_state, **values)
def _body(value): return canonical_json(value).encode()

@contextmanager
def _runtime_workspace(product, persistent_parent=None):
    _authorize_fixture("production_state_writes")
    seed_bytes = resources.files("crypto_quant").joinpath(
        "fixtures", "challenger-replacement-v077", "private-runtime-seeds-v1.json").read_bytes()
    seed_document = _strict_json_bytes(seed_bytes[:-1]); seed = seed_document["seeds"][product]
    if ((canonical_json(seed_document) + "\n").encode() != seed_bytes
            or frozenset(seed) != {"opportunity_id", "build_identity", "events"}):
        raise ValueError("PRIVATE_FAULT_RUNTIME_SEED_INVALID")
    if persistent_parent is None:
        owner = tempfile.TemporaryDirectory(
            prefix="cq-v077-runtime-scenario-", dir=_temporary_base())
        parent = Path(owner.name)
    else:
        parent = Path(persistent_parent)
        try:
            parent.mkdir(mode=0o700)
        except FileExistsError:
            pass
        parent_entry = parent.lstat()
        if (not stat.S_ISDIR(parent_entry.st_mode)
                or parent_entry.st_uid != os.getuid()
                or stat.S_IMODE(parent_entry.st_mode) != 0o700):
            raise ValueError("PRIVATE_FAULT_RUNTIME_ROOT_UNTRUSTED")
        owner = SimpleNamespace(name=str(parent))
    root_path = parent / "events"
    try:
        root_path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    if any(root_path.iterdir()):
        raise ValueError("PRIVATE_FAULT_RUNTIME_ROOT_NOT_EMPTY")
    entry = root_path.lstat()
    identity = ChallengerReplacementEventRootIdentity(
        str(root_path), entry.st_dev, entry.st_ino, entry.st_uid, "0700")
    root = open_challenger_replacement_event_root(identity)
    plan = load_challenger_replacement_plan_v3(
        _ROOT / "artifacts/challenger-replacement/challenger-replacement-plan-v0.69.0.json")
    build_identity = seed["build_identity"]
    state = ChallengerReplacementOpportunityState(
        event_root=root, plan=plan, build_identity=build_identity)
    completed = False
    try:
        input_payload = seed["events"][0]["payload"]
        capture_bytes = __import__("base64").b64decode(
            input_payload["source_bundle_bytes_base64"], validate=True
        )
        capture = load_challenger_replacement_public_market_capture_bytes(
            capture_bytes, plan=plan, build_identity=build_identity,
            previous_source_bundle=None,
        )
        economic = build_challenger_replacement_economic_plan()
        predecessor = build_challenger_replacement_simulation_contract(plan=plan)
        public_contract = build_challenger_replacement_public_simulation_contract(
            plan=plan, economic_plan=economic,
            predecessor_contract=predecessor,
        )
        with patch.object(public_runtime, "_acquire", return_value=capture), \
                patch.object(public_runtime, "_wall_now", return_value=datetime(
                    2026, 8, 26, 4, 5, tzinfo=timezone.utc)):
            observed = public_runtime.run_challenger_replacement_v3_opportunity(
                state=state, event_root=root, plan=plan,
                economic_plan=economic, predecessor_contract=predecessor,
                public_contract=public_contract, build_identity=build_identity,
            )
        if (observed["status"] != "OBSERVED"
                or observed["opportunity_id"] != seed["opportunity_id"]):
            raise ValueError("PRIVATE_FAULT_RUNTIME_SEED_INVALID")
        yield SimpleNamespace(temporary=owner, root=root, state=state, plan=plan,
            seed=seed, opportunity_id=seed["opportunity_id"])
        completed = True
    finally:
        root.close()
        if persistent_parent is None:
            owner.cleanup()
        elif completed:
            for candidate in root_path.iterdir():
                entry = candidate.lstat()
                if (not stat.S_ISREG(entry.st_mode) or entry.st_uid != os.getuid()
                        or entry.st_nlink != 1):
                    raise ValueError("PRIVATE_FAULT_RUNTIME_ROOT_UNTRUSTED")
                candidate.unlink()

@contextmanager
def _reopen_runtime_workspace(product, identity):
    _authorize_fixture("production_state_writes")
    seed_bytes = resources.files("crypto_quant").joinpath(
        "fixtures", "challenger-replacement-v077",
        "private-runtime-seeds-v1.json").read_bytes()
    document = _strict_json_bytes(seed_bytes[:-1])
    if ((canonical_json(document) + "\n").encode() != seed_bytes
            or product not in {"SPOT", "PERPETUAL"}):
        raise ValueError("PRIVATE_FAULT_RUNTIME_SEED_INVALID")
    seed = document["seeds"][product]
    root = open_challenger_replacement_event_root(identity)
    plan = load_challenger_replacement_plan_v3(
        _ROOT / "artifacts/challenger-replacement/challenger-replacement-plan-v0.69.0.json")
    state = ChallengerReplacementOpportunityState(
        event_root=root, plan=plan, build_identity=seed["build_identity"])
    try:
        yield SimpleNamespace(
            temporary=SimpleNamespace(name=str(Path(identity.absolute_path).parent)),
            root=root, state=state, plan=plan, seed=seed,
            opportunity_id=seed["opportunity_id"])
    finally:
        root.close()

def _runtime_authority(workspace):
    fixture = json.loads(resources.files("crypto_quant").joinpath(
        "fixtures", "challenger-replacement-v077", "account-preflight-flat.json").read_text())
    identity = BinanceCredentialIdentity(1, 2, os.getuid(), 3, 4, "9" * 64, "a" * 64)
    account_hash = _digest({"api_key_create_time": fixture["API_RESTRICTIONS"]["createTime"],
                            "spot_uid": fixture["SPOT_ACCOUNT"]["uid"], "venue": "BINANCE"})
    approval = BinanceAccountApproval(account_hash, identity.key_fingerprint,
        "203.0.113.10", os.getuid(), "2026-08-27T10:00:00.000Z",
        "2026-08-28T00:00:00.000Z", True, True)
    receipt = evaluate_binance_account_preflight(
        responses={key: _body(value) for key, value in fixture.items()},
        account_approval=approval, credential_identity=identity,
        build_identity=workspace.seed["build_identity"], now=_NOW)
    document = json.loads(receipt)
    activation_document = {"$schema": "./challenger-replacement-binance-private-activation-v1.schema.json",
        "schema_version": "1.0.0", "activation_id": "binance_private_activation_" + "5" * 64,
        "build_identity": workspace.seed["build_identity"],
        "configuration_sha256": document["configuration_sha256"],
        "account_approval_sha256": document["account_approval_sha256"],
        "block_id": "e0-block-" + "8" * 64, "stage": "E0", "capital_usdt": "100",
        "max_gross_exposure_usdt": "50", "max_leverage": "0.5",
        "expires_at": "2026-08-28T00:00:00.000Z", "production_activation": True}
    activation = load_binance_private_activation_bytes(
        (canonical_json(activation_document) + "\n").encode(),
        build_identity=workspace.seed["build_identity"], now=_NOW)
    parent = Path(workspace.temporary.name) / "preflight"
    created_parent = False
    try:
        parent.mkdir(mode=0o700); created_parent = True
    except FileExistsError:
        pass
    parent_entry = parent.lstat()
    if (not stat.S_ISDIR(parent_entry.st_mode)
            or parent_entry.st_uid != os.getuid()
            or stat.S_IMODE(parent_entry.st_mode) != 0o700):
        raise ValueError("PRIVATE_FAULT_PREFLIGHT_UNTRUSTED")
    path = parent / "receipt.json"
    if created_parent:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            if os.write(descriptor, receipt) != len(receipt):
                raise OSError
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    else:
        entry = path.lstat()
        if (not stat.S_ISREG(entry.st_mode) or entry.st_uid != os.getuid()
                or stat.S_IMODE(entry.st_mode) != 0o600 or entry.st_nlink != 1
                or path.read_bytes() != receipt):
            raise ValueError("PRIVATE_FAULT_PREFLIGHT_UNTRUSTED")
    parent_stat, file_stat = parent.lstat(), path.lstat()
    reference = {"schema_version": "1.0.0", "absolute_path": str(path),
        "parent_device": parent_stat.st_dev, "parent_inode": parent_stat.st_ino,
        "file_device": file_stat.st_dev, "file_inode": file_stat.st_ino,
        "file_sha256": _digest(receipt)}
    capability = open_binance_account_preflight_capability(
        reference_bytes=(canonical_json(reference) + "\n").encode(),
        expected_uid=os.getuid(), build_identity=workspace.seed["build_identity"])
    credential = SimpleNamespace(identity=identity)
    _observe("fixture_order_intents")
    intent = build_binance_order_intent_from_opportunity(
        slot=workspace.state.replay()["opportunities"][workspace.opportunity_id],
        activation=activation, attempt_ordinal=1)
    return activation, capability, credential, intent

def _transport_result(response_class, body, status=200):
    return BinancePrivateTransportResult(response_class,
        None if response_class == "UNKNOWN" else status, body, _digest(body), ())

def _runtime_call(workspace, authority, responses):
    activation, preflight, credential, intent = authority; calls = []
    response_values = tuple(responses)
    _observe_input("private_runtime_call", {
        "product": intent["product"],
        "intent_id": intent["intent_id"],
        "responses": [{"response_class": item.response_class,
            "http_status_or_null": item.status_or_null,
            "body_utf8": item.body.decode(), "body_sha256": _digest(item.body)}
            for item in response_values],
    })
    responses = iter(response_values)
    reconcile_captured = private_runtime._reconcile_captured
    reconcile_stop = private_runtime.reconcile_binance_protective_stop
    def transport(request, **_kwargs):
        _ACTIVE_LEDGER.authorize_request(request.endpoint_id, _FIXTURE_AUTHORITY)
        _observe("fixture_transport_requests"); calls.append(request.endpoint_id)
        if request.endpoint_id.endswith("CREATE"): _observe("fixture_mutating_requests")
        return next(responses)
    def observed_reconciliation(*args, **kwargs):
        _observe("fixture_reconciliations")
        return reconcile_captured(*args, **kwargs)
    def observed_stop_reconciliation(*args, **kwargs):
        _observe("fixture_reconciliations")
        return reconcile_stop(*args, **kwargs)
    public = PublicHttpResponse(200,
        "https://fapi.binance.com/fapi/v1/time" if intent["product"] == "PERPETUAL"
        else "https://api.binance.com/api/v3/time", {"Content-Type": "application/json"},
        b'{"serverTime":1787832000000}', 0, _NOW, _NOW)
    def fixed_public(*_args, **_kwargs):
        _authorize_fixture("public_network_requests")
        return public
    with patch.object(private_runtime, "_wall_now",
            return_value=datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)), \
            patch.object(private_runtime, "open_fixed_public_request", side_effect=fixed_public), \
            patch.object(private_runtime, "execute_binance_private_request", side_effect=transport), \
            patch.object(private_runtime, "_reconcile_captured",
                         side_effect=observed_reconciliation), \
            patch.object(private_runtime, "reconcile_binance_protective_stop",
                         side_effect=observed_stop_reconciliation):
        result = private_runtime.run_challenger_replacement_binance_private_intent(
            state=workspace.state, event_root=workspace.root, intent=intent,
            preflight_capability=preflight, activation=activation,
            credential=credential, build_identity=workspace.seed["build_identity"])
    return result, calls

def _runtime_client(workspace, intent):
    return derive_binance_client_order_id(plan_hash=workspace.plan["plan_hash"],
        block_id=intent["block_id"], intent_id=intent["intent_id"],
        attempt_ordinal=1, product=intent["product"])

def _runtime_event_types(workspace):
    return [json.loads(event.final_bytes)["event_type"]
            for event in workspace.state._replay()["events"]]

def _runtime_state_identity(workspace):
    projection = workspace.state._replay()
    return len(projection["events"]), projection["last_event_hash"]

def _runtime_probe_result(value, event_before, workspace):
    value["_fault_state_identity"] = {
        "event_before_or_null": event_before,
        "event_after_or_null": _runtime_state_identity(workspace)[1],
    }
    return value

def _prepare_spot_unknown(workspace, authority):
    absent = _body({"code": -2013, "msg": "Order does not exist."})
    return _runtime_call(workspace, authority, (
        _transport_result("RESPONSE_INVALID", absent, 400),
        _transport_result("UNKNOWN", b"")))

def _resume_spot_unknown(workspace, authority):
    intent = authority[3]
    client, quantity = _runtime_client(workspace, intent), intent["quantity"]
    order = _body({"symbol": "ETHUSDT", "orderId": 101,
        "clientOrderId": client, "price": "0", "origQty": quantity,
        "executedQty": quantity, "cummulativeQuoteQty": "30", "status": "FILLED",
        "timeInForce": "GTC", "type": "MARKET", "side": "BUY",
        "transactTime": 1787832000000})
    trade = _body([{"symbol": "ETHUSDT", "id": 301, "orderId": 101,
        "qty": quantity, "price": "2000", "quoteQty": "30", "commission": "0.03",
        "commissionAsset": "USDT", "time": 1787832000001, "isBuyer": True}])
    account = json.loads(resources.files("crypto_quant").joinpath(
        "fixtures", "challenger-replacement-v077", "account-preflight-flat.json").read_text())["SPOT_ACCOUNT"]
    balances = {item["asset"]: item for item in account["balances"]}
    balances["ETH"]["free"], balances["USDT"]["free"] = quantity, "69.97"
    return _runtime_call(workspace, authority, (
        _transport_result("QUERY_SUCCEEDED", order),
        _transport_result("QUERY_SUCCEEDED", trade),
        _transport_result("QUERY_SUCCEEDED", _body(account))))

def _runtime_spot_ack_recovery():
    with _runtime_workspace("SPOT") as workspace:
        event_before = _runtime_state_identity(workspace)[1]
        authority = _runtime_authority(workspace)
        initial, initial_calls = _prepare_spot_unknown(workspace, authority)
        workspace.state = ChallengerReplacementOpportunityState(
            event_root=workspace.root, plan=workspace.plan,
            build_identity=workspace.seed["build_identity"])
        recovered, recovery_calls = _resume_spot_unknown(workspace, authority)
        authority[1].close()
        return _runtime_probe_result({"initial_status": initial["status"], "recovered_status": recovered["status"],
            "economic_send_count": initial_calls.count("SPOT_ORDER_CREATE"),
            "recovery_send_count": recovery_calls.count("SPOT_ORDER_CREATE"),
            "initial_endpoints": initial_calls, "recovery_endpoints": recovery_calls,
            "event_types": _runtime_event_types(workspace),
            "last_event_hash": _runtime_state_identity(workspace)[1]},
            event_before, workspace)

def _perpetual_documents(workspace, intent, quantity, trade_ids):
    client = _runtime_client(workspace, intent); quote = str(Decimal(quantity) * 2000)
    order = _body({"symbol": "ETHUSDT", "orderId": 202, "clientOrderId": client,
        "avgPrice": "2000", "origQty": intent["quantity"], "executedQty": quantity,
        "cumQuote": quote, "status": "PARTIALLY_FILLED", "type": "MARKET", "side": "SELL",
        "positionSide": "BOTH", "reduceOnly": False, "updateTime": 1787832000000})
    trades = _body([{"symbol": "ETHUSDT", "id": trade_id, "orderId": 202,
        "qty": "0.005", "price": "2000", "quoteQty": "10", "commission": "0.004",
        "commissionAsset": "USDT", "realizedPnl": "0", "time": 1787832000000 + trade_id,
        "buyer": False} for trade_id in trade_ids])
    position = json.loads(resources.files("crypto_quant").joinpath(
        "fixtures", "challenger-replacement-v077", "account-preflight-flat.json").read_text())["FUTURES_POSITION"]
    position[0].update(positionAmt="-" + quantity, entryPrice="2000")
    return order, trades, _body(position)

def _runtime_stop(workspace, intent, quantity):
    trigger = workspace.state.replay()["opportunities"][workspace.opportunity_id][
        "result_evidence"]["next_snapshot"]["protective_stop_or_null"]["trigger"]
    stop = prepare_binance_protective_stop(short_quantity=quantity, trigger_price=trigger,
        intent_identity={"plan_hash": workspace.plan["plan_hash"],
            "block_id": intent["block_id"], "intent_id": intent["intent_id"]})
    algo = {"algoId": 900 + int(Decimal(quantity) * 1000),
        "clientAlgoId": stop["client_algo_id"], "algoType": "CONDITIONAL",
        "orderType": "STOP_MARKET", "symbol": "ETHUSDT", "side": "BUY",
        "positionSide": "BOTH", "quantity": quantity, "triggerPrice": trigger,
        "workingType": "MARK_PRICE", "reduceOnly": True, "closePosition": False,
        "algoStatus": "NEW"}
    return stop, _body(algo)

def _prepare_partial_stop(workspace, authority):
    intent = authority[3]
    absent = _body({"code": -2013, "msg": "Order does not exist."})
    order, trades, position = _perpetual_documents(
        workspace, intent, "0.005", (401,))
    old, old_algo = _runtime_stop(workspace, intent, "0.005")
    initial, calls = _runtime_call(workspace, authority, (
        _transport_result("RESPONSE_INVALID", absent, 400),
        _transport_result("ACKNOWLEDGED", order),
        _transport_result("QUERY_SUCCEEDED", order),
        _transport_result("QUERY_SUCCEEDED", trades),
        _transport_result("QUERY_SUCCEEDED", position),
        _transport_result("RESPONSE_INVALID", absent, 400),
        _transport_result("ACKNOWLEDGED", old_algo),
        _transport_result("QUERY_SUCCEEDED", old_algo)))
    return initial, calls, old

def _resume_partial_stop(workspace, authority):
    intent = authority[3]
    order, trades, position = _perpetual_documents(
        workspace, intent, "0.005", (401,))
    old, old_algo = _runtime_stop(workspace, intent, "0.005")
    replayed, calls = _runtime_call(workspace, authority, (
        _transport_result("QUERY_SUCCEEDED", order),
        _transport_result("QUERY_SUCCEEDED", trades),
        _transport_result("QUERY_SUCCEEDED", position),
        _transport_result("QUERY_SUCCEEDED", old_algo)))
    return replayed, calls, old

def _runtime_partial_stop(*, replace_stop=False, restart=False):
    with _runtime_workspace("PERPETUAL") as workspace:
        event_before = _runtime_state_identity(workspace)[1]
        authority = _runtime_authority(workspace); intent = authority[3]
        absent = _body({"code": -2013, "msg": "Order does not exist."})
        initial, initial_calls, old = _prepare_partial_stop(workspace, authority)
        if not replace_stop and not restart:
            authority[1].close()
            return _runtime_probe_result({"status": initial["status"], "protected_quantity": old["quantity"],
                    "transport_endpoints": initial_calls, "event_types": _runtime_event_types(workspace),
                    "last_event_hash": _runtime_state_identity(workspace)[1]},
                    event_before, workspace)
        workspace.state = ChallengerReplacementOpportunityState(
            event_root=workspace.root, plan=workspace.plan,
            build_identity=workspace.seed["build_identity"])
        if restart:
            replayed, calls, old = _resume_partial_stop(workspace, authority)
            authority[1].close()
            return _runtime_probe_result({"status": replayed["status"], "protected_quantity": old["quantity"],
                    "recovery_send_count": sum(name.endswith("CREATE") for name in calls),
                    "transport_endpoints": calls, "event_types": _runtime_event_types(workspace),
                    "last_event_hash": _runtime_state_identity(workspace)[1]},
                    event_before, workspace)
        larger, larger_trades, larger_position = _perpetual_documents(
            workspace, intent, "0.010", (401, 402))
        candidate, candidate_algo = _runtime_stop(workspace, intent, "0.01")
        _, old_algo = _runtime_stop(workspace, intent, "0.005")
        canceled = _body({**json.loads(old_algo), "algoStatus": "CANCELED"})
        replaced, calls = _runtime_call(workspace, authority, (
            _transport_result("QUERY_SUCCEEDED", larger),
            _transport_result("QUERY_SUCCEEDED", larger_trades),
            _transport_result("QUERY_SUCCEEDED", larger_position),
            _transport_result("RESPONSE_INVALID", absent, 400),
            _transport_result("ACKNOWLEDGED", candidate_algo),
            _transport_result("QUERY_SUCCEEDED", candidate_algo),
            _transport_result("QUERY_SUCCEEDED", candidate_algo),
            _transport_result("ACKNOWLEDGED", canceled), _transport_result("RESPONSE_INVALID", absent, 400)))
        event_types = _runtime_event_types(workspace); authority[1].close()
        reconciled = [index for index, event_type in enumerate(event_types)
                      if event_type == "BINANCE_STOP_RECONCILED"]
        stop = workspace.state.replay()["opportunities"][workspace.opportunity_id]["private"]["stop"]
        return _runtime_probe_result({"status": replaced["status"], "replacement_stage": stop["replacement"]["stage"],
            "candidate_verified_index": reconciled[-1],
            "old_cancel_started_index": event_types.index("BINANCE_STOP_REPLACEMENT_CANCEL_SEND_STARTED"),
            "transport_endpoints": initial_calls + calls, "event_types": event_types,
            "last_event_hash": _runtime_state_identity(workspace)[1]},
            event_before, workspace)
def _spot_documents(attempt, status="PARTIALLY_FILLED", quantity="0.01"):
    order = _body({"symbol": "ETHUSDT", "orderId": 101,
        "clientOrderId": attempt["venue_client_order_id"], "price": "0",
        "origQty": attempt["quantity"], "executedQty": quantity,
        "cummulativeQuoteQty": "20", "status": status, "timeInForce": "GTC",
        "type": "MARKET", "side": "BUY", "transactTime": 1787832000000})
    trade = {"symbol": "ETHUSDT", "id": 301, "orderId": 101,
        "qty": quantity, "price": "2000", "quoteQty": "20",
        "commission": "0.02", "commissionAsset": "USDT",
        "time": 1787832000001, "isBuyer": True}
    fixture = json.loads(resources.files("crypto_quant").joinpath(
        "fixtures", "challenger-replacement-v077", "account-preflight-flat.json").read_text())
    balances = {item["asset"]: item for item in fixture["SPOT_ACCOUNT"]["balances"]}
    balances["ETH"]["free"] = quantity; balances["USDT"]["free"] = "79.98"
    return order, trade, _body(fixture["SPOT_ACCOUNT"])
def _lifecycle_probe(case_id):
    activation, preflight, projection, intent = _private_context()
    if case_id == "SPOT_PERPETUAL_MUTUAL_EXCLUSION":
        projection["active_product_or_null"] = "PERPETUAL"
        return _error(lambda: _prepare_attempt(intent=intent,
            projection=projection, preflight=preflight, activation=activation),
            "MUTUAL_EXCLUSION")
    if case_id in {"DUPLICATE_CLIENT_ID", "QUERY_BEFORE_RETRY",
                   "PROVEN_ABSENT_ONLY_BEFORE_FIRST_SEND"}:
        ordinal = 1 if case_id == "DUPLICATE_CLIENT_ID" else 2
        intent["attempt_ordinal"] = ordinal
        client = derive_binance_client_order_id(plan_hash=projection["plan_hash"],
            block_id=intent["block_id"], intent_id=intent["intent_id"],
            attempt_ordinal=ordinal, product="SPOT")
        if case_id == "DUPLICATE_CLIENT_ID":
            projection["unresolved_client_order_ids"] = [client]
            value = _prepare_attempt(intent=intent,
                projection=projection, preflight=preflight, activation=activation)
            if value["venue_client_order_id"] != client or value["send_permitted"]:
                raise ValueError
            return {"client_order_id": client, "query_before_send": True}
        if case_id == "PROVEN_ABSENT_ONLY_BEFORE_FIRST_SEND":
            projection["proven_absent_client_order_ids"] = [client]
            value = _prepare_attempt(intent=intent, projection=projection,
                preflight=preflight, activation=activation)
            if not value["send_permitted"]: raise ValueError
            return value["required_first_endpoint"]
        return _error(lambda: _prepare_attempt(intent=intent,
            projection=projection, preflight=preflight, activation=activation),
            "ABSENCE_NOT_PROVEN")
    attempt = _prepare_attempt(intent=intent, projection=projection,
        preflight=preflight, activation=activation)
    order, trade, account = _spot_documents(attempt)
    if case_id in {"OVERFILL", "CONFLICTING_FILL"}:
        other = dict(trade)
        if case_id == "OVERFILL": other.update(id=302, qty="0.02", quoteQty="40")
        else: other["price"] = "2001"
        reason = "OVERFILL" if case_id == "OVERFILL" else "CONFLICTING_DUPLICATE_FILL"
        return _error(lambda: apply_binance_order_observation(attempt=attempt,
            order=order, trades=(_body(trade), _body(other)), account=account), reason)
    trades = (_body(trade),)
    if case_id in {"CANCEL_FILL_RACE", "LATE_FILL"}: order, _, _ = _spot_documents(attempt, "CANCELED")
    if case_id == "LATE_FILL":
        empty_order = json.loads(order); empty_order.update(
            executedQty="0", cummulativeQuoteQty="0")
        fixture = json.loads(resources.files("crypto_quant").joinpath(
            "fixtures", "challenger-replacement-v077", "account-preflight-flat.json").read_text())
        first = apply_binance_order_observation(attempt=attempt,
            order=_body(empty_order), trades=(), account=_body(fixture["SPOT_ACCOUNT"]))
        if first[-1]["event_type"] != "BINANCE_ORDER_CANCELED": raise ValueError
    events = apply_binance_order_observation(attempt=attempt, order=order,
                                             trades=trades, account=account)
    return [event["event_type"] for event in events]
def _preflight_probe(case_id):
    fixture = json.loads(resources.files("crypto_quant").joinpath(
        "fixtures", "challenger-replacement-v077", "account-preflight-flat.json").read_text())
    endpoint, key, value = {
        "WRONG_POSITION_MODE": ("FUTURES_POSITION_MODE", "dualSidePosition", True),
        "WRONG_MULTI_ASSET_MODE": ("FUTURES_MULTI_ASSET_MODE", "multiAssetsMargin", True),
        "WRONG_MARGIN_TYPE": ("FUTURES_SYMBOL_CONFIG", "marginType", "CROSSED"),
        "LEVERAGE_ABOVE_TWO": ("FUTURES_SYMBOL_CONFIG", "leverage", 3),
    }[case_id]
    target = fixture[endpoint][0] if endpoint == "FUTURES_SYMBOL_CONFIG" else fixture[endpoint]
    target[key] = value
    account_hash = _digest({"api_key_create_time": fixture["API_RESTRICTIONS"]["createTime"],
                            "spot_uid": fixture["SPOT_ACCOUNT"]["uid"], "venue": "BINANCE"})
    approval = BinanceAccountApproval(account_hash, "5" * 64, "203.0.113.10", os.getuid(),
        "2026-08-27T10:00:00.000Z", "2026-08-28T00:00:00.000Z", True, True)
    identity = BinanceCredentialIdentity(1, 2, os.getuid(), 3, 4, "7" * 64, "5" * 64)
    responses = {name: _body(document) for name, document in fixture.items()}
    _observe_input("account_preflight", {
        "case_id": case_id,
        "responses": {name: body.decode() for name, body in responses.items()},
    })
    return _error(lambda: evaluate_binance_account_preflight(responses=responses,
        account_approval=approval, credential_identity=identity,
        build_identity=_BUILD, now=_NOW), "CONFIGURATION_BLOCKED")

def _stop_probe(case_id):
    if case_id == "PARTIAL_SHORT_REQUIRES_STOP_BEFORE_RETURN":
        return _runtime_partial_stop()
    if case_id == "STOP_REPLACEMENT_NO_GAP":
        return _runtime_partial_stop(replace_stop=True)
    identity = {"plan_hash": "1" * 64, "block_id": "e0-block-" + "2" * 64,
                "intent_id": "replacement_intent_" + "3" * 64}
    quantity = "0.01" if case_id in {"PARTIAL_SHORT_REQUIRES_STOP_BEFORE_RETURN",
                                     "STOP_REPLACEMENT_NO_GAP"} else "0.025"
    expected = prepare_binance_protective_stop(short_quantity=quantity,
        trigger_price="2036.43", intent_identity=identity)
    position = _body({"symbol": "ETHUSDT", "positionSide": "BOTH",
                      "positionAmt": "-" + quantity, "entryPrice": "2000"})
    algo = {"algoId": 901, "clientAlgoId": expected["client_algo_id"],
        "algoType": "CONDITIONAL", "orderType": "STOP_MARKET", "symbol": "ETHUSDT",
        "side": "BUY", "positionSide": "BOTH", "quantity": quantity,
        "triggerPrice": "2036.43", "workingType": "MARK_PRICE", "reduceOnly": True,
        "closePosition": False, "algoStatus": "NEW"}
    if case_id == "STOP_REJECTED": algo["algoStatus"] = "REJECTED"
    elif case_id == "STOP_LOST":
        missing = _body({"code": -2013, "msg": "not found"})
        _observe_input("protective_stop_reconciliation", _safe_input({
            "position": position, "algo_order": missing, "expected": expected}))
        return _error(lambda: reconcile_binance_protective_stop(
            position=position, algo_order=missing, expected=expected),
            "WITHOUT_VALID_PROTECTIVE_STOP")
    elif case_id == "STOP_CANCEL_RACE": algo["algoStatus"] = "CANCELED"
    elif case_id == "STOP_QUERY_MISMATCH": algo["triggerPrice"] = "2036.44"
    _observe_input("protective_stop_reconciliation", _safe_input({
        "position": position, "algo_order": _body(algo), "expected": expected}))
    call = lambda: reconcile_binance_protective_stop(
        position=position, algo_order=_body(algo), expected=expected)
    if case_id in {"STOP_REJECTED", "STOP_CANCEL_RACE", "STOP_QUERY_MISMATCH"}:
        return _error(call, "WITHOUT_VALID_PROTECTIVE_STOP")
    result = call()
    if result["status"] != "BINANCE_PROTECTIVE_STOP_VERIFIED": raise ValueError
    return result

def _reconciliation_values():
    client = "cq77" + "1" * 32
    facts = {"product": "PERPETUAL", "signed_quantity": "-0.025",
        "average_entry_price_or_null": "2000", "realized_pnl": "-0.01",
        "unrealized_pnl": "1", "cumulative_fee": "0.02", "funding": "-0.005",
        "wallet_balance": "100", "available_balance": "75", "open_order_count": 0,
        "protective_stop_client_id_or_null": client, "fill_ids": [401]}
    fixture = json.loads(resources.files("crypto_quant").joinpath(
        "fixtures", "challenger-replacement-v077", "account-preflight-flat.json").read_text())
    account = fixture["FUTURES_ACCOUNT"]
    account.update(totalInitialMargin="25", totalMaintMargin="1",
        totalUnrealizedProfit="1", totalMarginBalance="101",
        totalPositionInitialMargin="25", availableBalance="75", maxWithdrawAmount="75")
    account["assets"][0].update(unrealizedProfit="1", marginBalance="101",
        maintMargin="1", initialMargin="25", positionInitialMargin="25",
        availableBalance="75", maxWithdrawAmount="75")
    position = fixture["FUTURES_POSITION"]
    position[0].update(positionAmt="-0.025", entryPrice="2000", markPrice="1960",
        unRealizedProfit="1", notional="-49", isolatedMargin="25",
        isolatedWallet="25", initialMargin="25", maintMargin="1",
        positionInitialMargin="25")
    shared = {"capture_event_sequence": 1, "capture_event_hash": "1" * 64,
        "device": 1, "inode": 2, "uid": os.getuid(), "mode_octal": "0600",
        "link_count": 1, "event_size": 1024, "event_sha256": "2" * 64}
    publications = {selector: {**shared, "payload_selector": selector,
        "decoded_size": 64, "decoded_sha256": digit * 64}
        for selector, digit in zip(("event_input", "ledger_input", "venue_input"), "345")}
    return {"event_projection": facts, "ledger_projection": dict(facts),
        "authorized_order": {"order_id": 202, "client_order_id": "cq77" + "2" * 32},
        "authorized_stop_or_null": {"client_algo_id": client, "side": "BUY",
            "quantity": "0.025", "trigger_price": "2036.43", "reduce_only": True},
        "order_documents": (_body({"symbol": "ETHUSDT", "orderId": 202,
            "clientOrderId": "cq77" + "2" * 32, "avgPrice": "2000", "origQty": "0.025",
            "executedQty": "0.025", "cumQuote": "50", "status": "FILLED", "type": "MARKET",
            "side": "SELL", "positionSide": "BOTH", "reduceOnly": False,
            "updateTime": 1787832000000}),),
        "trade_documents": (_body({"symbol": "ETHUSDT", "id": 401, "orderId": 202,
            "qty": "0.025", "price": "2000", "quoteQty": "50", "commission": "0.02",
            "commissionAsset": "USDT", "realizedPnl": "-0.01", "time": 1787832000002,
            "buyer": False}),), "account_document": _body(account),
        "position_document": _body(position), "income_documents": (_body({"tranId": 501,
            "symbol": "ETHUSDT", "incomeType": "FUNDING_FEE", "income": "-0.005",
            "asset": "USDT", "time": 1787832000003}),),
        "algo_documents": (_body({"algoId": 901, "clientAlgoId": client, "symbol": "ETHUSDT",
            "algoStatus": "NEW", "side": "BUY", "positionSide": "BOTH", "quantity": "0.025",
            "triggerPrice": "2036.43", "workingType": "MARK_PRICE", "reduceOnly": True,
            "closePosition": False, "algoType": "CONDITIONAL", "orderType": "STOP_MARKET"}),),
        "capture_publications": publications}

def _reconciliation_probe(case_id):
    values = _reconciliation_values()
    if case_id == "DUPLICATE_FEE": values["trade_documents"] *= 2
    elif case_id == "FEE_CORRECTION_CONFLICT":
        altered = json.loads(values["trade_documents"][0]); altered["commission"] = "0.03"
        values["trade_documents"] += (_body(altered),)
    elif case_id == "DUPLICATE_FUNDING": values["income_documents"] *= 2
    elif case_id == "FUNDING_CORRECTION_CONFLICT":
        altered = json.loads(values["income_documents"][0]); altered["income"] = "-0.006"
        values["income_documents"] += (_body(altered),)
    elif case_id == "BALANCE_DISAGREEMENT":
        altered = json.loads(values["account_document"]); altered["availableBalance"] = "74"; altered["assets"][0]["availableBalance"] = "74"
        values["account_document"] = _body(altered)
    elif case_id == "POSITION_DISAGREEMENT":
        altered = json.loads(values["position_document"]); altered[0]["positionAmt"] = "-0.02"
        values["position_document"] = _body(altered)
        algo = json.loads(values["algo_documents"][0]); algo["quantity"] = "0.02"
        values["algo_documents"] = (_body(algo),)
    elif case_id == "ORDER_DISAGREEMENT":
        altered = json.loads(values["order_documents"][0]); altered["status"] = "NEW"
        values["order_documents"] = (_body(altered),)
    elif case_id == "LEDGER_DISAGREEMENT":
        values["ledger_projection"] = {**values["ledger_projection"], "cumulative_fee": "0.03"}
    failures = {"FEE_CORRECTION_CONFLICT": "CONFLICTING_FILL",
        "FUNDING_CORRECTION_CONFLICT": "CONFLICTING_FUNDING",
        "LEDGER_DISAGREEMENT": "LEDGER_PROJECTION_MISMATCH"}
    if case_id in failures:
        return _error(lambda: _reconcile_fixture(**values), failures[case_id])
    if case_id in {"BALANCE_DISAGREEMENT", "POSITION_DISAGREEMENT", "ORDER_DISAGREEMENT"}:
        return _error(lambda: _reconcile_fixture(**values), "VENUE_LOCAL_POSITION_MISMATCH")
    return _digest(_reconcile_fixture(**values))

def _canary_probe(case_id):
    plan = build_challenger_replacement_accelerated_canary_plan()
    block = "e0-block-probe"
    ceremony = []
    states = ("CEREMONY_READY_FLAT", "SPOT_BUY_SUBMITTED", "SPOT_LONG_RECONCILED",
        "SPOT_SELL_SUBMITTED", "FLAT_RECONCILED_AFTER_SPOT", "PERP_SHORT_SUBMITTED",
        "PERP_SHORT_AND_PROTECTIVE_STOP_CONFIRMED", "PERP_CLOSE_REDUCE_ONLY_SUBMITTED",
        "FLAT_RECONCILED_AFTER_PERP", "CEREMONY_QUALIFIED")
    base = 1
    for index, state in enumerate(states):
        amount = state in {"SPOT_LONG_RECONCILED", "FLAT_RECONCILED_AFTER_SPOT",
            "PERP_SHORT_AND_PROTECTIVE_STOP_CONFIRMED", "FLAT_RECONCILED_AFTER_PERP"}
        flat = True if state in {"CEREMONY_READY_FLAT", "FLAT_RECONCILED_AFTER_SPOT",
            "FLAT_RECONCILED_AFTER_PERP", "CEREMONY_QUALIFIED"} else False if state in {
            "SPOT_LONG_RECONCILED", "PERP_SHORT_AND_PROTECTIVE_STOP_CONFIRMED"} else None
        ceremony.append({"event_type": "CEREMONY_STATE_RECONCILED", "block_id": block,
            "label": "OPERATIONAL_CEREMONY_NOT_STRATEGY_EVIDENCE", "state": state,
            "occurred_at": f"2026-08-27T12:00:{base + index:02d}.000Z",
            "reconciliation_id": "binance_reconciliation_" + "1" * 64,
            "minimum_amount_satisfied_or_null": True if amount else None,
            "flat_or_null": flat})
    if case_id == "CEREMONY_EXCLUDED_FROM_ECONOMICS":
        _observe_input("canary_projection", {"events": deepcopy(ceremony),
            "plan_hash": plan["plan_hash"], "now": "2026-08-27T13:00:00.000Z"})
        data = _project_challenger_replacement_canary(
            events=tuple(ceremony), plan=plan, now="2026-08-27T13:00:00.000Z")
        value = json.loads(data)
        if value["ceremony"]["economic_evidence_count"] != 0: raise ValueError
        return value["ceremony"]
    start = {"event_type": "CANARY_STAGE_BLOCK_STARTED", "stage": "E0",
        "block_id": block, "activation_id": "binance_private_activation_" + "2" * 64,
        "previous_block_id_or_null": None, "incident_unlock_id_or_null": None,
        "occurred_at": "2026-08-27T12:01:00.000Z", "starting_equity": "100"}
    equity = {"event_type": "CANARY_EQUITY_RECONCILED", "block_id": block,
        "occurred_at": "2026-08-27T12:02:00.000Z", "equity": "98", "flat": True,
        "new_risk_attempted": False, "hard_stop_or_null": None}
    if case_id == "DRAWDOWN_FLATTEN": equity["equity"] = "95"
    events = ceremony + [start, equity]
    if case_id == "UTC_ROLLOVER_ONLY_RESETS_DAILY_GATE":
        events.append({**equity, "occurred_at": "2026-08-28T00:00:00.000Z", "equity": "98"})
    _observe_input("canary_projection", {"events": deepcopy(events),
        "plan_hash": plan["plan_hash"], "now": "2026-08-28T01:00:00.000Z"})
    data = _project_challenger_replacement_canary(
        events=tuple(events), plan=plan, now="2026-08-28T01:00:00.000Z")
    block_value = json.loads(data)["stage_block_or_null"]
    expected = {"DAILY_STOP": "STAGE_DAILY_STOPPED", "DRAWDOWN_FLATTEN": "STAGE_FAILED_LOCKED",
                "UTC_ROLLOVER_ONLY_RESETS_DAILY_GATE": "STAGE_ACTIVE"}[case_id]
    if block_value["status"] != expected: raise ValueError
    return block_value["status"]

def _misc_probe(case_id):
    if case_id == "READ_ONLY_UI_LOADER_FAILURE":
        from .operations_projection_v3 import load_operations_projection_v3_bytes
        _observe_input("operations_projection_loader", _safe_input(b"{}"))
        return _error(lambda: load_operations_projection_v3_bytes(b"{}"),
                      "OPERATIONS_PROJECTION_V3")
    if case_id == "SECRET_ABSENT_FROM_LOGS_EXCEPTIONS_EVENTS_ARTIFACTS":
        secret = "B" * 32; api_key = "A" * 32; request = _request()
        signature = sign_binance_private_request(request, secret.encode())
        _observe_input("secret_surface_probe", {"request": _safe_input(request),
            "api_key_sha256": _digest(api_key.encode()),
            "secret_sha256": _digest(secret.encode()),
            "signature_sha256": _digest(signature.encode())})
        logs_out, logs_err = io.StringIO(), io.StringIO()
        with tempfile.TemporaryDirectory(
                prefix="cq-v077-secret-transport-", dir=_temporary_base()) as directory:
            credential, _path, _body_bytes = _credential(directory)
            connection = _Connection(response=_Response(200, b"{}"))
            try:
                with redirect_stdout(logs_out), redirect_stderr(logs_err), \
                        patch.object(http.client, "HTTPSConnection",
                                     return_value=connection):
                    transport = execute_binance_private_request(
                        request, credential=credential, activation=_activation(),
                        expected_build_identity=_BUILD, now=_NOW)
            finally:
                credential.close()
        try:
            sign_binance_private_request(
                replace(request, host="invalid"), secret.encode())
        except Exception as error:
            exception = str(error)
        _authorize_fixture("production_state_writes")
        core_hash = _inventory()[1]
        if _ACTIVE_LEDGER.scratch_root is None:
            raise RuntimeError("PRIVATE_FAULT_SCRATCH_ROOT_REQUIRED")
        _isolated_python(core_hash, _ACTIVE_LEDGER.scratch_root)
        parent = _site_root(core_hash, _ACTIVE_LEDGER.scratch_root) / "secret-surface"
        try: parent.mkdir(mode=0o700)
        except FileExistsError: pass
        root_path = parent / "events"
        try: root_path.mkdir(mode=0o700)
        except FileExistsError: pass
        if any(root_path.iterdir()):
            raise ValueError("PRIVATE_FAULT_SECRET_EVENT_ROOT_NOT_EMPTY")
        entry = root_path.lstat()
        identity = ChallengerReplacementEventRootIdentity(
            str(root_path), entry.st_dev, entry.st_ino, entry.st_uid, "0700")
        event_bytes = None
        with open_challenger_replacement_event_root(identity) as event_root:
            payload = canonical_json({"response_class": transport.response_class,
                "response_sha256": transport.response_sha256,
                "request_id": request.request_id}).encode()
            event = build_challenger_replacement_event(sequence=1,
                event_type="BINANCE_REQUEST_SEND_STARTED", slot_id="secret-surface",
                worker_id="v077-private-fault", recorded_at=_NOW,
                previous_event_hash="0" * 64, payload_bytes=payload,
                plan_hash="1" * 64, build_identity_hash="2" * 64,
                event_root=event_root)
            publish_challenger_replacement_event(event_root, event)
            replay = replay_challenger_replacement_events(event_root)
            if len(replay.events) != 1: raise ValueError
            event_bytes = replay.events[0].final_bytes
        artifact = canonical_json({"event_sha256": _digest(event_bytes),
            "response_class": transport.response_class,
            "response_sha256": transport.response_sha256}).encode()
        surfaces = {"logs": (logs_out.getvalue() + logs_err.getvalue()).encode(),
            "exceptions": exception.encode(), "events": event_bytes,
            "artifacts": artifact}
        sentinels = tuple(value.encode() for value in (api_key, secret, signature))
        counts = {name: sum(value.count(item) for item in sentinels)
                  for name, value in surfaces.items()}
        if any(counts.values()): raise ValueError
        for candidate in root_path.iterdir():
            candidate_entry = candidate.lstat()
            if (not stat.S_ISREG(candidate_entry.st_mode)
                    or candidate_entry.st_uid != os.getuid()
                    or candidate_entry.st_nlink != 1): raise ValueError
            candidate.unlink()
        return {"occurrences": counts,
            "surface_sha256": {name: _digest(value) for name, value in surfaces.items()},
            "surface_sizes": {name: len(value) for name, value in surfaces.items()},
            "actual_transport_executed": connection.attempts == 1,
            "actual_event_replayed": event_bytes == event.final_bytes,
            "_fault_state_identity": {
                "event_before_or_null": "0" * 64,
                "event_after_or_null": replay.last_event_hash,
            }}
    if case_id == "RESTART_PRESERVES_STOP":
        return _fresh_record("RESTART_PRESERVES_STOP",
                             _inventory()[1])
    return _reconciliation_probe(case_id)

def _fresh_probe(case_id):
    if case_id == "PRIVATE_FRESH_PROCESS_STOP_REPLAY":
        return _stop_probe("STOP_REPLACEMENT_NO_GAP")
    activation, preflight, projection, intent = _private_context()
    attempt = _prepare_attempt(intent=intent, projection=projection,
        preflight=preflight, activation=activation)
    fixture = json.loads(resources.files("crypto_quant").joinpath(
        "fixtures", "challenger-replacement-v077", "account-preflight-flat.json").read_text())
    events = apply_binance_order_observation(attempt=attempt,
        order=_body({"code": -1007, "msg": "timeout"}), trades=(),
        account=_body(fixture["SPOT_ACCOUNT"]))
    if events[-1]["event_type"] != "BINANCE_ORDER_UNKNOWN": raise ValueError
    return events[-1]

def _bind(function, case_id):
    def probe(): return function(case_id)
    probe.__name__ = "private_probe_" + case_id.lower()
    return probe

_GROUPS = (
    (_protocol_probe, CASE_IDS[0:7] + CASE_IDS[11:13] + CASE_IDS[17:22]),
    (_transport_probe, CASE_IDS[7:11] + CASE_IDS[13:17] + (CASE_IDS[34],)),
    (_lifecycle_probe, CASE_IDS[22:30] + (CASE_IDS[37],)),
    (_preflight_probe, CASE_IDS[38:42]),
    (_stop_probe, CASE_IDS[42:48]),
    (_canary_probe, CASE_IDS[52:54] + CASE_IDS[55:57]),
    (_fresh_probe, CASE_IDS[35:37]),
    (_reconciliation_probe, CASE_IDS[30:34] + CASE_IDS[48:52]),
    (_misc_probe, (CASE_IDS[54],) + CASE_IDS[57:]),
)
_FUNCTIONS = {case_id: function for function, cases in _GROUPS for case_id in cases}
if frozenset(_FUNCTIONS) != frozenset(CASE_IDS): raise RuntimeError("PRIVATE_FAULT_CASE_MAP_INVALID")
PROBES = MappingProxyType({case_id: _bind(_FUNCTIONS[case_id], case_id)
                          for case_id in CASE_IDS})

def _inventory():
    values = [{"path": path, "sha256": _digest((_ROOT / path).read_bytes())}
              for path in EXECUTABLE_INVENTORY_PATHS]
    return values, _digest(values)

def _fixture_bytes(case_id, core_hash, observed_inputs, subprocess_record):
    fixture = "spot-hmac-known-answer.json" if _FUNCTIONS[case_id] is _protocol_probe else (
        "account-preflight-flat.json" if _FUNCTIONS[case_id] in {
            _lifecycle_probe, _preflight_probe, _fresh_probe, _reconciliation_probe} else None)
    fixtures = {} if fixture is None else {fixture: resources.files("crypto_quant").joinpath(
        "fixtures", "challenger-replacement-v077", fixture).read_text()}
    transition = None if subprocess_record is None else {
        key: subprocess_record[key] for key in (
            "process_boundary_replay", "event_count_before", "event_count_after",
            "last_event_hash_before", "event_semantic_sha256_before",
            "event_semantic_sha256_after")}
    return canonical_json({"case_id": case_id, "probe_id": PROBES[case_id].__name__,
        "executable_core_hash": core_hash, "package_fixtures": fixtures,
        "observed_boundary_inputs": observed_inputs,
        "runtime_state_transition_or_null": transition}).encode()

def _git_identity():
    def read(argument):
        return subprocess.run(["git", "rev-parse", argument], cwd=_ROOT,
            check=True, capture_output=True, text=True).stdout.strip()
    checkpoint, tree = read("HEAD"), read("HEAD^{tree}")
    for path in EXECUTABLE_INVENTORY_PATHS:
        result = subprocess.run(["git", "show", checkpoint + ":" + path],
            cwd=_ROOT, check=False, capture_output=True)
        if result.returncode != 0 or result.stdout != (_ROOT / path).read_bytes():
            raise ValueError("PRIVATE_FAULT_EXECUTABLE_CHECKPOINT_DIRTY")
    return checkpoint, tree

def _foundation(data):
    if not isinstance(data, bytes) or not data: raise ValueError
    if _digest(data) != _V076_ARTIFACT_SHA256: raise ValueError
    value = _strict_json_bytes(data)
    loaded = load_challenger_replacement_fault_matrix_bytes(data,
        build_identity=value["build_identity"],
        runtime_core_identity=value["runtime_core_identity"])
    if (loaded["status"] != "FAULT_MATRIX_PASSED"
            or value["receipt_id"] != _V076_RECEIPT_ID
            or value["receipt_hash"] != _V076_RECEIPT_HASH): raise ValueError
    return {"artifact_sha256": _digest(data), "receipt_id": value["receipt_id"],
            "receipt_hash": value["receipt_hash"],
            "build_identity": deepcopy(value["build_identity"])}

def _temporary_base():
    candidate = (Path("/private/tmp") if sys.platform == "darwin"
                 and Path("/private/tmp").is_dir() else Path(tempfile.gettempdir()))
    if not stat.S_ISDIR(candidate.lstat().st_mode):
        raise ValueError("PRIVATE_FAULT_TEMP_BASE_UNTRUSTED")
    return candidate

def _site_root(core_hash, scratch_root):
    return Path(scratch_root) / ("isolated-python-" + core_hash[:16])

def _isolated_python(core_hash, scratch_root):
    root = _site_root(core_hash, scratch_root)
    created = False
    try:
        root.mkdir(mode=0o700); created = True
    except FileExistsError:
        pass
    entry = root.lstat()
    if (not stat.S_ISDIR(entry.st_mode) or entry.st_uid != os.getuid()
            or stat.S_IMODE(entry.st_mode) != 0o700):
        raise ValueError("PRIVATE_FAULT_VENV_UNTRUSTED")
    executable = root / "bin" / "python"
    if created:
        venv.EnvBuilder(with_pip=False, system_site_packages=False).create(root)
    elif not executable.exists():
        raise ValueError("PRIVATE_FAULT_VENV_UNTRUSTED")
    configuration = root / "pyvenv.cfg"
    if (not configuration.is_file()
            or "include-system-site-packages = false\n"
            not in configuration.read_text()):
        raise ValueError("PRIVATE_FAULT_VENV_UNTRUSTED")
    try: resolved = executable.resolve(strict=True)
    except (OSError, RuntimeError): raise ValueError("PRIVATE_FAULT_VENV_UNTRUSTED")
    if not resolved.samefile(Path(sys.executable).resolve()):
        raise ValueError("PRIVATE_FAULT_VENV_UNTRUSTED")
    site_packages = root / "lib" / ("python%d.%d" % sys.version_info[:2]) / "site-packages"
    import_roots = (_ROOT / "src", Path(jsonschema.__file__).resolve().parents[1])
    if any((base / name).exists() for base in import_roots
           for name in ("sitecustomize.py", "usercustomize.py")):
        raise ValueError("PRIVATE_FAULT_VENV_UNTRUSTED")
    paths = ("\n".join(str(path) for path in import_roots) + "\n").encode()
    path = site_packages / "crypto-quant-v077-private-fault.pth"
    try: pentry = path.lstat()
    except FileNotFoundError: pentry = None
    if pentry is not None:
        if (not stat.S_ISREG(pentry.st_mode) or pentry.st_uid != os.getuid()
                or stat.S_IMODE(pentry.st_mode) != 0o600 or pentry.st_nlink != 1):
            raise ValueError("PRIVATE_FAULT_VENV_UNTRUSTED")
        if path.read_bytes() != paths: raise ValueError("PRIVATE_FAULT_VENV_UNTRUSTED")
    elif created:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            if os.write(descriptor, paths) != len(paths): raise OSError
            os.fsync(descriptor)
        finally: os.close(descriptor)
    else:
        raise ValueError("PRIVATE_FAULT_VENV_UNTRUSTED")
    if {item.name for item in site_packages.iterdir()} != {path.name}:
        raise ValueError("PRIVATE_FAULT_VENV_UNTRUSTED")
    return [str(executable), "-I", "-m", __name__]

def _fresh_record(case_id, core_hash):
    _observe("fresh_processes")
    _observe_input("fresh_process_request", {"case_id": case_id,
        "executable_core_hash": core_hash})
    if _ACTIVE_LEDGER.scratch_root is None:
        raise RuntimeError("PRIVATE_FAULT_SCRATCH_ROOT_REQUIRED")
    command = _isolated_python(core_hash, _ACTIVE_LEDGER.scratch_root)
    product = ("SPOT" if case_id.endswith("UNKNOWN_REPLAY")
               else "PERPETUAL")
    persistent = _site_root(core_hash, _ACTIVE_LEDGER.scratch_root) / (
        "runtime-" + case_id.lower())
    with _runtime_workspace(product, persistent_parent=persistent) as workspace:
        authority = _runtime_authority(workspace)
        try:
            if product == "SPOT":
                initial, initial_calls = _prepare_spot_unknown(workspace, authority)
            else:
                initial, initial_calls, _old = _prepare_partial_stop(
                    workspace, authority)
        finally:
            authority[1].close()
        before_count, before_hash = _runtime_state_identity(workspace)
        path = Path(workspace.root.path)
        entry = path.lstat()
        argv = command + ["--fresh", case_id, str(path), str(entry.st_dev),
            str(entry.st_ino), str(entry.st_uid), before_hash]
        result = subprocess.run(argv, cwd=str(_temporary_base()),
            stdin=subprocess.DEVNULL, capture_output=True,
            env={"PATH": "/usr/bin:/bin"}, timeout=30)
    if result.returncode != 0: raise ValueError("PRIVATE_FAULT_SUBPROCESS_FAILED")
    value = _strict_json_bytes(result.stdout[:-1]) if result.stdout.endswith(b"\n") else None
    if not isinstance(value, dict) or value.get("case_id") != case_id: raise ValueError
    observed = value["result"]
    result_bytes = canonical_json(observed).encode()
    if (value["result_sha256"] != _digest(result_bytes)
            or value["authority"] != _ZERO
            or value["event_count_before"] != before_count
            or value["last_event_hash_before"] != before_hash):
        raise ValueError("PRIVATE_FAULT_SUBPROCESS_EVIDENCE_INVALID")
    before = observed.get("initial_status", observed.get("status"))
    after = observed.get("recovered_status", observed.get("status"))
    return {"case_id": case_id, "executable": argv[0], "argv": argv,
        "exit_status": result.returncode,
        "stdout_sha256": _digest(result.stdout), "stderr_sha256": _digest(result.stderr),
        "event_identity_sha256": _digest(observed["event_types"]),
        "artifact_identity_sha256": value["result_sha256"],
        "result_bytes_utf8": result_bytes.decode(),
        "result_sha256": value["result_sha256"], "authority": value["authority"],
        "probe_activity": value["probe_activity"],
        "runtime_status_before": before, "runtime_status_after": after,
        "economic_send_count": observed.get("economic_send_count", 0),
        "recovery_send_count": observed.get("recovery_send_count", 0),
        "process_boundary_replay": True,
        "event_count_before": value["event_count_before"],
        "event_count_after": value["event_count_after"],
        "last_event_hash_before": value["last_event_hash_before"],
        "last_event_hash_after": value["last_event_hash_after"],
        "event_semantic_sha256_before": value["event_semantic_sha256_before"],
        "event_semantic_sha256_after": value["event_semantic_sha256_after"]}

def _case(case_id, core_hash, ledger):
    global _ACTIVE_LEDGER
    input_mark = ledger.input_mark()
    before, activity_before = ledger.snapshot(), ledger.activity()
    stdout, stderr = io.StringIO(), io.StringIO()
    _ACTIVE_LEDGER = ledger
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            if case_id.startswith("PRIVATE_FRESH_PROCESS_"):
                subprocess_record = _fresh_record(case_id, core_hash)
                result = _strict_json_bytes(
                    subprocess_record["result_bytes_utf8"].encode())
            else:
                result = PROBES[case_id]()
                subprocess_record = (result if case_id == "RESTART_PRESERVES_STOP"
                                     else None)
    finally: _ACTIVE_LEDGER = None
    fixture = _fixture_bytes(
        case_id, core_hash, ledger.inputs_since(input_mark), subprocess_record)
    state_transition = (result.pop("_fault_state_identity", None)
                        if isinstance(result, dict) else None)
    result_bytes = canonical_json(result).encode()
    state_identity = {"applicability": "STATELESS_NOT_APPLICABLE",
        "event_before_or_null": None, "event_after_or_null": None,
        "artifact_before_or_null": None, "artifact_after_or_null": None}
    if subprocess_record is not None:
        state_identity.update(applicability="PUBLISHED_EVENT_AND_RESULT",
            event_before_or_null=subprocess_record["last_event_hash_before"],
            event_after_or_null=subprocess_record["last_event_hash_after"],
            artifact_after_or_null=subprocess_record["artifact_identity_sha256"])
    elif state_transition is not None:
        state_identity.update(applicability="PUBLISHED_EVENT_ONLY",
            **state_transition)
    elif _FUNCTIONS[case_id] in {_reconciliation_probe, _canary_probe}:
        state_identity.update(applicability="CANONICAL_RESULT_ARTIFACT",
            artifact_after_or_null=_digest(result_bytes))
    record = {"case_id": case_id, "probe_id": PROBES[case_id].__name__, "status": "PASS",
        "fixture_bytes_utf8": fixture.decode(), "fixture_sha256": _digest(fixture),
        "observed_code": result.get("outcome", "RETURNED") if isinstance(result, dict) else "RETURNED",
        "observed_result_bytes_utf8": result_bytes.decode(), "result_sha256": _digest(result_bytes),
        "stdout_sha256": _digest(stdout.getvalue().encode()), "stderr_sha256": _digest(stderr.getvalue().encode()),
        "observed_delta": ledger.delta(before), "observed_activity": ledger.activity_delta(activity_before),
        "subprocess_or_null": subprocess_record, "state_identity": state_identity}
    record["case_hash"] = _digest(record)
    return record

_ATTACHMENT_RECORD_KEYS = (
    frozenset({"device", "inode", "uid", "mode", "nlink", "size", "sha256"}),
    frozenset({"capture_event_sequence", "capture_event_hash", "device", "inode",
               "uid", "mode_octal", "link_count", "event_size", "event_sha256",
               "payload_selector", "decoded_size", "decoded_sha256"}),
)
_CREDENTIAL_REFERENCE_KEYS = frozenset({
    "$schema", "schema_version", "absolute_path", "parent_device",
    "parent_inode", "file_device", "file_inode", "file_sha256",
})
def _semantic_value(value):
    if isinstance(value, list): return [_semantic_value(item) for item in value]
    if not isinstance(value, dict): return value
    keys = frozenset(value)
    if keys in _ATTACHMENT_RECORD_KEYS:
        return {key: ("<OS_ATTACHMENT_COORDINATE>" if key in {"device", "inode"}
                      else _semantic_value(item)) for key, item in value.items()}
    if keys == _CREDENTIAL_REFERENCE_KEYS and value.get("$schema") == (
            "./challenger-replacement-binance-credential-reference-v1.schema.json"):
        variable = {"absolute_path", "parent_device", "parent_inode",
                    "file_device", "file_inode"}
        return {key: ("<OS_ATTACHMENT_COORDINATE>" if key in variable
                      else _semantic_value(item)) for key, item in value.items()}
    return {key: _semantic_value(item) for key, item in value.items()}

def _semantic_fixture(value):
    normalized = _semantic_value(value)
    transition = normalized.get("runtime_state_transition_or_null")
    if isinstance(transition, dict) and "last_event_hash_before" in transition:
        transition["last_event_hash_before"] = "<DERIVED_EVENT_HASH>"
    return normalized

_SUBPROCESS_SEMANTIC_KEYS = (
    "case_id", "executable", "exit_status", "authority", "probe_activity",
    "runtime_status_before", "runtime_status_after", "economic_send_count",
    "recovery_send_count", "process_boundary_replay", "event_count_before",
    "event_count_after", "event_semantic_sha256_before",
    "event_semantic_sha256_after",
)
def _semantic_subprocess(value):
    normalized = {key: _semantic_value(value[key])
                  for key in _SUBPROCESS_SEMANTIC_KEYS}
    normalized["executable"] = "<CAMPAIGN_ISOLATED_PYTHON>"
    return normalized

def _semantic_result(value, case_id):
    if case_id == "RESTART_PRESERVES_STOP":
        return _semantic_subprocess(value)
    normalized = _semantic_value(value)
    if isinstance(normalized, dict) and "last_event_hash" in normalized:
        normalized["last_event_hash"] = "<DERIVED_EVENT_HASH>"
    if (case_id == "SECRET_ABSENT_FROM_LOGS_EXCEPTIONS_EVENTS_ARTIFACTS"
            and isinstance(normalized, dict)
            and frozenset(normalized.get("surface_sha256", {})) == {
                "logs", "exceptions", "events", "artifacts"}):
        normalized["surface_sha256"]["events"] = "<DERIVED_EVENT_HASH>"
        normalized["surface_sha256"]["artifacts"] = "<DERIVED_ARTIFACT_HASH>"
    return normalized

def _semantic_case_projection(case):
    subprocess_record = case["subprocess_or_null"]
    subprocess_semantic = (None if subprocess_record is None
                           else _semantic_subprocess(subprocess_record))
    return {"case_id": case["case_id"], "probe_id": case["probe_id"],
        "status": case["status"], "observed_code": case["observed_code"],
        "fixture": _semantic_fixture(json.loads(case["fixture_bytes_utf8"])),
        "observed_result": _semantic_result(json.loads(
            case["observed_result_bytes_utf8"]), case["case_id"]),
        "observed_delta": deepcopy(case["observed_delta"]),
        "observed_activity": deepcopy(case["observed_activity"]),
        "subprocess_or_null": subprocess_semantic,
        "state_identity_applicability": case["state_identity"]["applicability"]}

def _validator():
    schema = json.loads(resources.files("crypto_quant").joinpath(
        "schemas", _SCHEMA).read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)

def _strict_receipt_bytes(data):
    if not isinstance(data, bytes) or not 0 < len(data) <= 4 * 1024 * 1024:
        raise ValueError("PRIVATE_FAULT_RECEIPT_SIZE_INVALID")
    return _strict_artifact_json_bytes(data)

def _execute_campaign(core_hash):
    def blocked_network(*_args, **_kwargs):
        if _ACTIVE_LEDGER is not None:
            _ACTIVE_LEDGER.block("private_network_requests")
        raise RuntimeError("PRIVATE_FAULT_RELEASE_AUTHORITY_BLOCKED:private_network_requests")
    with tempfile.TemporaryDirectory(
            prefix="cq-v077-private-fault-campaign-",
            dir=_temporary_base()) as directory:
        ledger = _BoundaryLedger(Path(directory))
        with patch.object(socket, "create_connection", side_effect=blocked_network):
            cases = [_case(case_id, core_hash, ledger) for case_id in CASE_IDS]
        authority, activity = ledger.snapshot(), ledger.activity()
    return cases, authority, activity

def _semantic_hashes(cases):
    return [{"case_id": case["case_id"],
             "semantic_hash": _digest(_semantic_case_projection(case))}
            for case in cases]

def run_challenger_replacement_private_fault_matrix(*, v076_fault_receipt_bytes):
    inventory, core_hash = _inventory(); checkpoint, tree = _git_identity()
    foundation = _foundation(v076_fault_receipt_bytes)
    cases, authority, activity = _execute_campaign(core_hash)
    replay_cases, replay_authority, replay_activity = _execute_campaign(core_hash)
    primary_semantics, replay_semantics = (_semantic_hashes(cases),
                                            _semantic_hashes(replay_cases))
    primary_aggregate, replay_aggregate = (_digest(primary_semantics),
                                            _digest(replay_semantics))
    if (primary_semantics != replay_semantics or authority != _ZERO
            or replay_authority != _ZERO or activity != replay_activity):
        raise ValueError("PRIVATE_FAULT_INDEPENDENT_REPLAY_MISMATCH")
    value = {"$schema": "./" + _SCHEMA, "schema_version": "1.0.0",
        "receipt_id": "", "receipt_hash": "0" * 64,
        "executable_checkpoint": checkpoint, "executable_tree": tree,
        "executable_inventory": inventory, "executable_core_hash": core_hash,
        "foundation": foundation, "cases": cases,
        "aggregate_case_hash": _digest([{"case_id": case["case_id"],
            "case_hash": case["case_hash"]} for case in cases]),
        "authority": authority, "probe_activity": activity,
        "independent_replay": {"execution_count": 2,
            "primary_case_semantic_hashes": primary_semantics,
            "independent_case_semantic_hashes": replay_semantics,
            "primary_aggregate_semantic_hash": primary_aggregate,
            "independent_aggregate_semantic_hash": replay_aggregate,
            "authority": replay_authority, "probe_activity": replay_activity,
            "semantic_match": True},
        "status": "PRIVATE_FAULT_MATRIX_PASSED_NOT_ACTIVATED"}
    identity = _digest({key: item for key, item in value.items()
                        if key not in {"receipt_id", "receipt_hash"}})
    value["receipt_id"] = "challenger_replacement_private_fault_matrix_" + identity
    value["receipt_hash"] = artifact_self_hash(value, "receipt_hash")
    if tuple(_validator().iter_errors(value)): raise ValueError("PRIVATE_FAULT_RECEIPT_INVALID")
    return (canonical_json(value) + "\n").encode()

def load_challenger_replacement_private_fault_matrix_bytes(data, *,
        v076_fault_receipt_bytes, expected_executable_checkpoint,
        expected_executable_tree, expected_receipt_sha256):
    try:
        if (not isinstance(data, bytes)
                or not 1 < len(data) <= 4 * 1024 * 1024 + 1
                or not data.endswith(b"\n")
                or not isinstance(expected_receipt_sha256, str)
                or len(expected_receipt_sha256) != 64
                or set(expected_receipt_sha256) - set("0123456789abcdef")
                or _digest(data) != expected_receipt_sha256): raise ValueError
        value = _strict_receipt_bytes(data[:-1])
        if ((canonical_json(value) + "\n").encode() != data
                or tuple(_validator().iter_errors(value))): raise ValueError
        inventory, core_hash = _inventory(); checkpoint, tree = _git_identity()
        if (value["executable_inventory"] != inventory
                or value["executable_core_hash"] != core_hash
                or value["executable_checkpoint"] != checkpoint
                or value["executable_tree"] != tree
                or checkpoint != expected_executable_checkpoint
                or tree != expected_executable_tree
                or value["foundation"] != _foundation(v076_fault_receipt_bytes)
                or tuple(case["case_id"] for case in value["cases"]) != CASE_IDS
                or any(case["probe_id"] != "private_probe_" + case["case_id"].lower()
                       or case["status"] != "PASS" or case["observed_delta"] != _ZERO
                       or case["fixture_sha256"] != _digest(
                           case["fixture_bytes_utf8"].encode())
                       or canonical_json(json.loads(case["fixture_bytes_utf8"])) !=
                           case["fixture_bytes_utf8"]
                       or case["result_sha256"] != _digest(
                           case["observed_result_bytes_utf8"].encode())
                       or canonical_json(json.loads(
                           case["observed_result_bytes_utf8"])) !=
                           case["observed_result_bytes_utf8"]
                       or case["case_hash"] != _digest({key: item for key, item in case.items()
                                                       if key != "case_hash"})
                       for case in value["cases"])
                or value["aggregate_case_hash"] != _digest([{"case_id": case["case_id"],
                    "case_hash": case["case_hash"]} for case in value["cases"]])
                or value["authority"] != _ZERO
                or value["probe_activity"] != {key: sum(
                    case["observed_activity"][key] for case in value["cases"])
                    for key in _ACTIVITY}
                or value["independent_replay"] != {
                    "execution_count": 2,
                    "primary_case_semantic_hashes": _semantic_hashes(value["cases"]),
                    "independent_case_semantic_hashes": _semantic_hashes(value["cases"]),
                    "primary_aggregate_semantic_hash": _digest(
                        _semantic_hashes(value["cases"])),
                    "independent_aggregate_semantic_hash": _digest(
                        _semantic_hashes(value["cases"])),
                    "authority": _ZERO,
                    "probe_activity": value["probe_activity"],
                    "semantic_match": True}
                or value["receipt_id"] != "challenger_replacement_private_fault_matrix_" +
                    _digest({key: item for key, item in value.items()
                             if key not in {"receipt_id", "receipt_hash"}})
                or value["receipt_hash"] != artifact_self_hash(value, "receipt_hash")):
            raise ValueError
        return deepcopy(value)
    except (KeyError, TypeError, UnicodeDecodeError, ValueError) as error:
        raise ValueError("CHALLENGER_REPLACEMENT_PRIVATE_FAULT_RECEIPT_INVALID") from error

def _main():
    global _ACTIVE_LEDGER
    if len(sys.argv) != 8 or sys.argv[1] != "--fresh" or sys.argv[2] not in {
            "PRIVATE_FRESH_PROCESS_UNKNOWN_REPLAY", "PRIVATE_FRESH_PROCESS_STOP_REPLAY",
            "RESTART_PRESERVES_STOP"}:
        raise SystemExit(2)
    case_id = sys.argv[2]
    product = "SPOT" if case_id.endswith("UNKNOWN_REPLAY") else "PERPETUAL"
    identity = ChallengerReplacementEventRootIdentity(
        sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6]), "0700")
    _ACTIVE_LEDGER = _BoundaryLedger()
    def blocked_network(*_args, **_kwargs):
        _ACTIVE_LEDGER.block("private_network_requests")
    try:
        with _reopen_runtime_workspace(product, identity) as workspace:
            before_count, before_hash = _runtime_state_identity(workspace)
            if before_hash != sys.argv[7]:
                raise SystemExit(3)
            before_types = _runtime_event_types(workspace)
            authority_values = _runtime_authority(workspace)
            try:
                with patch.object(socket, "create_connection", side_effect=blocked_network):
                    if product == "SPOT":
                        recovered, calls = _resume_spot_unknown(
                            workspace, authority_values)
                        if "BINANCE_ORDER_UNKNOWN" not in before_types:
                            raise SystemExit(3)
                        result = {"initial_status":
                            "UNRESOLVED_ECONOMIC_ORDER_UNKNOWN",
                            "recovered_status": recovered["status"],
                            "economic_send_count": before_types.count(
                                "BINANCE_REQUEST_SEND_STARTED"),
                            "recovery_send_count": calls.count("SPOT_ORDER_CREATE"),
                            "recovery_endpoints": calls,
                            "event_types": _runtime_event_types(workspace)}
                    else:
                        replayed, calls, old = _resume_partial_stop(
                            workspace, authority_values)
                        if "BINANCE_STOP_RECONCILED" not in before_types:
                            raise SystemExit(3)
                        result = {"status": replayed["status"],
                            "protected_quantity": old["quantity"],
                            "recovery_send_count": sum(
                                endpoint.endswith("CREATE") for endpoint in calls),
                            "transport_endpoints": calls,
                            "event_types": _runtime_event_types(workspace)}
            finally:
                authority_values[1].close()
            after_count, after_hash = _runtime_state_identity(workspace)
            after_types = _runtime_event_types(workspace)
        authority, activity = _ACTIVE_LEDGER.snapshot(), _ACTIVE_LEDGER.activity()
    finally: _ACTIVE_LEDGER = None
    value = {"case_id": case_id, "result": result,
        "result_sha256": _digest(canonical_json(result).encode()),
        "authority": authority, "probe_activity": activity,
        "event_count_before": before_count, "event_count_after": after_count,
        "last_event_hash_before": before_hash,
        "last_event_hash_after": after_hash,
        "event_semantic_sha256_before": _digest(before_types),
        "event_semantic_sha256_after": _digest(after_types)}
    sys.stdout.buffer.write((canonical_json(value) + "\n").encode())

if __name__ == "__main__":
    _main()
