"""Run the frozen v0.65 fixture in one isolated one-engine process."""

from __future__ import annotations

import argparse
import copy
import ctypes
import errno
import hashlib
import json
import os
import secrets
import socket
import stat
import sys
import warnings
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping


_MAX_BYTES = 4 * 1024 * 1024
_ZERO = "0" * 64
_FIXTURE_HASH = "8f9047ebd6271d2dc9f043aedacb065355cd24e507e29c4a11aa747f1531109c"
_ENGINE_CLAIMED = False
_SAFETY_COUNTERS = {
    "credential_reads": 0,
    "network_requests": 0,
    "live_adapter_imports": 0,
    "broker_requests": 0,
    "real_orders": 0,
    "production_state_writes": 0,
    "second_engine_creations": 0,
}
_SCENARIOS = (
    "IMMEDIATE_FULL",
    "PARTIAL_THEN_FULL",
    "BELOW_MINIMUM_REJECTED",
    "FRESH_PROCESS_REPLAY",
)
_FORBIDDEN_ENV_PARTS = (
    "API_KEY",
    "API_SECRET",
    "ACCESS_KEY",
    "SECRET_KEY",
    "PRIVATE_KEY",
    "TOKEN",
    "PASSWORD",
    "PROXY",
    "BINANCE",
    "BYBIT",
    "COINBASE",
    "KRAKEN",
    "BROKER",
    "AWS_",
    "AZURE_",
    "GOOGLE_APPLICATION_CREDENTIALS",
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash(value: Mapping[str, Any], *excluded: str) -> str:
    material = copy.deepcopy(dict(value))
    for field in excluded:
        if field in material:
            material[field] = _ZERO if not field.endswith("_id") else field.removesuffix("_id") + "_" + _ZERO
    return hashlib.sha256(_canonical(material)).hexdigest()


def _event(sequence: int, kind: str, **values: str) -> dict[str, Any]:
    result: dict[str, Any] = {"sequence": sequence, "kind": kind, **values, "event_hash": _ZERO}
    result["event_hash"] = _hash(result, "event_hash")
    return result


def _decimal(value: Decimal | str | int) -> str:
    decimal = value if isinstance(value, Decimal) else Decimal(str(value))
    if decimal == 0:
        return "0"
    rendered = format(decimal, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _strict_json(body: bytes) -> dict[str, Any]:
    if not 1 <= len(body) <= _MAX_BYTES or not body.endswith(b"\n"):
        raise RuntimeError("INPUT_NOT_CANONICAL")

    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise RuntimeError("INPUT_DUPLICATE_KEY")
            result[key] = value
        return result

    try:
        payload = json.loads(body, object_pairs_hook=pairs, parse_float=lambda _: (_ for _ in ()).throw(RuntimeError("FLOAT_FORBIDDEN")))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise RuntimeError("INPUT_JSON_INVALID") from error
    if not isinstance(payload, dict) or body != _canonical(payload) + b"\n":
        raise RuntimeError("INPUT_NOT_CANONICAL")
    return payload


def _require_flags(*names: str) -> int:
    flags = 0
    for name in names:
        value = getattr(os, name, 0)
        if not isinstance(value, int) or value == 0:
            raise RuntimeError("PLATFORM_UNSUPPORTED")
        flags |= value
    return flags


def _open_root(path: Path) -> int:
    value = path.lstat()
    if not stat.S_ISDIR(value.st_mode) or value.st_uid != os.geteuid() or stat.S_IMODE(value.st_mode) != 0o700:
        raise RuntimeError("ROOT_INVALID")
    fd = os.open(path, os.O_RDONLY | _require_flags("O_DIRECTORY", "O_NOFOLLOW"))
    attached = os.fstat(fd)
    if (attached.st_dev, attached.st_ino) != (value.st_dev, value.st_ino):
        os.close(fd)
        raise RuntimeError("ROOT_REPLACED")
    return fd


def _read_owner_file(root_fd: int, name: str) -> bytes:
    if Path(name).name != name:
        raise RuntimeError("INPUT_PATH_INVALID")
    fd = os.open(name, os.O_RDONLY | _require_flags("O_NOFOLLOW", "O_NONBLOCK"), dir_fd=root_fd)
    try:
        value = os.fstat(fd)
        if (
            not stat.S_ISREG(value.st_mode)
            or value.st_uid != os.geteuid()
            or value.st_nlink != 1
            or stat.S_IMODE(value.st_mode) != 0o600
            or not 1 <= value.st_size <= _MAX_BYTES
        ):
            raise RuntimeError("INPUT_PATH_INVALID")
        body = bytearray()
        while len(body) < value.st_size:
            chunk = os.read(fd, value.st_size - len(body))
            if not chunk:
                break
            body.extend(chunk)
        if len(body) != value.st_size:
            raise RuntimeError("INPUT_READ_FAILED")
        return bytes(body)
    finally:
        os.close(fd)


def _validate_environment() -> None:
    for key in os.environ:
        upper = key.upper()
        if any(part in upper for part in _FORBIDDEN_ENV_PARTS):
            _SAFETY_COUNTERS["credential_reads"] += 1
            raise RuntimeError("CREDENTIAL_ENV_FORBIDDEN")


def _verify_request(request: Mapping[str, Any]) -> None:
    expected_keys = {
        "$schema", "schema_version", "request_id", "request_hash", "plan_id", "plan_hash",
        "supply_chain_receipt_id", "supply_chain_receipt_hash", "fixture_id", "fixture_hash",
        "instrument", "starting_state", "decision_authority", "closed_bars", "scenarios", "authority_counters",
    }
    if (
        set(request) != expected_keys
        or request.get("$schema") != "./nautilus-sandbox-request-v2.schema.json"
        or request.get("schema_version") != "2.0.0"
        or request.get("fixture_id") != "ethusdt_4h_v2"
        or request.get("fixture_hash") != _FIXTURE_HASH
        or request.get("authority_counters") != {
            "credential_reads": 0,
            "network_requests": 0,
            "broker_requests": 0,
            "orders_outside_fixture": 0,
            "production_state_writes": 0,
        }
    ):
        raise RuntimeError("REQUEST_CONTRACT_INVALID")
    try:
        fixture_material = {key: request[key] for key in ("instrument", "starting_state", "decision_authority", "closed_bars", "scenarios")}
        fixture_hash = hashlib.sha256(_canonical(fixture_material)).hexdigest()
        digest = _hash(request, "request_id", "request_hash")
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError("REQUEST_CONTRACT_INVALID") from error
    if (
        fixture_hash != _FIXTURE_HASH
        or request.get("request_hash") != digest
        or request.get("request_id") != "nautilus_v065_request_" + digest
        or [item.get("scenario") for item in request.get("scenarios", [])] != list(_SCENARIOS)
    ):
        raise RuntimeError("REQUEST_CONTRACT_INVALID")


def _install_network_guard() -> None:
    original_socket = socket.socket

    class ForbiddenSocket(original_socket):
        def __new__(cls, *_args: Any, **_kwargs: Any) -> Any:
            _SAFETY_COUNTERS["network_requests"] += 1
            raise RuntimeError("NETWORK_FORBIDDEN")

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        _SAFETY_COUNTERS["network_requests"] += 1
        raise RuntimeError("NETWORK_FORBIDDEN")

    socket.socket = ForbiddenSocket
    socket.create_connection = forbidden  # type: ignore[assignment]
    socket.getaddrinfo = forbidden  # type: ignore[assignment]


def _claim_engine() -> None:
    global _ENGINE_CLAIMED
    if _ENGINE_CLAIMED:
        _SAFETY_COUNTERS["second_engine_creations"] += 1
        raise RuntimeError("SECOND_ENGINE_FORBIDDEN")
    _ENGINE_CLAIMED = True


def _timestamp_ns(value: str) -> int:
    from datetime import datetime

    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1_000_000_000)


def _run_engine(request: Mapping[str, Any]) -> list[dict[str, Any]]:
    _claim_engine()
    from nautilus_trader.backtest.engine import BacktestEngine
    from nautilus_trader.config import BacktestEngineConfig, LoggingConfig
    from nautilus_trader.model.currencies import ETH, USDT
    from nautilus_trader.model.data import QuoteTick
    from nautilus_trader.model.enums import AccountType, OmsType, OrderSide
    from nautilus_trader.model.identifiers import InstrumentId, Symbol, TraderId, Venue
    from nautilus_trader.model.instruments import CurrencyPair
    from nautilus_trader.model.objects import Money, Price, Quantity
    from nautilus_trader.trading.strategy import Strategy

    engine = BacktestEngine(
        BacktestEngineConfig(
            trader_id=TraderId("V065-001"),
            logging=LoggingConfig(log_level="ERROR", bypass_logging=True),
            run_analysis=False,
        )
    )
    try:
        contexts = []
        for index, scenario in enumerate(request["scenarios"], 1):
            venue = Venue(f"V065{index}")
            instrument_id = InstrumentId.from_str(f"ETHUSDT.{venue}")
            instrument = CurrencyPair(
                instrument_id=instrument_id,
                raw_symbol=Symbol("ETHUSDT"),
                base_currency=ETH,
                quote_currency=USDT,
                price_precision=2,
                size_precision=4,
                price_increment=Price.from_str("0.01"),
                size_increment=Quantity.from_str("0.0001"),
                ts_event=0,
                ts_init=0,
                max_quantity=Quantity.from_str("1000.0000"),
                min_quantity=Quantity.from_str("0.0001"),
                max_notional=Money.from_str("100000000.00 USDT"),
                min_notional=Money.from_str("5.00 USDT"),
                max_price=Price.from_str("1000000.00"),
                min_price=Price.from_str("0.01"),
                maker_fee=Decimal("0.001"),
                taker_fee=Decimal("0.001"),
            )
            quantity_text = f"{Decimal(str(scenario['order_intent']['quantity'])):.4f}"

            class FixtureStrategy(Strategy):
                def __init__(self, fixed_instrument_id: Any, fixed_quantity: str) -> None:
                    super().__init__()
                    self.fixed_instrument_id = fixed_instrument_id
                    self.fixed_quantity = fixed_quantity
                    self.submitted = False

                def on_start(self) -> None:
                    self.subscribe_quote_ticks(self.fixed_instrument_id)

                def on_quote_tick(self, _tick: QuoteTick) -> None:
                    if self.submitted:
                        return
                    self.submitted = True
                    order = self.order_factory.market(
                        instrument_id=self.fixed_instrument_id,
                        order_side=OrderSide.BUY,
                        quantity=Quantity.from_str(self.fixed_quantity),
                    )
                    self.submit_order(order)

            engine.add_venue(
                venue=venue,
                oms_type=OmsType.NETTING,
                account_type=AccountType.CASH,
                starting_balances=[
                    Money.from_str("1000.00 USDT"),
                    Money.from_str("0.00000000 ETH"),
                ],
                use_market_order_acks=True,
                liquidity_consumption=scenario["scenario"] == "PARTIAL_THEN_FULL",
            )
            engine.add_instrument(instrument)
            ticks = []
            for market_event in scenario["events"]:
                if market_event["kind"] != "BBO":
                    continue
                timestamp = _timestamp_ns(str(market_event["occurred_at"]))
                ticks.append(
                    QuoteTick(
                        instrument_id=instrument_id,
                        bid_price=Price.from_str(
                            f"{Decimal(str(market_event['bid'])):.2f}"
                        ),
                        ask_price=Price.from_str(
                            f"{Decimal(str(market_event['ask'])):.2f}"
                        ),
                        bid_size=Quantity.from_str(
                            f"{Decimal(str(market_event['bid_size'])):.4f}"
                        ),
                        ask_size=Quantity.from_str(
                            f"{Decimal(str(market_event['ask_size'])):.4f}"
                        ),
                        ts_event=timestamp,
                        ts_init=timestamp,
                    )
                )
            engine.add_data(ticks)
            engine.add_strategy(FixtureStrategy(instrument_id, quantity_text))
            last_bid = Price.from_str(
                f"{Decimal(str([item for item in scenario['events'] if item['kind'] == 'BBO'][-1]['bid'])):.2f}"
            )
            contexts.append((scenario, venue, instrument_id, quantity_text, last_bid))
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=r"Timestamp\.utcnow is deprecated and will be removed in a future version\..*",
            )
            engine.run()

        results = []
        for scenario, venue, instrument_id, quantity_text, last_bid in contexts:
            orders = engine.cache.orders(instrument_id=instrument_id)
            account = engine.cache.account_for_venue(venue=venue)
            if len(orders) != 1 or account is None:
                raise RuntimeError("ENGINE_ACCOUNT_OR_ORDER_INVALID")
            order = orders[0]
            fills = [
                item
                for item in order.events
                if item.__class__.__name__ == "OrderFilled"
            ]
            rejected = any(
                item.__class__.__name__ in ("OrderDenied", "OrderRejected")
                for item in order.events
            )
            requested = Decimal(quantity_text)
            filled = order.filled_qty.as_decimal()
            fees = sum(
                (item.commission.as_decimal() for item in fills), Decimal(0)
            )
            average = Decimal(0) if order.avg_px is None else order.avg_px
            ending_cash_money = account.balance_total(USDT)
            realized_money = engine.portfolio.realized_pnl(
                instrument_id,
                account_id=account.id,
                target_currency=USDT,
            )
            unrealized_money = engine.portfolio.unrealized_pnl(
                instrument_id,
                price=last_bid,
                account_id=account.id,
                target_currency=USDT,
            )
            total_money = engine.portfolio.total_pnl(
                instrument_id,
                price=last_bid,
                account_id=account.id,
                target_currency=USDT,
            )
            if ending_cash_money is None or unrealized_money is None or total_money is None:
                raise RuntimeError("ENGINE_ACCOUNTING_UNAVAILABLE")
            ending_position = engine.portfolio.net_position(
                instrument_id,
                account_id=account.id,
            )
            realized_value = Decimal(0) if realized_money is None else realized_money.as_decimal()
            status = (
                "FILLED"
                if filled == requested
                else "REJECTED_MIN_NOTIONAL"
                if rejected and filled == 0
                else "ENGINE_RESULT_INVALID"
            )
            if status == "ENGINE_RESULT_INVALID":
                raise RuntimeError(status)
            events = [
                _event(
                    1,
                    "ORDER_ACCEPTED" if filled else "ORDER_REJECTED",
                    status=status,
                )
            ]
            for sequence, fill in enumerate(fills, 2):
                events.append(
                    _event(
                        sequence,
                        "FILL",
                        price=_decimal(fill.last_px.as_decimal()),
                        quantity=_decimal(fill.last_qty.as_decimal()),
                        fee_usdt=_decimal(fill.commission.as_decimal()),
                    )
                )
            results.append(
                {
                    "scenario": scenario["scenario"],
                    "scenario_hash": scenario["scenario_hash"],
                    "status": status,
                    "requested_quantity": _decimal(requested),
                    "filled_quantity": _decimal(filled),
                    "average_price": _decimal(average),
                    "fee_usdt": _decimal(fees),
                    "ending_cash_usdt": _decimal(ending_cash_money.as_decimal()),
                    "ending_position_eth": _decimal(ending_position),
                    "realized_pnl_usdt": _decimal(realized_value),
                    "unrealized_pnl_usdt": _decimal(unrealized_money.as_decimal()),
                    "net_pnl_usdt": _decimal(total_money.as_decimal()),
                    "events": events,
                }
            )
        return results
    finally:
        engine.dispose()


