"""Strict loader for committed, fixture-only Binance simulation inputs.

The module consumes complete canonical bytes.  It has no path, clock, market,
account, Broker, order, credential, install, or production-state capability.
"""

import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from functools import lru_cache
from importlib import resources
from typing import Any, Dict, Mapping

from jsonschema import Draft202012Validator

from .canonical import canonical_decimal, canonical_json, stable_id, utc_datetime
from .challenger_replacement_plan import (
    ChallengerReplacementPlanError,
    _strict_json_bytes,
)
from .challenger_replacement_plan_v3 import (
    challenger_replacement_plan_v3_reasons,
)
from .challenger_replacement_opportunities import opportunity_id_for
from .challenger_replacement_simulation_contract import (
    build_challenger_replacement_simulation_contract,
)
from .decimal_math import as_decimal
from .errors import CanonicalizationError, ContractError
from .evidence import artifact_self_hash
from .instruments import InstrumentMetadata, MarketType


_SCHEMA = "challenger-replacement-binance-simulation-input-v1.schema.json"
_MAX_BYTES = 2 * 1024 * 1024
_BUILD_KEYS = {
    "release_tag",
    "peeled_commit",
    "package_version",
    "manifest_version",
    "build_input_tree_hash",
    "manifest_hash",
    "manifest_file_sha256",
}
_AUTHORITY = {
    "network_requests": 0,
    "account_requests": 0,
    "broker_requests": 0,
    "orders_submitted_to_venue": 0,
    "credentials_used": False,
    "production_state_writes": 0,
}
_FIXTURE_BUILD_VERSIONS = {
    ("v0.71.0-fixture", "0.71.0", "1.65.0"),
    ("v0.72.0-fixture", "0.72.0", "1.66.0"),
}


