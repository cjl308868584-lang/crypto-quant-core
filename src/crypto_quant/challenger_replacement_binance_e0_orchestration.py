"""Fixed Binance-only E0 orchestration; authority artifacts are mandatory."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from .challenger_replacement_binance_private_lifecycle import (
    build_binance_order_intent_from_opportunity,
)
from .challenger_replacement_binance_private_runtime import (
    run_challenger_replacement_binance_private_intent,
)
from .challenger_replacement_binance_credential import (
    open_binance_credential_capability,
)
from .challenger_replacement_binance_preflight import (
    BinanceAccountPreflightError, evaluate_binance_account_preflight,
    open_binance_account_preflight_capability,
)
from .challenger_replacement_binance_private_contract import (
    load_binance_account_approval_bytes, load_binance_private_activation_bytes,
)
from .challenger_replacement_binance_private_protocol import (
    build_binance_private_request, observe_binance_server_time,
)
from .challenger_replacement_binance_private_runtime import (
    _public_time_transport,
)
from .challenger_replacement_binance_private_transport import (
    execute_binance_private_request,
)
from .challenger_replacement_install_trust import (
    _close_descriptor, _open_directory, _publish_contract_exact,
    _read_published_exact,
)
from .challenger_replacement_v3_activation_install import (
    open_fixed_v3_installed_sources,
)


class BinanceE0OrchestrationError(ValueError):
    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code


_PRIVATE_ROOT = Path(
    "/Users/chenm4/Library/Application Support/CryptoQuant/"
    "challenger-replacement-binance-e0-v1"
)
_AUTHORITY_FILES = (
    "activation.json", "credential-reference.json",
)
_PREFLIGHT_ROOT = _PRIVATE_ROOT / "preflights"
_PREFLIGHT_ENDPOINTS = {
    "API_RESTRICTIONS": {}, "API_TRADING_STATUS": {},
    "SPOT_ACCOUNT": {}, "SPOT_OPEN_ORDERS": {"symbol": "ETHUSDT"},
    "FUTURES_POSITION_MODE": {}, "FUTURES_MULTI_ASSET_MODE": {},
    "FUTURES_SYMBOL_CONFIG": {"symbol": "ETHUSDT"},
    "FUTURES_ACCOUNT": {}, "FUTURES_POSITION": {"symbol": "ETHUSDT"},
    "FUTURES_OPEN_ORDERS": {"symbol": "ETHUSDT"},
    "FUTURES_OPEN_ALGO_ORDERS": {"symbol": "ETHUSDT"},
}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _reference_bytes(path, parent, opened, body):
    import hashlib
    return (json.dumps({
        "schema_version": "1.0.0", "absolute_path": str(path),
        "parent_device": parent.st_dev, "parent_inode": parent.st_ino,
        "file_device": opened.st_dev, "file_inode": opened.st_ino,
        "file_sha256": hashlib.sha256(body).hexdigest(),
    }, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _open_current_preflight(build_identity, activation, credential):
    parent_fd = -1
    valid = []
    try:
        parent_fd, parent = _open_directory(_PREFLIGHT_ROOT, exact_mode=0o700)
        for name in sorted(os.listdir(parent_fd)):
            if (not name.startswith("binance_account_preflight_")
                    or not name.endswith(".json")):
                raise BinanceE0OrchestrationError(
                    "BINANCE_E0_PREFLIGHT_ROOT_UNTRUSTED"
                )
            found = _read_published_exact(parent_fd, name)
            if found is None:
                raise BinanceE0OrchestrationError(
                    "BINANCE_E0_PREFLIGHT_ROOT_UNTRUSTED"
                )
            reference = _reference_bytes(
                _PREFLIGHT_ROOT / name, parent, found[1], found[0],
            )
            capability = open_binance_account_preflight_capability(
                reference_bytes=reference, expected_uid=os.getuid(),
                build_identity=build_identity,
            )
            try:
                capability.load(
                    activation=activation,
                    credential_identity=credential.identity, now=_now(),
                )
            except BinanceAccountPreflightError as error:
                capability.close()
                if error.reason_code == "BINANCE_ACCOUNT_PREFLIGHT_AUTHORITY_INVALID":
                    continue
                raise
            valid.append(capability)
        if len(valid) != 1:
            raise BinanceE0OrchestrationError(
                "BINANCE_E0_CURRENT_PREFLIGHT_NOT_UNIQUE"
            )
        return valid.pop()
    finally:
        for capability in valid:
            capability.close()
        if parent_fd >= 0:
            _close_descriptor(parent_fd)


@contextmanager
def _open_fixed_private_authority(build_identity):
    root_fd = -1
    credential = preflight = None
    primary = None
    try:
        root_fd, _opened = _open_directory(_PRIVATE_ROOT, exact_mode=0o700)
        loaded = []
        for name in _AUTHORITY_FILES:
            found = _read_published_exact(root_fd, name)
            if found is None:
                raise BinanceE0OrchestrationError(
                    "BINANCE_E0_AUTHORITY_ARTIFACTS_REQUIRED"
                )
            loaded.append(found[0])
        activation = load_binance_private_activation_bytes(
            loaded[0], build_identity=build_identity, now=_now(),
        )
        try:
            reference = json.loads(loaded[1].decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise BinanceE0OrchestrationError(
                "BINANCE_E0_AUTHORITY_ARTIFACTS_INVALID"
            ) from error
        credential = open_binance_credential_capability(
            reference=reference, expected_owner_uid=os.getuid(),
        )
        preflight = _open_current_preflight(
            build_identity, activation, credential,
        )
        yield activation, credential, preflight
    except BinanceE0OrchestrationError as error:
        primary = error
        raise
    except (OSError, TypeError, ValueError) as error:
        primary = BinanceE0OrchestrationError(
            "BINANCE_E0_AUTHORITY_ARTIFACTS_INVALID"
        )
        raise primary from error
    finally:
        for capability in (preflight, credential):
            if capability is not None:
                try:
                    capability.close()
                except BaseException as error:
                    if primary is None:
                        primary = error
        if root_fd >= 0:
            _close_descriptor(root_fd, primary)
        if primary is not None and not isinstance(
                primary, BinanceE0OrchestrationError):
            raise primary


def run_fixed_binance_private_opportunity(opportunity_id):
    with open_fixed_v3_installed_sources() as installed:
        with _open_fixed_private_authority(
                installed["build_identity"]) as authority:
            activation, credential, preflight = authority
            state = installed["state"]
            try:
                slot = state.replay()["opportunities"][opportunity_id]
            except (AttributeError, KeyError, TypeError) as error:
                raise BinanceE0OrchestrationError(
                    "BINANCE_E0_OPPORTUNITY_NOT_OBSERVED"
                ) from error
            intent = build_binance_order_intent_from_opportunity(
                slot=slot, activation=activation, attempt_ordinal=1,
            )
            return run_challenger_replacement_binance_private_intent(
                state=state, event_root=installed["event_root"], intent=intent,
                preflight_capability=preflight, activation=activation,
                credential=credential,
                build_identity=installed["build_identity"],
            )


def run_fixed_binance_account_preflight():
    with open_fixed_v3_installed_sources() as installed:
        build = installed["build_identity"]
        root_fd = -1
        credential = None
        try:
            root_fd, _root = _open_directory(_PRIVATE_ROOT, exact_mode=0o700)
            values = []
            for name in ("activation.json", "credential-reference.json",
                         "account-approval.json"):
                found = _read_published_exact(root_fd, name)
                if found is None:
                    raise BinanceE0OrchestrationError(
                        "BINANCE_E0_AUTHORITY_ARTIFACTS_REQUIRED"
                    )
                values.append(found[0])
            activation = load_binance_private_activation_bytes(
                values[0], build_identity=build, now=_now(),
            )
            credential = open_binance_credential_capability(
                reference=json.loads(values[1]), expected_owner_uid=os.getuid(),
            )
            approval = load_binance_account_approval_bytes(
                values[2], now=_now(),
            )
            responses = {}
            for endpoint, parameters in _PREFLIGHT_ENDPOINTS.items():
                product = ("PERPETUAL" if endpoint.startswith("FUTURES_")
                           else "SPOT")
                evidence = observe_binance_server_time(
                    product=product, transport=_public_time_transport,
                    local_clock=lambda: int(
                        datetime.now(timezone.utc).timestamp() * 1000
                    ),
                )
                request = build_binance_private_request(
                    endpoint, parameters, timestamp_ms=evidence.server_time_ms,
                )
                result = execute_binance_private_request(
                    request, credential=credential, activation=activation,
                    expected_build_identity=build, now=_now(),
                )
                if result.response_class != "QUERY_SUCCEEDED":
                    raise BinanceE0OrchestrationError(
                        "BINANCE_E0_PREFLIGHT_QUERY_FAILED"
                    )
                responses[endpoint] = result.body
            body = evaluate_binance_account_preflight(
                responses=responses, account_approval=approval,
                credential_identity=credential.identity,
                build_identity=build, now=_now(),
            )
            document = json.loads(body)
            name = document["preflight_id"] + ".json"
            outcome = _publish_contract_exact(_PREFLIGHT_ROOT, name, body)
            return {"status": "BINANCE_ACCOUNT_PREFLIGHT_VERIFIED_FLAT",
                    "preflight_id": document["preflight_id"],
                    "publication": outcome[0]}
        except BinanceE0OrchestrationError:
            raise
        except (KeyError, OSError, TypeError, ValueError) as error:
            raise BinanceE0OrchestrationError(
                "BINANCE_E0_PREFLIGHT_FAILED"
            ) from error
        finally:
            if credential is not None:
                credential.close()
            if root_fd >= 0:
                _close_descriptor(root_fd)


def run_fixed_binance_emergency_stop(opportunity_id):
    with open_fixed_v3_installed_sources() as installed:
        with _open_fixed_private_authority(
                installed["build_identity"]) as authority:
            activation, credential, preflight = authority
            state = installed["state"]
            try:
                slot = state.replay()["opportunities"][opportunity_id]
                private = slot["private"]
                if (private.get("product") != "PERPETUAL"
                        or private.get("action") != "OPEN_SHORT"):
                    raise ValueError
                intent = build_binance_order_intent_from_opportunity(
                    slot=slot, activation=activation, attempt_ordinal=1,
                )
                return run_challenger_replacement_binance_private_intent(
                    state=state, event_root=installed["event_root"],
                    intent=intent, preflight_capability=preflight,
                    activation=activation, credential=credential,
                    build_identity=installed["build_identity"],
                )
            except BinanceE0OrchestrationError:
                raise
            except (AttributeError, KeyError, TypeError, ValueError) as error:
                raise BinanceE0OrchestrationError(
                    "BINANCE_E0_EMERGENCY_STOP_NOT_AUTHORIZED"
                ) from error
