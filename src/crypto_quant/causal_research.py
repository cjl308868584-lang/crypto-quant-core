"""Event-time-causal archive features and conservative 24h LONG labels."""

import json
import os
from bisect import bisect_right
from datetime import datetime, timedelta, timezone
from decimal import Context, Decimal, ROUND_CEILING, ROUND_FLOOR, localcontext
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence, Tuple

from jsonschema import Draft202012Validator

from .canonical import (
    business_hash,
    canonical_decimal,
    canonical_json,
    stable_id,
    utc_datetime,
)
from .evidence import artifact_self_hash
from .research_execution import execution_source_hash
from .research_corpus import _publish_exact, _strict_json_bytes


_SCHEMA = "causal-feature-label-dataset-v1.schema.json"
_ZERO_HASH = "0" * 64
_CONTEXT = Context(prec=50)
_FOUR_HOURS = timedelta(hours=4)
_ONE_MINUTE = timedelta(minutes=1)
_FEATURE_NAMES = (
    "eth_log_return_5",
    "eth_sma20_distance",
    "eth_annualized_volatility_20",
    "eth_mean_range_ratio_6",
    "eth_taker_buy_quote_ratio_6",
    "btc_log_return_5",
    "btc_sma20_distance",
    "eth_mark_basis",
    "eth_latest_funding_rate",
)
_REFERENCE_NOTIONAL = Decimal("1000")
_QUANTITY_STEP = Decimal("0.0001")
_PRICE_TICK = Decimal("0.01")
_SLIPPAGE = Decimal("0.001")
_TAKER_FEE = Decimal("0.0015")
_WARNINGS = (
    "EVENT_TIME_CAUSALITY_DOES_NOT_PROVE_HISTORICAL_INGESTION_AVAILABILITY",
    "ONE_MINUTE_WORST_BAR_FILLS_ARE_PROXIES_NOT_REAL_FILLS",
    "LONG_ONLY_SHORT_NOT_EVALUATED",
    "NO_PROFITABILITY_CLAIM",
)