def _rename_noreplace(root_fd: int, source: str, destination: str) -> None:
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        primitive = getattr(library, "renameatx_np", None)
        if primitive is None:
            raise RuntimeError("PLATFORM_UNSUPPORTED")
        outcome = primitive(root_fd, source.encode(), root_fd, destination.encode(), 0x00000004)
    elif sys.platform.startswith("linux"):
        primitive = getattr(library, "renameat2", None)
        if primitive is None:
            raise RuntimeError("PLATFORM_UNSUPPORTED")
        outcome = primitive(root_fd, source.encode(), root_fd, destination.encode(), 1)
    else:
        raise RuntimeError("PLATFORM_UNSUPPORTED")
    if outcome != 0:
        error = ctypes.get_errno()
        if error == errno.EEXIST:
            raise RuntimeError("RESULT_EXISTS")
        raise OSError(error, os.strerror(error))


def _publish(root_fd: int, name: str, body: bytes) -> None:
    if Path(name).name != name or not 1 <= len(body) <= _MAX_BYTES:
        raise RuntimeError("RESULT_PATH_INVALID")
    try:
        os.stat(name, dir_fd=root_fd, follow_symlinks=False)
    except FileNotFoundError:
        pass
    else:
        raise RuntimeError("RESULT_EXISTS")
    staging = f".nautilus-v065-{secrets.token_hex(16)}.staging"
    fd = os.open(staging, os.O_CREAT | os.O_EXCL | os.O_RDWR | _require_flags("O_NOFOLLOW"), 0o600, dir_fd=root_fd)
    try:
        offset = 0
        while offset < len(body):
            try:
                written = os.write(fd, body[offset:])
            except InterruptedError:
                continue
            if written <= 0:
                raise RuntimeError("RESULT_WRITE_FAILED")
            offset += written
        os.lseek(fd, 0, os.SEEK_SET)
        readback = bytearray()
        while len(readback) < len(body):
            chunk = os.read(fd, len(body) - len(readback))
            if not chunk:
                break
            readback.extend(chunk)
        if bytes(readback) != body:
            raise RuntimeError("RESULT_READBACK_FAILED")
        os.fsync(fd)
        _rename_noreplace(root_fd, staging, name)
        value = os.fstat(fd)
        attached = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        if (value.st_dev, value.st_ino) != (attached.st_dev, attached.st_ino):
            raise RuntimeError("RESULT_REPLACED")
        os.fsync(root_fd)
    finally:
        os.close(fd)


