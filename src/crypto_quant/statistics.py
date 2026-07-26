"""Deterministic dependent-series statistics over frozen economic facts."""

import hashlib
import re
from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_EVEN, localcontext
from functools import wraps
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple, TypeVar

from .canonical import canonical_decimal
from .economics import economic_snapshot_reasons, period_economic_pnl
from .errors import CanonicalizationError
from .evidence import artifact_self_hash

_Result = TypeVar("_Result")


def _fixed_decimal_context(
    function: Callable[..., _Result],
) -> Callable[..., _Result]:
    @wraps(function)
    def wrapped(*args: Any, **kwargs: Any) -> _Result:
        with localcontext() as context:
            context.prec = 50
            context.rounding = ROUND_HALF_EVEN
            return function(*args, **kwargs)

    return wrapped


def statistical_series_hash(series: Mapping[str, Any]) -> str:
    return artifact_self_hash(series, "series_hash")


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp is not a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp is not timezone aware")
    return parsed.astimezone(timezone.utc)


def _decimal(value: Any) -> Decimal:
    return Decimal(canonical_decimal(value))


def _require_id(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}",
        value,
    ) is None:
        raise ValueError(f"{field_name} is not a canonical ID")


def _require_hash(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or re.fullmatch(
        r"[a-f0-9]{64}",
        value,
    ) is None:
        raise ValueError(f"{field_name} is not a SHA-256 digest")


def _next_month(start: datetime) -> datetime:
    year = start.year + (1 if start.month == 12 else 0)
    month = 1 if start.month == 12 else start.month + 1
    return start.replace(year=year, month=month)


def _is_complete_utc_month(start: datetime, end: datetime) -> bool:
    return (
        start.day == 1
        and start.hour == 0
        and start.minute == 0
        and start.second == 0
        and start.microsecond == 0
        and end == _next_month(start)
    )


def statistical_series_reasons(
    series: Mapping[str, Any],
) -> Tuple[str, ...]:
    reasons = []
    try:
        computed_hash = statistical_series_hash(series)
    except CanonicalizationError:
        computed_hash = ""
        reasons.append("STATISTICAL_SERIES_NOT_CANONICAL")
    if series.get("series_hash") != computed_hash:
        reasons.append("STATISTICAL_SERIES_SELF_HASH_MISMATCH")
    if series.get("replay_verified") is not True:
        reasons.append("STATISTICAL_SERIES_REPLAY_UNVERIFIED")

    scope = series.get("scope")
    if not isinstance(scope, Mapping):
        return tuple(
            sorted(set(reasons + ["STATISTICAL_SERIES_SCOPE_INVALID"]))
        )
    if (
        scope.get("evaluation_ledger") == "BASELINE_LEDGER"
        and scope.get("release_route") != "BASELINE_ONLY"
    ) or (
        scope.get("evaluation_ledger") == "AI_LEDGER"
        and scope.get("release_route") != "AI_ENHANCED"
    ):
        reasons.append("STATISTICAL_SERIES_LEDGER_ROUTE_MISMATCH")
    if (
        scope.get("direction"),
        scope.get("venue"),
    ) not in {
        ("LONG", "BINANCE_SPOT"),
        ("SHORT", "BINANCE_USDT_PERP"),
    }:
        reasons.append("STATISTICAL_SERIES_DIRECTION_VENUE_MISMATCH")
    try:
        scope_start = _timestamp(scope.get("evaluation_window_start"))
        scope_end = _timestamp(scope.get("evaluation_window_end"))
        generated = _timestamp(series.get("generated_at"))
        if scope_end <= scope_start:
            reasons.append("STATISTICAL_SERIES_WINDOW_NOT_INCREASING")
        if generated < scope_end:
            reasons.append("STATISTICAL_SERIES_GENERATED_BEFORE_END")
    except (TypeError, ValueError):
        return tuple(
            sorted(set(reasons + ["STATISTICAL_SERIES_TIME_INVALID"]))
        )

    observations = series.get("observations")
    if not isinstance(observations, list) or not observations:
        return tuple(
            sorted(set(reasons + ["STATISTICAL_SERIES_OBSERVATIONS_MISSING"]))
        )
    identifiers = []
    source_hashes = []
    period_boundaries = []
    month_completeness = []
    previous_end: Optional[datetime] = None
    for observation in observations:
        if not isinstance(observation, Mapping):
            reasons.append("STATISTICAL_SERIES_OBSERVATION_INVALID")
            continue
        identifiers.append(observation.get("observation_id"))
        source_hashes.append(
            observation.get("source_economic_snapshot_hash")
        )
        try:
            start = _timestamp(observation.get("period_start"))
            end = _timestamp(observation.get("period_end"))
            if end <= start:
                reasons.append("STATISTICAL_SERIES_PERIOD_NOT_INCREASING")
            if previous_end is not None and start < previous_end:
                reasons.append("STATISTICAL_SERIES_PERIOD_OVERLAP")
            if start < scope_start or end > scope_end:
                reasons.append("STATISTICAL_SERIES_PERIOD_OUTSIDE_SCOPE")
            if observation.get(
                "calendar_month_complete"
            ) is not _is_complete_utc_month(start, end):
                reasons.append(
                    "STATISTICAL_SERIES_MONTH_COMPLETENESS_MISMATCH"
                )
            period_boundaries.append((start, end))
            month_completeness.append(
                observation.get("calendar_month_complete")
            )
            _decimal(observation.get("value"))
            previous_end = end
        except (CanonicalizationError, TypeError, ValueError):
            reasons.append("STATISTICAL_SERIES_OBSERVATION_VALUE_INVALID")
    if len(identifiers) != len(set(identifiers)):
        reasons.append("STATISTICAL_SERIES_OBSERVATION_ID_DUPLICATE")
    declared_sources = series.get("source_economic_snapshot_hashes")
    if not isinstance(declared_sources, list) or declared_sources != (
        source_hashes
    ):
        reasons.append("STATISTICAL_SERIES_SOURCE_SEQUENCE_MISMATCH")
    if len(source_hashes) != len(set(source_hashes)):
        reasons.append("STATISTICAL_SERIES_SOURCE_DUPLICATE")
    if period_boundaries:
        if (
            period_boundaries[0][0] != scope_start
            or period_boundaries[-1][1] != scope_end
        ):
            reasons.append("STATISTICAL_SERIES_BOUNDARY_MISMATCH")
    if series.get("series_kind") == "MONTHLY_ECONOMIC_PNL_USDT":
        if series.get("aggregation") != "MEAN":
            reasons.append("STATISTICAL_SERIES_MONTHLY_AGGREGATION_INVALID")
        if any(
            current[0] != previous[1]
            for previous, current in zip(
                period_boundaries,
                period_boundaries[1:],
            )
        ):
            reasons.append("STATISTICAL_SERIES_MONTHLY_PERIOD_GAP")
        if any(
            complete is not True and index not in (0, len(month_completeness) - 1)
            for index, complete in enumerate(month_completeness)
        ):
            reasons.append("STATISTICAL_SERIES_INTERIOR_PARTIAL_MONTH")
        if (
            series.get("capital_normalization")
            != "MONTHLY_RESET_TO_APPROVED_CAPITAL"
        ):
            reasons.append(
                "STATISTICAL_SERIES_MONTHLY_CAPITAL_NORMALIZATION_INVALID"
            )
    else:
        if series.get("aggregation") != "SUM":
            reasons.append("STATISTICAL_SERIES_ENDPOINT_AGGREGATION_INVALID")
        if (
            series.get("capital_normalization")
            != "APPROVED_CAPITAL_EVALUATION_WINDOW"
        ):
            reasons.append(
                "STATISTICAL_SERIES_ENDPOINT_CAPITAL_NORMALIZATION_INVALID"
            )
    return tuple(sorted(set(reasons)))


def _validated_series(
    inputs: Mapping[str, Any],
) -> Tuple[Optional[Mapping[str, Any]], Tuple[str, ...]]:
    series = inputs.get("statistical_series_snapshot")
    if not isinstance(series, Mapping):
        return None, ("STATISTICAL_SERIES_INVALID",)
    reasons = statistical_series_reasons(series)
    return (series, ()) if not reasons else (None, reasons)


def _eligible_values(
    series: Mapping[str, Any],
    *,
    complete_months_only: bool,
) -> Tuple[Decimal, ...]:
    return tuple(
        _decimal(observation["value"])
        for observation in series["observations"]
        if not complete_months_only
        or observation["calendar_month_complete"]
    )


@_fixed_decimal_context
def geyer_initial_positive_sequence_ess(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]:
    series, reasons = _validated_series(inputs)
    if reasons:
        return "FAIL", None, reasons
    values = _eligible_values(series, complete_months_only=False)
    design = series["bootstrap_design"]
    block_length = design["block_length"]
    if (
        len(values) // block_length
        < design["minimum_block_count"]
        or len(values) < 3
    ):
        return (
            "INCONCLUSIVE",
            None,
            ("STATISTICAL_SERIES_INSUFFICIENT_BLOCKS",),
        )
    count = Decimal(len(values))
    mean = sum(values, Decimal("0")) / count
    centered = tuple(value - mean for value in values)
    gamma_zero = sum(
        (value * value for value in centered),
        Decimal("0"),
    ) / count
    if gamma_zero == 0:
        return (
            "INCONCLUSIVE",
            None,
            ("STATISTICAL_SERIES_ZERO_VARIANCE",),
        )
    autocorrelations = []
    for lag in range(1, len(values)):
        covariance = sum(
            (
                centered[index] * centered[index + lag]
                for index in range(len(values) - lag)
            ),
            Decimal("0"),
        ) / count
        autocorrelations.append(covariance / gamma_zero)
    retained_sum = Decimal("0")
    for index in range(0, len(autocorrelations) - 1, 2):
        pair = autocorrelations[index] + autocorrelations[index + 1]
        if pair <= 0:
            break
        retained_sum += pair
    tau = max(Decimal("1"), Decimal("1") + Decimal("2") * retained_sum)
    effective = (count / tau).to_integral_value(rounding=ROUND_FLOOR)
    return "COMPUTED", int(min(count, effective)), ()


def _draw_start(
    *,
    seed: int,
    replicate: int,
    draw: int,
    start_count: int,
) -> int:
    modulus = 1 << 256
    acceptance_limit = modulus - modulus % start_count
    attempt = 0
    while True:
        material = (
            "MBB_V1:"
            f"{seed}:{replicate}:{draw}:{start_count}:{attempt}"
        ).encode("ascii")
        candidate = int.from_bytes(
            hashlib.sha256(material).digest(),
            "big",
        )
        if candidate < acceptance_limit:
            return candidate % start_count
        attempt += 1


def _moving_block_lcb(
    series: Mapping[str, Any],
    *,
    complete_months_only: bool,
) -> Tuple[str, Any, Tuple[str, ...]]:
    values = _eligible_values(
        series,
        complete_months_only=complete_months_only,
    )
    design = series["bootstrap_design"]
    length = design["block_length"]
    if (
        not values
        or len(values) // length < design["minimum_block_count"]
        or len(values) < length
    ):
        return (
            "INCONCLUSIVE",
            None,
            ("STATISTICAL_SERIES_INSUFFICIENT_BLOCKS",),
        )
    start_count = len(values) - length + 1
    blocks_per_sample = (len(values) + length - 1) // length
    replicates = []
    for replicate in range(design["resample_count"]):
        sampled = []
        for draw in range(blocks_per_sample):
            start = _draw_start(
                seed=design["seed"],
                replicate=replicate,
                draw=draw,
                start_count=start_count,
            )
            sampled.extend(values[start : start + length])
        sampled = sampled[: len(values)]
        statistic = sum(sampled, Decimal("0"))
        if series["aggregation"] == "MEAN":
            statistic /= Decimal(len(sampled))
        replicates.append(statistic)
    replicates.sort()
    rank = max(1, (design["resample_count"] * 5 + 99) // 100)
    return "COMPUTED", canonical_decimal(replicates[rank - 1]), ()


@_fixed_decimal_context
def one_sided_95_moving_block_bootstrap(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]:
    series, reasons = _validated_series(inputs)
    if reasons:
        return "FAIL", None, reasons
    if series["series_kind"] != "PRIMARY_ENDPOINT_CONTRIBUTION":
        return "FAIL", None, ("STATISTICAL_SERIES_KIND_MISMATCH",)
    return _moving_block_lcb(series, complete_months_only=False)


@_fixed_decimal_context
def monthly_economic_pnl_mbb_lcb95(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]:
    series, reasons = _validated_series(inputs)
    if reasons:
        return "FAIL", None, reasons
    if series["series_kind"] != "MONTHLY_ECONOMIC_PNL_USDT":
        return "FAIL", None, ("STATISTICAL_SERIES_KIND_MISMATCH",)
    return _moving_block_lcb(series, complete_months_only=True)


@_fixed_decimal_context
def complete_utc_calendar_month_count(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]:
    series, reasons = _validated_series(inputs)
    if reasons:
        return "FAIL", None, reasons
    if series["series_kind"] != "MONTHLY_ECONOMIC_PNL_USDT":
        return "FAIL", None, ("STATISTICAL_SERIES_KIND_MISMATCH",)
    return (
        "COMPUTED",
        sum(
            1
            for observation in series["observations"]
            if observation["calendar_month_complete"]
        ),
        (),
    )


@_fixed_decimal_context
def cash_flow_adjusted_economic_log_growth(
    inputs: Mapping[str, Any],
) -> Tuple[str, Any, Tuple[str, ...]]:
    snapshot = inputs.get("economic_ledger_snapshot")
    if not isinstance(snapshot, Mapping):
        return "FAIL", None, ("ECONOMIC_SNAPSHOT_INVALID",)
    reasons = economic_snapshot_reasons(snapshot)
    if reasons:
        return "FAIL", None, reasons
    points = snapshot["equity_points"]
    growth = Decimal("0")
    for previous, current in zip(points, points[1:]):
        start = _timestamp(previous["as_of"])
        end = _timestamp(current["as_of"])
        starting_equity = _decimal(previous["liquidation_equity_usdt"])
        external = sum(
            (
                _decimal(item["signed_amount_usdt"])
                for item in snapshot["external_cash_flows"]
                if start < _timestamp(item["occurred_at"]) <= end
            ),
            Decimal("0"),
        )
        costs = sum(
            (
                _decimal(item["amount_usdt"])
                for item in snapshot["allocated_costs"]
                if start < _timestamp(item["occurred_at"]) <= end
            ),
            Decimal("0"),
        )
        adjusted_end = (
            _decimal(current["liquidation_equity_usdt"])
            - external
            - costs
        )
        if starting_equity <= 0 or adjusted_end <= 0:
            return "FAIL", None, ("ECONOMIC_EQUITY_NONPOSITIVE",)
        growth += (adjusted_end / starting_equity).ln()
    return "COMPUTED", canonical_decimal(growth), ()


@_fixed_decimal_context
def monthly_economic_series_snapshot(
    *,
    series_id: str,
    economic_snapshots: Sequence[Mapping[str, Any]],
    approved_production_capital_usdt: Any,
    split_policy_id: str,
    split_policy_hash: str,
    statistical_design_policy_id: str,
    statistical_design_policy_hash: str,
    experiment_manifest_id: str,
    experiment_manifest_hash: str,
    block_length: int,
    minimum_block_count: int,
    resample_count: int,
    seed: int,
    generated_at: str,
) -> Dict[str, Any]:
    """Build a monthly series only from valid, same-scope economic snapshots."""

    if not economic_snapshots:
        raise ValueError("economic snapshots cannot be empty")
    for name, value in (
        ("series_id", series_id),
        ("split_policy_id", split_policy_id),
        ("statistical_design_policy_id", statistical_design_policy_id),
        ("experiment_manifest_id", experiment_manifest_id),
    ):
        _require_id(value, name)
    for name, value in (
        ("split_policy_hash", split_policy_hash),
        ("statistical_design_policy_hash", statistical_design_policy_hash),
        ("experiment_manifest_hash", experiment_manifest_hash),
    ):
        _require_hash(value, name)
    if _decimal(approved_production_capital_usdt) <= 0:
        raise ValueError("approved production capital must be positive")
    approved_capital = _decimal(approved_production_capital_usdt)
    if (
        isinstance(block_length, bool)
        or not isinstance(block_length, int)
        or block_length < 1
        or isinstance(minimum_block_count, bool)
        or not isinstance(minimum_block_count, int)
        or minimum_block_count < 2
        or isinstance(resample_count, bool)
        or not isinstance(resample_count, int)
        or not 1000 <= resample_count <= 1000000
        or isinstance(seed, bool)
        or not isinstance(seed, int)
        or not 0 <= seed <= 9007199254740991
    ):
        raise ValueError("bootstrap design is outside frozen bounds")
    ordered = sorted(
        economic_snapshots,
        key=lambda item: item["scope"]["evaluation_window_start"],
    )
    for snapshot in ordered:
        reasons = economic_snapshot_reasons(snapshot)
        if reasons:
            raise ValueError(f"invalid economic snapshot: {reasons}")
    first_scope = ordered[0]["scope"]
    identity_fields = (
        "account_id",
        "evaluation_ledger",
        "release_route",
        "direction",
        "venue",
        "recipe_release_id",
        "recipe_release_hash",
        "deployment_line_id",
        "deployment_line_hash",
    )
    for snapshot in ordered:
        if any(
            snapshot["scope"].get(name) != first_scope.get(name)
            for name in identity_fields
        ):
            raise ValueError("economic snapshot scopes do not match")
        for name in (
            "accounting_policy_id",
            "accounting_policy_hash",
            "cost_allocation_policy_id",
            "cost_allocation_policy_hash",
        ):
            if snapshot.get(name) != ordered[0].get(name):
                raise ValueError("economic snapshot policies do not match")
        if _decimal(
            snapshot.get("starting_liquidation_equity_usdt")
        ) != approved_capital:
            raise ValueError(
                "economic snapshot is not reset to approved capital"
            )
    observations = []
    previous_end: Optional[datetime] = None
    for snapshot in ordered:
        start = _timestamp(snapshot["scope"]["evaluation_window_start"])
        end = _timestamp(snapshot["scope"]["evaluation_window_end"])
        if previous_end is not None and start < previous_end:
            raise ValueError("economic snapshot windows overlap")
        status, value, reasons = period_economic_pnl(
            {"economic_ledger_snapshot": snapshot}
        )
        if status != "COMPUTED":
            raise ValueError(f"economic PnL unavailable: {reasons}")
        observations.append(
            {
                "observation_id": snapshot["snapshot_id"],
                "period_start": snapshot["scope"]["evaluation_window_start"],
                "period_end": snapshot["scope"]["evaluation_window_end"],
                "value": value,
                "calendar_month_complete": _is_complete_utc_month(
                    start,
                    end,
                ),
                "source_economic_snapshot_hash": snapshot["snapshot_hash"],
            }
        )
        previous_end = end
    artifact = {
        "$schema": "./statistical-series-snapshot-v1.schema.json",
        "schema_version": "1.0.0",
        "series_id": series_id,
        "series_hash": "0" * 64,
        "hash_algorithm": "SHA-256",
        "canonicalization": "RFC8785_JCS",
        "source_economic_snapshot_hashes": [
            snapshot["snapshot_hash"] for snapshot in ordered
        ],
        "accounting_policy_id": ordered[0]["accounting_policy_id"],
        "accounting_policy_hash": ordered[0]["accounting_policy_hash"],
        "cost_allocation_policy_id": ordered[0][
            "cost_allocation_policy_id"
        ],
        "cost_allocation_policy_hash": ordered[0][
            "cost_allocation_policy_hash"
        ],
        "split_policy_id": split_policy_id,
        "split_policy_hash": split_policy_hash,
        "statistical_design_policy_id": statistical_design_policy_id,
        "statistical_design_policy_hash": statistical_design_policy_hash,
        "experiment_manifest_id": experiment_manifest_id,
        "experiment_manifest_hash": experiment_manifest_hash,
        "scope": {
            **{name: first_scope[name] for name in identity_fields},
            "evaluation_window_start": observations[0]["period_start"],
            "evaluation_window_end": observations[-1]["period_end"],
        },
        "approved_production_capital_usdt": canonical_decimal(
            approved_capital
        ),
        "capital_normalization": "MONTHLY_RESET_TO_APPROVED_CAPITAL",
        "series_kind": "MONTHLY_ECONOMIC_PNL_USDT",
        "aggregation": "MEAN",
        "observations": observations,
        "bootstrap_design": {
            "block_length": block_length,
            "minimum_block_count": minimum_block_count,
            "resample_count": resample_count,
            "seed": seed,
            "confidence_level": "0.95",
            "confidence_side": "LOWER_ONE_SIDED",
            "sampling_rule": (
                "OVERLAPPING_NON_CIRCULAR_MBB_TRUNCATE_TO_N"
            ),
            "quantile_rule": "CONSERVATIVE_NEAREST_RANK_V1",
        },
        "generated_at": generated_at,
        "replay_verified": True,
    }
    artifact["series_hash"] = statistical_series_hash(artifact)
    reasons = statistical_series_reasons(artifact)
    if reasons:
        raise ValueError(f"invalid statistical series: {reasons}")
    return artifact