class CausalResearchError(ValueError):
    """The sources, feature path, label path, or artifact failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _utc(value: object) -> Tuple[datetime, str]:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise CausalResearchError("CAUSAL_RESEARCH_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CausalResearchError("CAUSAL_RESEARCH_TIME_INVALID") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise CausalResearchError("CAUSAL_RESEARCH_TIME_INVALID")
    rendered = utc_datetime(parsed)
    return parsed, rendered


def _decimal(value: object, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str):
        raise CausalResearchError("CAUSAL_RESEARCH_DECIMAL_INVALID")
    try:
        parsed = Decimal(value)
    except Exception as error:
        raise CausalResearchError("CAUSAL_RESEARCH_DECIMAL_INVALID") from error
    if not parsed.is_finite() or (positive and parsed <= 0):
        raise CausalResearchError("CAUSAL_RESEARCH_DECIMAL_INVALID")
    return parsed


def _series(
    facts: Sequence[Mapping[str, Any]],
    *,
    family: str,
    symbol: str,
) -> Tuple[Mapping[str, Any], ...]:
    if not isinstance(facts, Sequence) or not facts:
        raise CausalResearchError("CAUSAL_RESEARCH_SERIES_INVALID")
    values = tuple(facts)
    times = []
    for fact in values:
        if (
            not isinstance(fact, Mapping)
            or fact.get("data_family") != family
            or fact.get("symbol") != symbol
        ):
            raise CausalResearchError("CAUSAL_RESEARCH_SERIES_INVALID")
        opened, _ = _utc(fact.get("open_time"))
        closed, _ = _utc(fact.get("close_time"))
        if closed <= opened or closed > opened + _FOUR_HOURS:
            raise CausalResearchError("CAUSAL_RESEARCH_SERIES_INVALID")
        for field in ("open", "high", "low", "close"):
            _decimal(fact.get(field), positive=True)
        times.append(opened)
    if (
        times != sorted(times)
        or len(times) != len(set(times))
        or any(right - left != _FOUR_HOURS for left, right in zip(times, times[1:]))
    ):
        raise CausalResearchError("CAUSAL_RESEARCH_SERIES_INVALID")
    return values


def _funding_series(
    facts: Sequence[Mapping[str, Any]],
) -> Tuple[Tuple[datetime, Mapping[str, Any]], ...]:
    values = []
    for fact in facts:
        if (
            not isinstance(fact, Mapping)
            or fact.get("data_family") != "FUNDING_RATE"
            or fact.get("symbol") != "ETHUSDT"
        ):
            raise CausalResearchError("CAUSAL_RESEARCH_FUNDING_INVALID")
        event, _ = _utc(fact.get("event_time"))
        _decimal(fact.get("funding_rate"))
        values.append((event, fact))
    if (
        not values
        or values != sorted(values, key=lambda item: item[0])
        or len({item[0] for item in values}) != len(values)
    ):
        raise CausalResearchError("CAUSAL_RESEARCH_FUNDING_INVALID")
    return tuple(values)


def _feature_schema() -> Dict[str, Any]:
    contract = {
        "feature_schema_version": "CAUSAL_ARCHIVE_FEATURES_V1",
        "ordered_feature_names": list(_FEATURE_NAMES),
        "feature_count": len(_FEATURE_NAMES),
        "missing_value_policy": "FAIL_CLOSED_NO_IMPUTATION",
        "causality_policy": "SOURCE_EVENT_TIME_NOT_AFTER_DECISION_TIME",
    }
    return {
        "feature_schema_version": contract["feature_schema_version"],
        "feature_schema_hash": business_hash(contract),
        "ordered_feature_names": contract["ordered_feature_names"],
        "feature_count": contract["feature_count"],
        "missing_value_policy": contract["missing_value_policy"],
        "causality_policy": contract["causality_policy"],
    }


def _label_policy() -> Dict[str, Any]:
    contract = {
        "label_policy_version": "SPOT_LONG_24H_1M_WORST_BAR_V1",
        "direction": "LONG",
        "horizon_hours": 24,
        "minimum_hold_hours": 8,
        "reference_notional_usdt": "1000",
        "quantity_step_eth": "0.0001",
        "price_tick_usdt": "0.01",
        "slippage_rate_per_side": "0.001",
        "taker_fee_rate_per_side": "0.0015",
        "fill_policy": "OFFICIAL_1M_WORST_BAR_PLUS_10BPS_V1",
    }
    return {
        "label_policy_version": contract["label_policy_version"],
        "label_policy_hash": business_hash(contract),
        **{key: value for key, value in contract.items() if key != "label_policy_version"},
    }


def _mean(values: Sequence[Decimal]) -> Decimal:
    if not values:
        raise CausalResearchError("CAUSAL_RESEARCH_FEATURE_INVALID")
    return sum(values, Decimal("0")) / Decimal(len(values))


def _sample_volatility(closes: Sequence[Decimal]) -> Decimal:
    if len(closes) != 21:
        raise CausalResearchError("CAUSAL_RESEARCH_FEATURE_INVALID")
    with localcontext(_CONTEXT):
        returns = [
            (closes[index] / closes[index - 1]).ln()
            for index in range(1, len(closes))
        ]
        mean = _mean(returns)
        variance = sum(
            (value - mean) ** 2 for value in returns
        ) / Decimal(len(returns) - 1)
        return variance.sqrt() * Decimal(6 * 365).sqrt()


def _feature_values(
    *,
    eth: Sequence[Mapping[str, Any]],
    btc: Sequence[Mapping[str, Any]],
    mark_by_open: Mapping[str, Mapping[str, Any]],
    funding: Sequence[Tuple[datetime, Mapping[str, Any]]],
    funding_times: Sequence[datetime],
    index: int,
) -> Tuple[Tuple[str, ...], str]:
    if index < 20 or index >= len(eth) or index >= len(btc):
        raise CausalResearchError("CAUSAL_RESEARCH_FEATURE_INVALID")
    current = eth[index]
    if btc[index]["open_time"] != current["open_time"]:
        raise CausalResearchError("CAUSAL_RESEARCH_ALIGNMENT_INVALID")
    mark = mark_by_open.get(current["open_time"])
    if mark is None:
        raise CausalResearchError("CAUSAL_RESEARCH_ALIGNMENT_INVALID")
    decision, _ = _utc(current["close_time"])
    feature_events = [
        _utc(current["close_time"])[0],
        _utc(btc[index]["close_time"])[0],
        _utc(mark["close_time"])[0],
    ]
    funding_index = bisect_right(funding_times, decision) - 1
    if funding_index < 0:
        raise CausalResearchError("CAUSAL_RESEARCH_FUNDING_MISSING")
    funding_event, funding_fact = funding[funding_index]
    feature_events.append(funding_event)
    if max(feature_events) > decision:
        raise CausalResearchError("CAUSAL_RESEARCH_LOOKAHEAD")
    with localcontext(_CONTEXT):
        eth_closes = [
            _decimal(row["close"], positive=True) for row in eth[index - 20 : index + 1]
        ]
        btc_closes = [
            _decimal(row["close"], positive=True) for row in btc[index - 20 : index + 1]
        ]
        ranges = [
            (
                _decimal(row["high"], positive=True)
                - _decimal(row["low"], positive=True)
            )
            / _decimal(row["close"], positive=True)
            for row in eth[index - 5 : index + 1]
        ]
        quote_volume = sum(
            (_decimal(row["quote_asset_volume"]) for row in eth[index - 5 : index + 1]),
            Decimal("0"),
        )
        taker_quote = sum(
            (
                _decimal(row["taker_buy_quote_asset_volume"])
                for row in eth[index - 5 : index + 1]
            ),
            Decimal("0"),
        )
        if quote_volume <= 0:
            raise CausalResearchError("CAUSAL_RESEARCH_FEATURE_INVALID")
        values = (
            (eth_closes[-1] / eth_closes[-6]).ln(),
            eth_closes[-1] / _mean(eth_closes[:-1]) - Decimal("1"),
            _sample_volatility(eth_closes),
            _mean(ranges),
            taker_quote / quote_volume,
            (btc_closes[-1] / btc_closes[-6]).ln(),
            btc_closes[-1] / _mean(btc_closes[:-1]) - Decimal("1"),
            _decimal(mark["close"], positive=True) / eth_closes[-1]
            - Decimal("1"),
            _decimal(funding_fact["funding_rate"]),
        )
    rendered = tuple(canonical_decimal(value) for value in values)
    if len(rendered) != len(_FEATURE_NAMES):
        raise CausalResearchError("CAUSAL_RESEARCH_FEATURE_INVALID")
    return rendered, utc_datetime(max(feature_events))


def _next_minute(close_time: str) -> datetime:
    parsed, _ = _utc(close_time)
    return (parsed + _ONE_MINUTE).replace(second=0, microsecond=0)


def _round_up(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_CEILING) * step


def _round_down(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step


def causal_dataset_hash(dataset: Mapping[str, Any]) -> str:
    return artifact_self_hash(dataset, "dataset_hash")


def feature_input_facts_root_hash(
    *,
    eth_spot_facts: Sequence[Mapping[str, Any]],
    btc_context_facts: Sequence[Mapping[str, Any]],
    eth_mark_facts: Sequence[Mapping[str, Any]],
    eth_funding_facts: Sequence[Mapping[str, Any]],
) -> str:
    return business_hash(
        {
            "eth_spot_facts": list(eth_spot_facts),
            "btc_context_facts": list(btc_context_facts),
            "eth_mark_facts": list(eth_mark_facts),
            "eth_funding_facts": list(eth_funding_facts),
        }
    )


def build_causal_feature_label_dataset(
    *,
    eth_spot_facts: Sequence[Mapping[str, Any]],
    btc_context_facts: Sequence[Mapping[str, Any]],
    eth_mark_facts: Sequence[Mapping[str, Any]],
    eth_funding_facts: Sequence[Mapping[str, Any]],
    execution_sources: Sequence[Mapping[str, Any]],
    source_roots: Mapping[str, str],
    recorded_at: str,
) -> Dict[str, Any]:
    """Build non-overlapping LONG episodes from event-time-causal inputs."""

    _, recorded_text = _utc(recorded_at)
    if set(source_roots) != {
        "corpus_plan_hash",
        "corpus_snapshot_hash",
        "corpus_repair_bundle_hash",
        "execution_source_root_hash",
        "feature_input_facts_root_hash",
    } or any(
        not isinstance(value, str) or len(value) != 64
        for value in source_roots.values()
    ):
        raise CausalResearchError("CAUSAL_RESEARCH_SOURCE_ROOTS_INVALID")
    eth = _series(eth_spot_facts, family="KLINES", symbol="ETHUSDT")
    btc = _series(btc_context_facts, family="KLINES", symbol="BTCUSDT")
    mark = _series(
        eth_mark_facts,
        family="MARK_PRICE_KLINES",
        symbol="ETHUSDT",
    )
    if len(eth) != len(btc) or len(eth) != len(mark):
        raise CausalResearchError("CAUSAL_RESEARCH_ALIGNMENT_INVALID")
    mark_by_open = {row["open_time"]: row for row in mark}
    funding = _funding_series(eth_funding_facts)
    funding_times = tuple(item[0] for item in funding)
    if source_roots["feature_input_facts_root_hash"] != (
        feature_input_facts_root_hash(
            eth_spot_facts=eth_spot_facts,
            btc_context_facts=btc_context_facts,
            eth_mark_facts=eth_mark_facts,
            eth_funding_facts=eth_funding_facts,
        )
    ):
        raise CausalResearchError("CAUSAL_RESEARCH_FACT_ROOT_MISMATCH")
    execution_items = []
    execution_rows = {}
    for source in execution_sources:
        if (
            not isinstance(source, Mapping)
            or source.get("source_hash") != execution_source_hash(source)
            or source.get("formal_pit_eligibility")
            != "INELIGIBLE_ARCHIVE_REPLAY"
            or source.get("quality_eligibility")
            not in (
                "FORMAL_COMPLETE",
                "FORMAL_COMPLETE_WITH_EXPLICIT_DAILY_REPAIRS",
                "RESEARCH_REQUIRED_ROWS_COMPLETE_WITH_SOURCE_GAPS",
            )
        ):
            raise CausalResearchError("CAUSAL_RESEARCH_EXECUTION_SOURCE_INVALID")
        period = source["request"]["period"]
        execution_items.append(
            {"period": period, "source_hash": source["source_hash"]}
        )
        for row in source["selected_rows"]:
            if row["open_time"] in execution_rows:
                raise CausalResearchError(
                    "CAUSAL_RESEARCH_EXECUTION_SOURCE_INVALID"
                )
            execution_rows[row["open_time"]] = row
    execution_items.sort(key=lambda item: item["period"])
    if business_hash(execution_items) != source_roots["execution_source_root_hash"]:
        raise CausalResearchError("CAUSAL_RESEARCH_EXECUTION_ROOT_MISMATCH")

    feature_schema = _feature_schema()
    label_policy = _label_policy()
    samples = []
    index = 20
    while index < len(eth) - 6:
        current = _decimal(eth[index]["close"], positive=True)
        prior_sma = _mean(
            [
                _decimal(row["close"], positive=True)
                for row in eth[index - 20 : index]
            ]
        )
        if current <= prior_sma:
            index += 1
            continue
        exit_index = None
        exit_reason = "VERTICAL_24H_EXIT"
        for candidate in range(index + 2, min(index + 7, len(eth))):
            candidate_close = _decimal(
                eth[candidate]["close"],
                positive=True,
            )
            candidate_sma = _mean(
                [
                    _decimal(row["close"], positive=True)
                    for row in eth[candidate - 20 : candidate]
                ]
            )
            if candidate_close <= candidate_sma:
                exit_index = candidate
                exit_reason = "SMA20_EXIT_AFTER_MIN_HOLD"
                break
        if exit_index is None:
            exit_index = index + 6
        feature_values, max_feature_event = _feature_values(
            eth=eth,
            btc=btc,
            mark_by_open=mark_by_open,
            funding=funding,
            funding_times=funding_times,
            index=index,
        )
        _, decision_time = _utc(eth[index]["close_time"])
        entry_open = _next_minute(decision_time)
        _, exit_decision = _utc(eth[exit_index]["close_time"])
        exit_open = _next_minute(exit_decision)
        entry_text = utc_datetime(entry_open)
        exit_text = utc_datetime(exit_open)
        entry_row = execution_rows.get(entry_text)
        exit_row = execution_rows.get(exit_text)
        if entry_row is None or exit_row is None:
            raise CausalResearchError(
                "CAUSAL_RESEARCH_REQUIRED_EXECUTION_MINUTE_MISSING"
            )
        decision, _ = _utc(decision_time)
        exit_decision_value, _ = _utc(exit_decision)
        if (
            entry_open <= decision
            or exit_open <= exit_decision_value
            or not 8 <= (exit_index - index) * 4 <= 24
        ):
            raise CausalResearchError("CAUSAL_RESEARCH_LABEL_TIME_INVALID")
        with localcontext(_CONTEXT):
            entry_fill = _round_up(
                _decimal(entry_row["high"], positive=True)
                * (Decimal("1") + _SLIPPAGE),
                _PRICE_TICK,
            )
            exit_fill = _round_down(
                _decimal(exit_row["low"], positive=True)
                * (Decimal("1") - _SLIPPAGE),
                _PRICE_TICK,
            )
            quantity = _round_down(
                _REFERENCE_NOTIONAL / entry_fill,
                _QUANTITY_STEP,
            )
            if quantity <= 0 or exit_fill <= 0:
                raise CausalResearchError("CAUSAL_RESEARCH_LABEL_INVALID")
            entry_notional = entry_fill * quantity
            exit_notional = exit_fill * quantity
            entry_fee = entry_notional * _TAKER_FEE
            exit_fee = exit_notional * _TAKER_FEE
            gross = (exit_fill - entry_fill) * quantity
            net = gross - entry_fee - exit_fee
            realized = net / _REFERENCE_NOTIONAL
        feature_vector_hash = business_hash(
            {
                "feature_schema_hash": feature_schema["feature_schema_hash"],
                "decision_time": decision_time,
                "ordered_feature_names": list(_FEATURE_NAMES),
                "feature_values": list(feature_values),
            }
        )
        label_payload = {
            "label_policy_hash": label_policy["label_policy_hash"],
            "entry_source_row_hash": entry_row["source_row_hash"],
            "exit_source_row_hash": exit_row["source_row_hash"],
            "entry_fill_price": canonical_decimal(entry_fill),
            "exit_fill_price": canonical_decimal(exit_fill),
            "filled_quantity": canonical_decimal(quantity),
            "entry_fee_usdt": canonical_decimal(entry_fee),
            "exit_fee_usdt": canonical_decimal(exit_fee),
            "gross_pnl_usdt": canonical_decimal(gross),
            "net_pnl_usdt": canonical_decimal(net),
            "realized_net_return_24h": canonical_decimal(realized),
            "y_take": 1 if realized > 0 else 0,
        }
        sample_identity = {
            "decision_time": decision_time,
            "feature_vector_hash": feature_vector_hash,
            "label_hash": business_hash(label_payload),
        }
        samples.append(
            {
                "sample_id": stable_id("causal_sample", sample_identity),
                "direction": "LONG",
                "decision_time": decision_time,
                "entry_open_time": entry_text,
                "exit_decision_time": exit_decision,
                "exit_open_time": exit_text,
                "label_end_time_exclusive": utc_datetime(
                    exit_open + _ONE_MINUTE
                ),
                "holding_hours": (exit_index - index) * 4,
                "exit_reason": exit_reason,
                "max_feature_event_time": max_feature_event,
                "feature_values": list(feature_values),
                "feature_vector_hash": feature_vector_hash,
                **{
                    key: value
                    for key, value in label_payload.items()
                    if key != "label_policy_hash"
                },
                "label_hash": business_hash(label_payload),
            }
        )
        index = exit_index + 1
    if not samples:
        raise CausalResearchError("CAUSAL_RESEARCH_NO_SAMPLES")
    positive = sum(sample["y_take"] for sample in samples)
    samples_root = business_hash(samples)
    identity = {
        "source_roots": dict(source_roots),
        "feature_schema_hash": feature_schema["feature_schema_hash"],
        "label_policy_hash": label_policy["label_policy_hash"],
        "samples_root_hash": samples_root,
    }
    dataset = {
        "$schema": "./causal-feature-label-dataset-v1.schema.json",
        "schema_version": "1.0.0",
        "dataset_id": stable_id("causal_dataset", identity),
        "dataset_hash": _ZERO_HASH,
        "recorded_at": recorded_text,
        "source_roots": dict(source_roots),
        "feature_schema": feature_schema,
        "label_policy": label_policy,
        "samples_root_hash": samples_root,
        "samples": samples,
        "summary": {
            "direction": "LONG",
            "sample_count": len(samples),
            "positive_label_count": positive,
            "negative_label_count": len(samples) - positive,
            "feature_count": len(_FEATURE_NAMES),
            "first_decision_time": samples[0]["decision_time"],
            "last_decision_time": samples[-1]["decision_time"],
            "required_execution_minute_count": len(execution_rows),
            "missing_required_execution_minute_count": 0,
            "maximum_holding_hours": 24,
        },
        "research_eligibility": "ARCHIVE_CAUSAL_RESEARCH_ONLY",
        "formal_pit_eligibility": "INELIGIBLE_ARCHIVE_REPLAY",
        "profitability_eligibility": "INELIGIBLE",
        "warnings": list(_WARNINGS),
    }
    dataset["dataset_hash"] = causal_dataset_hash(dataset)
    if tuple(_validator().iter_errors(dataset)):
        raise CausalResearchError("CAUSAL_RESEARCH_SCHEMA_INVALID")
    return dataset


def causal_dataset_reasons(
    dataset: Mapping[str, Any],
    *,
    eth_spot_facts: Sequence[Mapping[str, Any]],
    btc_context_facts: Sequence[Mapping[str, Any]],
    eth_mark_facts: Sequence[Mapping[str, Any]],
    eth_funding_facts: Sequence[Mapping[str, Any]],
    execution_sources: Sequence[Mapping[str, Any]],
) -> Tuple[str, ...]:
    reasons = []
    if not isinstance(dataset, Mapping):
        return ("CAUSAL_RESEARCH_DATASET_INVALID",)
    try:
        if tuple(_validator().iter_errors(dataset)):
            reasons.append("CAUSAL_RESEARCH_SCHEMA_INVALID")
        if dataset.get("dataset_hash") != causal_dataset_hash(dataset):
            reasons.append("CAUSAL_RESEARCH_HASH_MISMATCH")
        rebuilt = build_causal_feature_label_dataset(
            eth_spot_facts=eth_spot_facts,
            btc_context_facts=btc_context_facts,
            eth_mark_facts=eth_mark_facts,
            eth_funding_facts=eth_funding_facts,
            execution_sources=execution_sources,
            source_roots=dataset["source_roots"],
            recorded_at=dataset["recorded_at"],
        )
        if business_hash(rebuilt) != business_hash(dataset):
            reasons.append("CAUSAL_RESEARCH_SEMANTIC_MISMATCH")
    except (KeyError, TypeError, ValueError, CausalResearchError):
        reasons.append("CAUSAL_RESEARCH_SEMANTIC_INVALID")
    return tuple(sorted(set(reasons)))


def publish_causal_dataset(
    *,
    dataset: Mapping[str, Any],
    output_path: Path,
) -> None:
    if (
        not isinstance(dataset, Mapping)
        or tuple(_validator().iter_errors(dataset))
        or dataset.get("dataset_hash") != causal_dataset_hash(dataset)
    ):
        raise CausalResearchError("CAUSAL_RESEARCH_DATASET_INVALID")
    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    _publish_exact(path, canonical_json(dataset).encode("utf-8"))


def load_causal_dataset(path: Path) -> Mapping[str, Any]:
    try:
        dataset = _strict_json_bytes(
            Path(path).expanduser().resolve().read_bytes()
        )
    except OSError as error:
        raise CausalResearchError("CAUSAL_RESEARCH_DATASET_READ_FAILED") from error
    if (
        tuple(_validator().iter_errors(dataset))
        or dataset.get("dataset_hash") != causal_dataset_hash(dataset)
    ):
        raise CausalResearchError("CAUSAL_RESEARCH_DATASET_INVALID")
    return dataset
