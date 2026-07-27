"""Deterministic failure attribution for the rejected V1 simple baseline."""

import json
import os
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
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
from .causal_research import causal_dataset_hash
from .evidence import artifact_self_hash
from .research_corpus import _publish_exact, _strict_json_bytes


_SCHEMA = "baseline-failure-attribution-v1.schema.json"
_ZERO_HASH = "0" * 64
_BOUNDARY = timedelta(hours=24)
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
_BANDS = {
    "eth_sma20_distance": (
        ("SMA_DISTANCE_0_TO_0_005", Decimal("0"), Decimal("0.005")),
        ("SMA_DISTANCE_0_005_TO_0_01", Decimal("0.005"), Decimal("0.01")),
        ("SMA_DISTANCE_0_01_TO_0_02", Decimal("0.01"), Decimal("0.02")),
        ("SMA_DISTANCE_0_02_PLUS", Decimal("0.02"), None),
    ),
    "eth_annualized_volatility_20": (
        ("ANNUAL_VOL_0_TO_0_4", Decimal("0"), Decimal("0.4")),
        ("ANNUAL_VOL_0_4_TO_0_8", Decimal("0.4"), Decimal("0.8")),
        ("ANNUAL_VOL_0_8_TO_1_2", Decimal("0.8"), Decimal("1.2")),
        ("ANNUAL_VOL_1_2_PLUS", Decimal("1.2"), None),
    ),
    "eth_mean_range_ratio_6": (
        ("RANGE_RATIO_0_TO_0_01", Decimal("0"), Decimal("0.01")),
        ("RANGE_RATIO_0_01_TO_0_02", Decimal("0.01"), Decimal("0.02")),
        ("RANGE_RATIO_0_02_TO_0_04", Decimal("0.02"), Decimal("0.04")),
        ("RANGE_RATIO_0_04_PLUS", Decimal("0.04"), None),
    ),
}
_WARNINGS = (
    "ATTRIBUTION_DESCRIBES_VIEWED_ARCHIVE_DATA_ONLY",
    "GROUP_RESULTS_MUST_NOT_BE_USED_FOR_THRESHOLD_SEARCH",
    "CHALLENGER_HAS_NOT_BEEN_EVALUATED",
    "NO_MODEL_TRAINED_OR_APPROVED",
    "NO_PROFITABILITY_CLAIM",
)