class ChallengerReplacementSimulationInputError(ValueError):
    """The committed simulation input failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _invalid(reason="CHALLENGER_REPLACEMENT_SIMULATION_INPUT_INVALID"):
    raise ChallengerReplacementSimulationInputError(reason)


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _canonical_time(value: object) -> datetime:
    if not isinstance(value, str):
        _invalid()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _invalid()
    if parsed.tzinfo is None or utc_datetime(parsed) != value:
        _invalid()
    return parsed.astimezone(timezone.utc)


def _canonical_decimal(value: object) -> Decimal:
    if not isinstance(value, str):
        _invalid()
    parsed = as_decimal(value)
    if canonical_decimal(parsed) != value:
        _invalid()
    return parsed


def _valid_build_identity(value: object) -> bool:
    if not isinstance(value, Mapping) or set(value) != _BUILD_KEYS:
        return False
    hashes = (
        ("peeled_commit", 40),
        ("build_input_tree_hash", 64),
        ("manifest_hash", 64),
        ("manifest_file_sha256", 64),
    )
    for key, size in hashes:
        item = value.get(key)
        if (
            not isinstance(item, str)
            or len(item) != size
            or any(character not in "0123456789abcdef" for character in item)
        ):
            return False
    version = (
        value.get("release_tag"),
        value.get("package_version"),
        value.get("manifest_version"),
    )
    return version in _FIXTURE_BUILD_VERSIONS


def _metadata(payload: object, *, market_type: MarketType) -> InstrumentMetadata:
    if not isinstance(payload, Mapping):
        _invalid()
    expected_id = "BINANCE:%s:ETHUSDT" % market_type.value
    try:
        metadata = InstrumentMetadata(
            schema_version=payload["schema_version"],
            instrument_id=payload["instrument_id"],
            exchange=payload["exchange"],
            market_type=MarketType(payload["market_type"]),
            symbol=payload["symbol"],
            base_asset=payload["base_asset"],
            quote_asset=payload["quote_asset"],
            settlement_asset=payload["settlement_asset"],
            effective_from=_canonical_time(payload["effective_from"]),
            effective_to_or_null=(
                None
                if payload["effective_to_or_null"] is None
                else _canonical_time(payload["effective_to_or_null"])
            ),
            price_tick=_canonical_decimal(payload["price_tick"]),
            quantity_step=_canonical_decimal(payload["quantity_step"]),
            min_quantity=_canonical_decimal(payload["min_quantity"]),
            max_quantity=_canonical_decimal(payload["max_quantity"]),
            min_notional=_canonical_decimal(payload["min_notional"]),
            contract_multiplier=_canonical_decimal(payload["contract_multiplier"]),
            supported_order_types=tuple(payload["supported_order_types"]),
            supported_time_in_force=tuple(payload["supported_time_in_force"]),
            supports_reduce_only=payload["supports_reduce_only"],
            supports_stop_market=payload["supports_stop_market"],
            maker_fee=_canonical_decimal(payload["maker_fee"]),
            taker_fee=_canonical_decimal(payload["taker_fee"]),
            metadata_source=payload["metadata_source"],
        )
    except (KeyError, TypeError, ValueError, CanonicalizationError, ContractError):
        _invalid()
    canonical_payload = json.loads(canonical_json(metadata.business_payload()))
    if (
        dict(payload) != canonical_payload
        or metadata.market_type is not market_type
        or metadata.instrument_id != expected_id
        or metadata.exchange != "BINANCE"
        or metadata.symbol != "ETHUSDT"
    ):
        _invalid()
    return metadata


def _validate_bars(bars: object, scheduled_for: datetime) -> None:
    if not isinstance(bars, list) or len(bars) != 21:
        _invalid()
    previous_close = None
    for bar in bars:
        if not isinstance(bar, Mapping) or set(bar) != {
            "open_time",
            "close_boundary",
            "open",
            "high",
            "low",
            "close",
        }:
            _invalid()
        opened = _canonical_time(bar["open_time"])
        closed = _canonical_time(bar["close_boundary"])
        if closed - opened != timedelta(hours=4) or (
            previous_close is not None and opened != previous_close
        ):
            _invalid()
        opened_price = _canonical_decimal(bar["open"])
        high = _canonical_decimal(bar["high"])
        low = _canonical_decimal(bar["low"])
        close = _canonical_decimal(bar["close"])
        if (
            min(opened_price, high, low, close) <= 0
            or low > min(opened_price, close)
            or high < max(opened_price, close)
            or high < low
        ):
            _invalid()
        previous_close = closed
    if previous_close != scheduled_for:
        _invalid()


def _validate_quotes(quotes: object) -> None:
    if not isinstance(quotes, Mapping) or set(quotes) != {"spot", "perpetual"}:
        _invalid()
    for product, keys in (
        ("spot", {"bid", "ask", "last"}),
        ("perpetual", {"bid", "ask", "last", "mark"}),
    ):
        quote = quotes.get(product)
        if not isinstance(quote, Mapping) or set(quote) != keys:
            _invalid()
        bid = _canonical_decimal(quote["bid"])
        ask = _canonical_decimal(quote["ask"])
        last = _canonical_decimal(quote["last"])
        if bid <= 0 or bid > last or last > ask:
            _invalid()
        if product == "perpetual" and _canonical_decimal(quote["mark"]) <= 0:
            _invalid()


def _validate_document(
    document: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    contract: Mapping[str, Any],
    build_identity: Mapping[str, Any],
    opportunity_id: str,
) -> None:
    if tuple(_validator().iter_errors(document)):
        _invalid()
    if challenger_replacement_plan_v3_reasons(plan):
        _invalid()
    if contract != build_challenger_replacement_simulation_contract(plan=plan):
        _invalid()
    if not _valid_build_identity(build_identity):
        _invalid()
    if document["build_identity"] != dict(build_identity):
        _invalid()
    expected_plan = {"plan_id": plan["plan_id"], "plan_hash": plan["plan_hash"]}
    expected_contract = {
        "contract_id": contract["contract_id"],
        "contract_hash": contract["contract_hash"],
    }
    if (
        document["plan"] != expected_plan
        or document["simulation_contract"] != expected_contract
        or not isinstance(opportunity_id, str)
        or not opportunity_id
    ):
        _invalid()

    opportunity = document["opportunity"]
    scheduled = _canonical_time(opportunity["scheduled_for"])
    opened = _canonical_time(opportunity["capture_open"])
    closed = _canonical_time(opportunity["capture_close"])
    observed = _canonical_time(opportunity["observed_at"])
    try:
        canonical_opportunity_id = opportunity_id_for(
            opportunity["scheduled_for"]
        )
    except ValueError:
        _invalid()
    if (
        opportunity["opportunity_id"] != opportunity_id
        or opportunity_id != canonical_opportunity_id
        or opened != scheduled + timedelta(minutes=2)
        or closed != scheduled + timedelta(minutes=10)
        or not opened <= observed <= closed
    ):
        _invalid()
    _validate_bars(document["bars"], scheduled)

    instruments = document["instruments"]
    if not isinstance(instruments, Mapping) or set(instruments) != {
        "spot",
        "perpetual",
    }:
        _invalid()
    metadata = {}
    for product, market_type in (
        ("spot", MarketType.SPOT),
        ("perpetual", MarketType.USDT_PERP),
    ):
        record = instruments.get(product)
        if not isinstance(record, Mapping) or set(record) != {
            "metadata",
            "metadata_hash",
        }:
            _invalid()
        item = _metadata(record["metadata"], market_type=market_type)
        try:
            item.assert_effective(observed)
        except ContractError:
            _invalid()
        if record["metadata_hash"] != item.metadata_hash:
            _invalid()
        metadata[product] = item
    if (
        metadata["spot"].taker_fee != _canonical_decimal(contract["spot_taker_fee"])
        or metadata["perpetual"].taker_fee
        != _canonical_decimal(contract["perpetual_taker_fee"])
    ):
        _invalid("SIMULATION_CONTRACT_METADATA_CONFLICT")

    _validate_quotes(document["quotes"])
    funding = document["funding"]
    if not isinstance(funding, Mapping) or set(funding) != {
        "boundary_at_or_null",
        "rate_or_null",
    }:
        _invalid()
    boundary = funding["boundary_at_or_null"]
    rate = funding["rate_or_null"]
    if (boundary is None) != (rate is None):
        _invalid()
    if boundary is not None:
        if _canonical_time(boundary) != scheduled:
            _invalid()
        _canonical_decimal(rate)
    if document["authority"] != _AUTHORITY:
        _invalid()

    expected_id = stable_id(
        "challenger_replacement_binance_simulation_input",
        {
            "plan": document["plan"],
            "simulation_contract": document["simulation_contract"],
            "build_identity": document["build_identity"],
            "opportunity": document["opportunity"],
        },
    )
    if (
        document["input_id"] != expected_id
        or document["input_hash"] != artifact_self_hash(document, "input_hash")
    ):
        _invalid()


def load_challenger_replacement_binance_simulation_input_bytes(
    data: bytes,
    *,
    plan,
    contract,
    build_identity,
    opportunity_id,
) -> Dict[str, Any]:
    """Replay one complete canonical fixture input against frozen identities."""

    if not isinstance(data, bytes) or not 0 < len(data) <= _MAX_BYTES:
        _invalid("CHALLENGER_REPLACEMENT_SIMULATION_INPUT_BYTES_INVALID")
    try:
        document = _strict_json_bytes(data)
        if not isinstance(document, Mapping):
            raise TypeError("input must be an object")
        if data != canonical_json(document).encode("utf-8"):
            _invalid("CHALLENGER_REPLACEMENT_SIMULATION_INPUT_BYTES_INVALID")
        _validate_document(
            document,
            plan=plan,
            contract=contract,
            build_identity=build_identity,
            opportunity_id=opportunity_id,
        )
        return copy.deepcopy(dict(document))
    except ChallengerReplacementSimulationInputError:
        raise
    except (
        ChallengerReplacementPlanError,
        CanonicalizationError,
        ContractError,
        KeyError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as error:
        raise ChallengerReplacementSimulationInputError(
            "CHALLENGER_REPLACEMENT_SIMULATION_INPUT_BYTES_INVALID"
        ) from error