def _parent_main(request_path: Path, receipt_path: Path, result_path: Path) -> int:
    _validate_environment()
    parents = {path.absolute().parent for path in (request_path, receipt_path, result_path)}
    if len(parents) != 1:
        raise RuntimeError("ROOT_MISMATCH")
    root_path = parents.pop()
    root_fd = _open_root(root_path)
    try:
        request = _strict_json(_read_owner_file(root_fd, request_path.name))
        receipt = _strict_json(_read_owner_file(root_fd, receipt_path.name))
        _verify_request(request)
        if set(receipt) != {"receipt_id", "receipt_hash"}:
            raise RuntimeError("RECEIPT_INVALID")
        if (
            receipt["receipt_id"] != request.get("supply_chain_receipt_id")
            or receipt["receipt_hash"] != request.get("supply_chain_receipt_hash")
        ):
            raise RuntimeError("RECEIPT_OR_REQUEST_BINDING_INVALID")
        try:
            os.stat(result_path.name, dir_fd=root_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise RuntimeError("RESULT_EXISTS")
        _install_network_guard()
        results = _run_engine(request)
        first, replay = results[0], results[3]
        semantic_keys = (
            "status", "requested_quantity", "filled_quantity", "average_price", "fee_usdt",
            "ending_cash_usdt", "ending_position_eth", "realized_pnl_usdt", "unrealized_pnl_usdt", "net_pnl_usdt",
        )
        if any(first[key] != replay[key] for key in semantic_keys):
            raise RuntimeError("FRESH_PROCESS_REPLAY_MISMATCH")
        result: dict[str, Any] = {
            "$schema": "./nautilus-sandbox-result-v2.schema.json",
            "schema_version": "2.0.0",
            "result_id": "nautilus_v065_result_" + _ZERO,
            "result_hash": _ZERO,
            "request_id": request["request_id"],
            "request_hash": request["request_hash"],
            "engine": "NAUTILUS_TRADER_1.230.0",
            "scenario_results": results,
            "fresh_process_replay_verified": True,
            "safety_counters": copy.deepcopy(_SAFETY_COUNTERS),
        }
        digest = _hash(result, "result_id", "result_hash")
        result["result_id"] = "nautilus_v065_result_" + digest
        result["result_hash"] = digest
        _publish(root_fd, result_path.name, _canonical(result) + b"\n")
        return 0
    finally:
        os.close(root_fd)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="crypto_quant_nautilus_v065.runner")
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    return parser


def main() -> int:
    try:
        arguments = _parser().parse_args()
        return _parent_main(arguments.request, arguments.receipt, arguments.result)
    except BaseException as error:
        sys.stderr.write(f"{error}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