class BaselineAttributionError(ValueError):
    """The attribution input, calculation, or artifact failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise BaselineAttributionError("BASELINE_ATTRIBUTION_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise BaselineAttributionError(
            "BASELINE_ATTRIBUTION_TIME_INVALID"
        ) from error
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() != timedelta(0)
        or utc_datetime(parsed) != value
    ):
        raise BaselineAttributionError("BASELINE_ATTRIBUTION_TIME_INVALID")
    return parsed


def _decimal(value: object) -> Decimal:
    if not isinstance(value, str):
        raise BaselineAttributionError("BASELINE_ATTRIBUTION_NUMBER_INVALID")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise BaselineAttributionError(
            "BASELINE_ATTRIBUTION_NUMBER_INVALID"
        ) from error
    if not parsed.is_finite():
        raise BaselineAttributionError("BASELINE_ATTRIBUTION_NUMBER_INVALID")
    return parsed


def _grouping_policy() -> Dict[str, Any]:
    contract = {
        "grouping_policy_version": "BASELINE_FAILURE_ATTRIBUTION_V1",
        "grouped_scope": "POOLED_ARCHIVE_OOS",
        "feature_index_map": {
            name: index for index, name in enumerate(_FEATURE_NAMES)
        },
        "bands": {
            name: [
                {
                    "bucket_id": bucket_id,
                    "lower_inclusive_or_null": (
                        canonical_decimal(lower)
                        if lower is not None
                        else None
                    ),
                    "upper_exclusive_or_null": (
                        canonical_decimal(upper)
                        if upper is not None
                        else None
                    ),
                }
                for bucket_id, lower, upper in bands
            ]
            for name, bands in _BANDS.items()
        },
        "momentum_buckets": [
            "ETH_LOG_RETURN_5_NEGATIVE",
            "ETH_LOG_RETURN_5_NONNEGATIVE",
        ],
        "fold_boundary_hours": 24,
    }
    return {
        **contract,
        "grouping_policy_hash": business_hash(contract),
    }


def _hypothesis_registration() -> Dict[str, Any]:
    contract = {
        "trial_family": "baseline-rule-challenger-2026q3",
        "economic_hypothesis_count": 1,
        "parameter_combination_count": 1,
        "challenger_policy_id": "SPOT_LONG_SMA20_COST_MARGIN_MOMENTUM_V2",
        "sma20_distance_minimum": "0.005",
        "eth_log_return_5_operator": ">",
        "eth_log_return_5_threshold": "0",
        "entry_rule": "ALL_CONDITIONS_REQUIRED",
        "exit_policy": "UNCHANGED_FROM_V1",
        "episode_regeneration": "FULL_EVENT_STREAM_REJECTED_ENTRY_DOES_NOT_CONSUME_WINDOW",
        "viewed_archive_status": "VIEWED_DEVELOPMENT_ONLY",
        "challenger_evaluation_status": "NOT_RUN_PREREGISTERED_FORWARD_ONLY",
        "forward_validation_start": "2026-07-29T00:00:00.000Z",
    }
    return {
        **contract,
        "hypothesis_registration_hash": business_hash(contract),
    }


def _validated_samples(
    dataset: Mapping[str, Any],
) -> Tuple[Mapping[str, Any], ...]:
    try:
        names = tuple(dataset["feature_schema"]["ordered_feature_names"])
        reference_notional = _decimal(
            dataset["label_policy"]["reference_notional_usdt"]
        )
        samples = tuple(dataset["samples"])
    except (KeyError, TypeError) as error:
        raise BaselineAttributionError(
            "BASELINE_ATTRIBUTION_DATASET_INVALID"
        ) from error
    if (
        dataset.get("dataset_hash") != causal_dataset_hash(dataset)
        or dataset.get("research_eligibility")
        != "ARCHIVE_CAUSAL_RESEARCH_ONLY"
        or names != _FEATURE_NAMES
        or reference_notional <= 0
        or not samples
        or dataset.get("samples_root_hash") != business_hash(list(samples))
    ):
        raise BaselineAttributionError("BASELINE_ATTRIBUTION_DATASET_INVALID")
    identities = []
    times = []
    for sample in samples:
        try:
            identity = sample["sample_id"]
            decision = _utc(sample["decision_time"])
            label_end = _utc(sample["label_end_time_exclusive"])
            raw_values = sample["feature_values"]
            if isinstance(raw_values, (str, bytes)) or not isinstance(
                raw_values,
                Sequence,
            ):
                raise BaselineAttributionError(
                    "BASELINE_ATTRIBUTION_SAMPLE_INVALID"
                )
            values = tuple(raw_values)
            gross = _decimal(sample["gross_pnl_usdt"])
            entry_fee = _decimal(sample["entry_fee_usdt"])
            exit_fee = _decimal(sample["exit_fee_usdt"])
            net = _decimal(sample["net_pnl_usdt"])
            realized = _decimal(sample["realized_net_return_24h"])
            label = sample["y_take"]
            holding = sample["holding_hours"]
            exit_reason = sample["exit_reason"]
        except (KeyError, TypeError) as error:
            raise BaselineAttributionError(
                "BASELINE_ATTRIBUTION_SAMPLE_INVALID"
            ) from error
        if (
            not isinstance(identity, str)
            or len(values) != len(_FEATURE_NAMES)
            or any(not _decimal(value).is_finite() for value in values)
            or entry_fee < 0
            or exit_fee < 0
            or net != gross - entry_fee - exit_fee
            or realized != net / reference_notional
            or label not in (0, 1)
            or label != int(realized > 0)
            or label_end <= decision
            or not isinstance(holding, int)
            or holding <= 0
            or not isinstance(exit_reason, str)
            or not exit_reason
        ):
            raise BaselineAttributionError(
                "BASELINE_ATTRIBUTION_SAMPLE_INVALID"
            )
        identities.append(identity)
        times.append(decision)
    if (
        len(identities) != len(set(identities))
        or times != sorted(times)
        or len(times) != len(set(times))
    ):
        raise BaselineAttributionError("BASELINE_ATTRIBUTION_SAMPLE_ORDER_INVALID")
    return samples


def _validated_folds(
    folds: Sequence[Mapping[str, Any]],
) -> Tuple[Mapping[str, Any], ...]:
    if not isinstance(folds, Sequence) or not folds:
        raise BaselineAttributionError("BASELINE_ATTRIBUTION_FOLDS_INVALID")
    values = tuple(folds)
    prior_end = None
    for expected_index, fold in enumerate(values, 1):
        try:
            index = fold["fold_index"]
            fold_id = fold["fold_id"]
            start = _utc(fold["oos_window_start"])
            end = _utc(fold["oos_window_end_exclusive"])
        except (KeyError, TypeError) as error:
            raise BaselineAttributionError(
                "BASELINE_ATTRIBUTION_FOLDS_INVALID"
            ) from error
        if (
            index != expected_index
            or not isinstance(fold_id, str)
            or not fold_id
            or start >= end
            or fold.get("purge_duration_hours") != 24
            or fold.get("embargo_duration_hours") != 24
            or (prior_end is not None and start != prior_end)
        ):
            raise BaselineAttributionError("BASELINE_ATTRIBUTION_FOLDS_INVALID")
        prior_end = end
    return values


def _oos_samples(
    samples: Sequence[Mapping[str, Any]],
    fold: Mapping[str, Any],
) -> Tuple[Mapping[str, Any], ...]:
    start = _utc(fold["oos_window_start"]) + _BOUNDARY
    end = _utc(fold["oos_window_end_exclusive"])
    decision_end = end - _BOUNDARY
    return tuple(
        sample
        for sample in samples
        if start <= _utc(sample["decision_time"]) < decision_end
        and _utc(sample["label_end_time_exclusive"]) <= end
    )


def _metrics(samples: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    count = len(samples)
    gross = sum(
        (_decimal(sample["gross_pnl_usdt"]) for sample in samples),
        Decimal("0"),
    )
    entry_fee = sum(
        (_decimal(sample["entry_fee_usdt"]) for sample in samples),
        Decimal("0"),
    )
    exit_fee = sum(
        (_decimal(sample["exit_fee_usdt"]) for sample in samples),
        Decimal("0"),
    )
    net = sum(
        (_decimal(sample["net_pnl_usdt"]) for sample in samples),
        Decimal("0"),
    )
    returns = [
        _decimal(sample["realized_net_return_24h"]) for sample in samples
    ]
    positive = sum(sample["y_take"] for sample in samples)
    return {
        "sample_count": count,
        "positive_label_count": positive,
        "positive_label_rate": (
            canonical_decimal(Decimal(positive) / Decimal(count))
            if count
            else "0"
        ),
        "gross_pnl_usdt_sum": canonical_decimal(gross),
        "entry_fee_usdt_sum": canonical_decimal(entry_fee),
        "exit_fee_usdt_sum": canonical_decimal(exit_fee),
        "total_fee_usdt_sum": canonical_decimal(entry_fee + exit_fee),
        "net_pnl_usdt_sum": canonical_decimal(net),
        "gross_pnl_usdt_mean": (
            canonical_decimal(gross / Decimal(count)) if count else "0"
        ),
        "net_pnl_usdt_mean": (
            canonical_decimal(net / Decimal(count)) if count else "0"
        ),
        "realized_net_return_sum": canonical_decimal(
            sum(returns, Decimal("0"))
        ),
        "fee_flip_count": sum(
            _decimal(sample["gross_pnl_usdt"]) > 0
            and _decimal(sample["net_pnl_usdt"]) <= 0
            for sample in samples
        ),
        "minimum_realized_net_return_or_null": (
            canonical_decimal(min(returns)) if returns else None
        ),
        "maximum_realized_net_return_or_null": (
            canonical_decimal(max(returns)) if returns else None
        ),
        "first_decision_time_or_null": (
            samples[0]["decision_time"] if samples else None
        ),
        "last_decision_time_or_null": (
            samples[-1]["decision_time"] if samples else None
        ),
    }


def _concentration(samples: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    values = sorted(
        (
            (
                _decimal(sample["realized_net_return_24h"]),
                sample["sample_id"],
            )
            for sample in samples
            if _decimal(sample["realized_net_return_24h"]) > 0
        ),
        key=lambda item: (-item[0], item[1]),
    )
    total_positive = sum((value for value, _ in values), Decimal("0"))
    total = sum(
        (
            _decimal(sample["realized_net_return_24h"])
            for sample in samples
        ),
        Decimal("0"),
    )
    top_one = sum((value for value, _ in values[:1]), Decimal("0"))
    top_five = sum((value for value, _ in values[:5]), Decimal("0"))
    return {
        "positive_event_count": len(values),
        "positive_contribution_sum": canonical_decimal(total_positive),
        "top_1_positive_share": (
            canonical_decimal(top_one / total_positive)
            if total_positive
            else "0"
        ),
        "top_5_positive_share": (
            canonical_decimal(top_five / total_positive)
            if total_positive
            else "0"
        ),
        "net_return_sum_after_top_1_positive_removed": canonical_decimal(
            total - top_one
        ),
        "net_return_sum_after_top_5_positive_removed": canonical_decimal(
            total - top_five
        ),
        "top_5_sample_ids": [identity for _, identity in values[:5]],
    }


def _band_bucket(
    value: Decimal,
    bands: Sequence[Tuple[str, Decimal, Decimal]],
) -> str:
    for bucket_id, lower, upper in bands:
        if value >= lower and (upper is None or value < upper):
            return bucket_id
    raise BaselineAttributionError("BASELINE_ATTRIBUTION_BAND_INVALID")


def baseline_attribution_hash(attribution: Mapping[str, Any]) -> str:
    return artifact_self_hash(attribution, "attribution_hash")


def build_baseline_failure_attribution(
    *,
    dataset: Mapping[str, Any],
    folds: Sequence[Mapping[str, Any]],
    recorded_at: str,
) -> Dict[str, Any]:
    """Build the frozen descriptive attribution without testing a challenger."""

    _utc(recorded_at)
    samples = _validated_samples(dataset)
    fold_values = _validated_folds(folds)
    pooled = []
    groups = []
    for fold in fold_values:
        selected = _oos_samples(samples, fold)
        pooled.extend(selected)
        groups.append(
            {
                "dimension": "OOS_FOLD",
                "bucket_id": f"FOLD_{fold['fold_index']}",
                "bucket_order": fold["fold_index"],
                "metrics": _metrics(selected),
            }
        )
    if not pooled or len({sample["sample_id"] for sample in pooled}) != len(
        pooled
    ):
        raise BaselineAttributionError("BASELINE_ATTRIBUTION_OOS_INVALID")
    pooled.sort(key=lambda sample: sample["decision_time"])
    dimensions = []
    exit_values = sorted({sample["exit_reason"] for sample in pooled})
    dimensions.append(
        (
            "EXIT_REASON",
            [
                (
                    f"EXIT_{value}",
                    tuple(
                        sample
                        for sample in pooled
                        if sample["exit_reason"] == value
                    ),
                )
                for value in exit_values
            ],
        )
    )
    holding_values = sorted({sample["holding_hours"] for sample in pooled})
    dimensions.append(
        (
            "HOLDING_HOURS",
            [
                (
                    f"HOLDING_{value}H",
                    tuple(
                        sample
                        for sample in pooled
                        if sample["holding_hours"] == value
                    ),
                )
                for value in holding_values
            ],
        )
    )
    feature_indexes = {
        name: index for index, name in enumerate(_FEATURE_NAMES)
    }
    momentum_index = feature_indexes["eth_log_return_5"]
    dimensions.append(
        (
            "ETH_LOG_RETURN_5",
            [
                (
                    "ETH_LOG_RETURN_5_NEGATIVE",
                    tuple(
                        sample
                        for sample in pooled
                        if _decimal(sample["feature_values"][momentum_index])
                        < 0
                    ),
                ),
                (
                    "ETH_LOG_RETURN_5_NONNEGATIVE",
                    tuple(
                        sample
                        for sample in pooled
                        if _decimal(sample["feature_values"][momentum_index])
                        >= 0
                    ),
                ),
            ],
        )
    )
    for name, bands in _BANDS.items():
        index = feature_indexes[name]
        buckets = []
        for bucket_id, _, _ in bands:
            buckets.append(
                (
                    bucket_id,
                    tuple(
                        sample
                        for sample in pooled
                        if _band_bucket(
                            _decimal(sample["feature_values"][index]),
                            bands,
                        )
                        == bucket_id
                    ),
                )
            )
        dimensions.append((name.upper(), buckets))
    for dimension, buckets in dimensions:
        for order, (bucket_id, selected) in enumerate(buckets, 1):
            groups.append(
                {
                    "dimension": dimension,
                    "bucket_id": bucket_id,
                    "bucket_order": order,
                    "metrics": _metrics(selected),
                }
            )
    grouping = _grouping_policy()
    hypothesis = _hypothesis_registration()
    all_metrics = _metrics(samples)
    pooled_metrics = _metrics(pooled)
    group_root = business_hash(groups)
    concentration = {
        "all_events": _concentration(samples),
        "pooled_archive_oos": _concentration(pooled),
    }
    identity = {
        "dataset_hash": dataset["dataset_hash"],
        "fold_plan_hash": business_hash(list(fold_values)),
        "grouping_policy_hash": grouping["grouping_policy_hash"],
        "hypothesis_registration_hash": hypothesis[
            "hypothesis_registration_hash"
        ],
        "groups_root_hash": group_root,
        "concentration": concentration,
    }
    attribution = {
        "$schema": "./baseline-failure-attribution-v1.schema.json",
        "schema_version": "1.0.0",
        "attribution_id": stable_id("baseline_failure_attribution", identity),
        "attribution_hash": _ZERO_HASH,
        "recorded_at": recorded_at,
        "dataset_id": dataset["dataset_id"],
        "dataset_hash": dataset["dataset_hash"],
        "samples_root_hash": dataset["samples_root_hash"],
        "fold_plan_hash": identity["fold_plan_hash"],
        "grouping_policy": grouping,
        "hypothesis_registration": hypothesis,
        "all_event_metrics": all_metrics,
        "pooled_archive_oos_metrics": pooled_metrics,
        "groups_root_hash": group_root,
        "groups": groups,
        "contribution_concentration": concentration,
        "diagnosis": {
            "all_event_gross_edge_status": (
                "NEGATIVE_BEFORE_FEES"
                if _decimal(all_metrics["gross_pnl_usdt_sum"]) < 0
                else "NONNEGATIVE_BEFORE_FEES"
            ),
            "pooled_oos_gross_edge_status": (
                "NEGATIVE_BEFORE_FEES"
                if _decimal(pooled_metrics["gross_pnl_usdt_sum"]) < 0
                else "NONNEGATIVE_BEFORE_FEES"
            ),
            "all_event_exact_fee_drag_usdt": all_metrics[
                "total_fee_usdt_sum"
            ],
            "pooled_oos_exact_fee_drag_usdt": pooled_metrics[
                "total_fee_usdt_sum"
            ],
            "interpretation": "DESCRIPTIVE_FAILURE_ATTRIBUTION_NOT_A_GATE",
        },
        "baseline_advancement": "REJECTED_V1",
        "challenger_evaluation_status": (
            "NOT_RUN_PREREGISTERED_FORWARD_ONLY"
        ),
        "formal_pit_eligibility": "INELIGIBLE_ARCHIVE_REPLAY",
        "release_oos_eligibility": "INELIGIBLE_VIEWED_ARCHIVE",
        "profitability_eligibility": "INELIGIBLE",
        "warnings": list(_WARNINGS),
    }
    attribution["attribution_hash"] = baseline_attribution_hash(attribution)
    if tuple(_validator().iter_errors(attribution)):
        raise BaselineAttributionError(
            "BASELINE_ATTRIBUTION_SCHEMA_INVALID"
        )
    return attribution


def baseline_attribution_reasons(
    attribution: Mapping[str, Any],
    *,
    dataset: Mapping[str, Any],
    folds: Sequence[Mapping[str, Any]],
) -> Tuple[str, ...]:
    reasons = []
    if not isinstance(attribution, Mapping):
        return ("BASELINE_ATTRIBUTION_INVALID",)
    try:
        if tuple(_validator().iter_errors(attribution)):
            reasons.append("BASELINE_ATTRIBUTION_SCHEMA_INVALID")
        if attribution.get("attribution_hash") != baseline_attribution_hash(
            attribution
        ):
            reasons.append("BASELINE_ATTRIBUTION_HASH_MISMATCH")
        rebuilt = build_baseline_failure_attribution(
            dataset=dataset,
            folds=folds,
            recorded_at=attribution["recorded_at"],
        )
        if business_hash(rebuilt) != business_hash(attribution):
            reasons.append("BASELINE_ATTRIBUTION_SEMANTIC_MISMATCH")
    except (KeyError, TypeError, ValueError, BaselineAttributionError):
        reasons.append("BASELINE_ATTRIBUTION_SEMANTIC_INVALID")
    return tuple(sorted(set(reasons)))


def publish_baseline_attribution(
    *,
    attribution: Mapping[str, Any],
    output_path: Path,
) -> None:
    if (
        not isinstance(attribution, Mapping)
        or tuple(_validator().iter_errors(attribution))
        or attribution.get("attribution_hash")
        != baseline_attribution_hash(attribution)
    ):
        raise BaselineAttributionError("BASELINE_ATTRIBUTION_INVALID")
    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    _publish_exact(path, canonical_json(attribution).encode("utf-8"))


def load_baseline_attribution(path: Path) -> Mapping[str, Any]:
    try:
        attribution = _strict_json_bytes(
            Path(path).expanduser().resolve().read_bytes()
        )
    except OSError as error:
        raise BaselineAttributionError(
            "BASELINE_ATTRIBUTION_READ_FAILED"
        ) from error
    if (
        tuple(_validator().iter_errors(attribution))
        or attribution.get("attribution_hash")
        != baseline_attribution_hash(attribution)
    ):
        raise BaselineAttributionError("BASELINE_ATTRIBUTION_INVALID")
    return attribution
