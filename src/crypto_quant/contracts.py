"""Core serializable contracts for the decision-to-execution chain."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from .canonical import business_hash, canonical_decimal, stable_id, utc_datetime
from .decimal_math import RiskRatio, as_decimal
from .errors import ContractError


class Direction(str, Enum):
    FLAT = "FLAT"
    LONG = "LONG"
    SHORT = "SHORT"


class StrategyRole(str, Enum):
    BASE = "BASE"
    CHALLENGER = "CHALLENGER"
    SHADOW = "SHADOW"


class DecisionSource(str, Enum):
    NO_AI_BASE = "NO_AI_BASE"
    MODEL = "MODEL"


class DeploymentStage(str, Enum):
    CANDIDATE = "CANDIDATE"
    SHADOW = "SHADOW"
    PAPER = "PAPER"
    CANARY_25 = "CANARY_25"
    CANARY_50 = "CANARY_50"
    CANARY_75 = "CANARY_75"
    CHAMPION = "CHAMPION"
    LAST_KNOWN_GOOD = "LAST_KNOWN_GOOD"
    RETIRED = "RETIRED"


class TargetAction(str, Enum):
    NO_DECISION = "NO_DECISION"
    HOLD_CURRENT = "HOLD_CURRENT"
    FREEZE_INCREASES = "FREEZE_INCREASES"
    REDUCE_TO = "REDUCE_TO"
    SET_TARGET = "SET_TARGET"
    FLATTEN = "FLATTEN"


_NUMERIC_TARGET_ACTIONS = {TargetAction.REDUCE_TO, TargetAction.SET_TARGET}
_NON_NUMERIC_TARGET_ACTIONS = {
    TargetAction.NO_DECISION,
    TargetAction.HOLD_CURRENT,
    TargetAction.FREEZE_INCREASES,
}
_ALLOWED_NONZERO_BUCKETS = {
    Decimal("0.25"),
    Decimal("0.5"),
    Decimal("0.75"),
    Decimal("1"),
}


def _optional_decimal(value: Optional[Any]) -> Optional[Decimal]:
    return None if value is None else as_decimal(value)


def _require_sha256(value: str, field_name: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ContractError(f"{field_name} must be a lowercase SHA-256 hex digest")


@dataclass(frozen=True)
class StrategyProposal:
    schema_version: str
    market_snapshot_id: str
    feature_snapshot_id: str
    strategy_id: str
    strategy_version: str
    strategy_role: StrategyRole
    instrument_id: str
    direction: Direction
    raw_strength: Decimal
    reason_codes: Tuple[str, ...]
    expected_horizon_hours: int
    minimum_hold_hours: int
    valid_until: datetime
    created_at: datetime

    def __post_init__(self) -> None:
        if self.expected_horizon_hours != 24:
            raise ContractError("V1 proposal horizon must be 24 hours")
        if self.minimum_hold_hours != 8:
            raise ContractError("V1 minimum hold must be 8 hours")
        if self.valid_until <= self.created_at:
            raise ContractError("proposal valid_until must be after created_at")
        if not self.reason_codes:
            raise ContractError("proposal requires at least one reason code")
        object.__setattr__(self, "raw_strength", as_decimal(self.raw_strength))

    def business_payload(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "market_snapshot_id": self.market_snapshot_id,
            "feature_snapshot_id": self.feature_snapshot_id,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "strategy_role": self.strategy_role.value,
            "instrument_id": self.instrument_id,
            "direction": self.direction.value,
            "raw_strength": canonical_decimal(self.raw_strength),
            "reason_codes": self.reason_codes,
            "expected_horizon_hours": self.expected_horizon_hours,
            "minimum_hold_hours": self.minimum_hold_hours,
            "valid_until": utc_datetime(self.valid_until),
            "created_at": utc_datetime(self.created_at),
        }

    @property
    def proposal_id(self) -> str:
        return stable_id("proposal", self.business_payload())

    @property
    def proposal_hash(self) -> str:
        return business_hash(self.business_payload())


@dataclass(frozen=True)
class MetaDecision:
    schema_version: str
    proposal_id: str
    decision_source: DecisionSource
    no_ai_base_version_or_null: Optional[str]
    model_id_or_null: Optional[str]
    model_version_or_null: Optional[str]
    deployment_stage: DeploymentStage
    calibration_version_or_null: Optional[str]
    p_net_positive_or_null: Optional[Decimal]
    expected_net_return_or_null: Optional[Decimal]
    return_q10_or_null: Optional[Decimal]
    return_q50_or_null: Optional[Decimal]
    return_q90_or_null: Optional[Decimal]
    uncertainty_score_or_null: Optional[Decimal]
    ood_score_or_null: Optional[Decimal]
    eligible: bool
    ineligibility_reason_mask: Tuple[str, ...]
    recommended_action: TargetAction
    recommended_bucket_or_null: Optional[RiskRatio]
    model_input_hash: str
    prediction_hash: str
    hard_risk_authorized: bool = False

    def __post_init__(self) -> None:
        decimal_fields = (
            "p_net_positive_or_null",
            "expected_net_return_or_null",
            "return_q10_or_null",
            "return_q50_or_null",
            "return_q90_or_null",
            "uncertainty_score_or_null",
            "ood_score_or_null",
        )
        for field_name in decimal_fields:
            object.__setattr__(
                self,
                field_name,
                _optional_decimal(getattr(self, field_name)),
            )
        _require_sha256(self.model_input_hash, "model_input_hash")
        _require_sha256(self.prediction_hash, "prediction_hash")

        if self.decision_source is DecisionSource.NO_AI_BASE:
            if not self.no_ai_base_version_or_null:
                raise ContractError("NO_AI_BASE requires an approved baseline version")
            if any(
                value is not None
                for value in (
                    self.model_id_or_null,
                    self.model_version_or_null,
                    self.calibration_version_or_null,
                    self.p_net_positive_or_null,
                    self.expected_net_return_or_null,
                    self.return_q10_or_null,
                    self.return_q50_or_null,
                    self.return_q90_or_null,
                    self.uncertainty_score_or_null,
                    self.ood_score_or_null,
                )
            ):
                raise ContractError("NO_AI_BASE model and prediction fields must be null")
        else:
            if self.no_ai_base_version_or_null is not None:
                raise ContractError("MODEL decision cannot carry a NO_AI_BASE version")
            if not self.model_id_or_null or not self.model_version_or_null:
                raise ContractError("MODEL decision requires model identity")
            if self.deployment_stage in (DeploymentStage.SHADOW, DeploymentStage.RETIRED):
                if self.eligible:
                    raise ContractError("Shadow/Retired model cannot be formally eligible")

        if self.eligible and self.ineligibility_reason_mask:
            raise ContractError("eligible decision cannot carry ineligibility reasons")
        if not self.eligible and not self.ineligibility_reason_mask:
            raise ContractError("ineligible decision requires a reason mask")
        if (
            not self.eligible
            and self.recommended_action is not TargetAction.FREEZE_INCREASES
            and not (
                self.recommended_action is TargetAction.FLATTEN
                and self.hard_risk_authorized
            )
        ):
            raise ContractError("ineligible decision must freeze increases or hard-flatten")

        bucket = self.recommended_bucket_or_null
        if self.recommended_action in _NUMERIC_TARGET_ACTIONS:
            if bucket is None or bucket.value not in _ALLOWED_NONZERO_BUCKETS:
                raise ContractError("SET_TARGET/REDUCE_TO requires 0.25/0.5/0.75/1 bucket")
        elif self.recommended_action is TargetAction.FLATTEN:
            if bucket is None or bucket.value != 0:
                raise ContractError("FLATTEN requires an explicit zero bucket")
            if not self.hard_risk_authorized:
                raise ContractError("only hard risk authority may emit FLATTEN")
        elif bucket is not None:
            raise ContractError("non-numeric meta action requires a null bucket")

        for field_name in ("p_net_positive_or_null", "uncertainty_score_or_null", "ood_score_or_null"):
            value = getattr(self, field_name)
            if value is not None and not Decimal("0") <= value <= Decimal("1"):
                raise ContractError(f"{field_name} must be in [0, 1]")
        quantiles = (
            self.return_q10_or_null,
            self.return_q50_or_null,
            self.return_q90_or_null,
        )
        if all(value is not None for value in quantiles):
            q10, q50, q90 = quantiles
            if not q10 <= q50 <= q90:
                raise ContractError("return quantiles must be ordered q10 <= q50 <= q90")

    def business_payload(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "proposal_id": self.proposal_id,
            "decision_source": self.decision_source.value,
            "no_ai_base_version_or_null": self.no_ai_base_version_or_null,
            "model_id_or_null": self.model_id_or_null,
            "model_version_or_null": self.model_version_or_null,
            "deployment_stage": self.deployment_stage.value,
            "calibration_version_or_null": self.calibration_version_or_null,
            "p_net_positive_or_null": (
                None
                if self.p_net_positive_or_null is None
                else canonical_decimal(self.p_net_positive_or_null)
            ),
            "expected_net_return_or_null": (
                None
                if self.expected_net_return_or_null is None
                else canonical_decimal(self.expected_net_return_or_null)
            ),
            "return_q10_or_null": (
                None
                if self.return_q10_or_null is None
                else canonical_decimal(self.return_q10_or_null)
            ),
            "return_q50_or_null": (
                None
                if self.return_q50_or_null is None
                else canonical_decimal(self.return_q50_or_null)
            ),
            "return_q90_or_null": (
                None
                if self.return_q90_or_null is None
                else canonical_decimal(self.return_q90_or_null)
            ),
            "uncertainty_score_or_null": (
                None
                if self.uncertainty_score_or_null is None
                else canonical_decimal(self.uncertainty_score_or_null)
            ),
            "ood_score_or_null": (
                None
                if self.ood_score_or_null is None
                else canonical_decimal(self.ood_score_or_null)
            ),
            "eligible": self.eligible,
            "ineligibility_reason_mask": self.ineligibility_reason_mask,
            "recommended_action": self.recommended_action.value,
            "recommended_bucket_or_null": (
                None
                if self.recommended_bucket_or_null is None
                else str(self.recommended_bucket_or_null)
            ),
            "model_input_hash": self.model_input_hash,
            "prediction_hash": self.prediction_hash,
            "hard_risk_authorized": self.hard_risk_authorized,
        }

    @property
    def meta_decision_id(self) -> str:
        return stable_id("meta", self.business_payload())

    @property
    def prediction_business_hash(self) -> str:
        return business_hash(self.business_payload())


@dataclass(frozen=True)
class TargetPosition:
    schema_version: str
    target_sequence: int
    supersedes_target_id_or_null: Optional[str]
    instrument_id: str
    account_id: str
    target_action: TargetAction
    direction: Direction
    signed_target_ratio_or_null: Optional[Decimal]
    risk_bucket_or_null: Optional[RiskRatio]
    base_volatility_exposure: RiskRatio
    target_notional_usdt_or_null: Optional[Decimal]
    volatility_target: Decimal
    volatility_estimator_version: str
    decision_time: datetime
    valid_until: datetime
    minimum_hold_until: datetime
    hysteresis_state: str
    source_proposal_id: str
    source_meta_decision_id: str
    position_policy_version: str

    def __post_init__(self) -> None:
        ratio = _optional_decimal(self.signed_target_ratio_or_null)
        notional = _optional_decimal(self.target_notional_usdt_or_null)
        vol_target = as_decimal(self.volatility_target)
        if self.target_sequence < 0:
            raise ContractError("target_sequence cannot be negative")
        if self.valid_until <= self.decision_time:
            raise ContractError("target valid_until must be after decision_time")
        if not self.decision_time <= self.minimum_hold_until <= self.valid_until:
            raise ContractError("minimum_hold_until must be inside the target validity window")
        if vol_target != Decimal("0.12"):
            raise ContractError("V1 volatility target must be 0.12")
        symbol = self.instrument_id.rsplit(":", 1)[-1]
        if not symbol.startswith("ETH"):
            raise ContractError("V1 formal TargetPosition is restricted to ETH")
        if self.target_action in _NUMERIC_TARGET_ACTIONS:
            if self.direction is Direction.LONG and ":SPOT:" not in self.instrument_id:
                raise ContractError("V1 LONG target must use unlevered spot")
            if (
                self.direction is Direction.SHORT
                and ":USDT_PERP:" not in self.instrument_id
            ):
                raise ContractError("V1 SHORT target must use USDT perpetual")

        if self.target_action in _NUMERIC_TARGET_ACTIONS:
            bucket = self.risk_bucket_or_null
            if ratio is None or notional is None or bucket is None:
                raise ContractError("SET_TARGET/REDUCE_TO requires all numeric target fields")
            if bucket.value not in _ALLOWED_NONZERO_BUCKETS:
                raise ContractError("numeric target requires 0.25/0.5/0.75/1 bucket")
            if notional < 0:
                raise ContractError("target notional cannot be negative")
            sign = Decimal("-1") if self.direction is Direction.SHORT else Decimal("1")
            if self.direction is Direction.FLAT:
                raise ContractError("numeric target direction cannot be FLAT")
            expected = sign * self.base_volatility_exposure.value * bucket.value
            if ratio != expected:
                raise ContractError("signed target ratio does not match volatility × bucket")
        elif self.target_action is TargetAction.FLATTEN:
            if (
                self.direction is not Direction.FLAT
                or ratio != 0
                or notional != 0
                or self.risk_bucket_or_null is None
                or self.risk_bucket_or_null.value != 0
            ):
                raise ContractError("FLATTEN requires FLAT and explicit zero numeric fields")
        elif self.target_action in _NON_NUMERIC_TARGET_ACTIONS:
            if ratio is not None or notional is not None or self.risk_bucket_or_null is not None:
                raise ContractError("non-numeric target action requires null numeric fields")
        else:
            raise ContractError("unknown target action")
        object.__setattr__(self, "signed_target_ratio_or_null", ratio)
        object.__setattr__(self, "target_notional_usdt_or_null", notional)
        object.__setattr__(self, "volatility_target", vol_target)

    def assert_lineage(self, proposal: StrategyProposal, meta: MetaDecision) -> None:
        if proposal.strategy_role is StrategyRole.SHADOW:
            raise ContractError("Shadow proposal cannot enter the formal target chain")
        if meta.deployment_stage in (
            DeploymentStage.CANDIDATE,
            DeploymentStage.SHADOW,
            DeploymentStage.RETIRED,
        ):
            raise ContractError("Candidate/Shadow/Retired decision cannot enter formal target")
        if self.source_proposal_id != proposal.proposal_id:
            raise ContractError("target source_proposal_id mismatch")
        if meta.proposal_id != proposal.proposal_id:
            raise ContractError("meta decision proposal lineage mismatch")
        if self.source_meta_decision_id != meta.meta_decision_id:
            raise ContractError("target source_meta_decision_id mismatch")
        if self.target_action is not meta.recommended_action:
            raise ContractError("target action differs from MetaDecision")
        if self.risk_bucket_or_null != meta.recommended_bucket_or_null:
            raise ContractError("target bucket differs from MetaDecision")
        if self.target_action in _NUMERIC_TARGET_ACTIONS and not meta.eligible:
            raise ContractError("ineligible MetaDecision cannot create a numeric target")
        if self.direction is not proposal.direction and self.target_action is not TargetAction.FLATTEN:
            raise ContractError("Meta/PositionPolicy cannot invent a different direction")

    def business_payload(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "target_sequence": self.target_sequence,
            "supersedes_target_id_or_null": self.supersedes_target_id_or_null,
            "instrument_id": self.instrument_id,
            "account_id": self.account_id,
            "target_action": self.target_action.value,
            "direction": self.direction.value,
            "signed_target_ratio_or_null": (
                None
                if self.signed_target_ratio_or_null is None
                else canonical_decimal(self.signed_target_ratio_or_null)
            ),
            "risk_bucket_or_null": (
                None if self.risk_bucket_or_null is None else str(self.risk_bucket_or_null)
            ),
            "base_volatility_exposure": str(self.base_volatility_exposure),
            "target_notional_usdt_or_null": (
                None
                if self.target_notional_usdt_or_null is None
                else canonical_decimal(self.target_notional_usdt_or_null)
            ),
            "volatility_target": canonical_decimal(self.volatility_target),
            "volatility_estimator_version": self.volatility_estimator_version,
            "decision_time": utc_datetime(self.decision_time),
            "valid_until": utc_datetime(self.valid_until),
            "minimum_hold_until": utc_datetime(self.minimum_hold_until),
            "hysteresis_state": self.hysteresis_state,
            "source_proposal_id": self.source_proposal_id,
            "source_meta_decision_id": self.source_meta_decision_id,
            "position_policy_version": self.position_policy_version,
        }

    @property
    def target_id(self) -> str:
        return stable_id("target", self.business_payload())

    @property
    def target_hash(self) -> str:
        return business_hash(self.business_payload())

    @property
    def economic_asset(self) -> str:
        return "ETH"


@dataclass(frozen=True)
class PortfolioRiskSnapshot:
    schema_version: str
    portfolio_risk_snapshot_id: str
    account_id: str
    exchange_snapshot_time: datetime
    marked_equity_usdt: Decimal
    available_balance_usdt: Decimal
    actual_deployable_capital_usdt: Decimal
    net_eth_exposure_usdt: Decimal
    gross_eth_exposure_usdt: Decimal
    active_orders_max_potential_fill_usdt: Decimal
    worst_case_gross_exposure_usdt: Decimal
    margin_used_usdt: Decimal
    effective_leverage: Decimal
    daily_loss_ratio: Decimal
    current_drawdown: RiskRatio
    instrument_metadata_versions: Tuple[str, ...]
    unresolved_order_count: int
    reconciliation_clean: bool

    def __post_init__(self) -> None:
        decimal_fields = (
            "marked_equity_usdt",
            "available_balance_usdt",
            "actual_deployable_capital_usdt",
            "net_eth_exposure_usdt",
            "gross_eth_exposure_usdt",
            "active_orders_max_potential_fill_usdt",
            "worst_case_gross_exposure_usdt",
            "margin_used_usdt",
            "effective_leverage",
            "daily_loss_ratio",
        )
        for field_name in decimal_fields:
            object.__setattr__(self, field_name, as_decimal(getattr(self, field_name)))
        if self.marked_equity_usdt <= 0:
            raise ContractError("marked equity must be positive")
        if any(
            value < 0
            for value in (
                self.available_balance_usdt,
                self.actual_deployable_capital_usdt,
                self.gross_eth_exposure_usdt,
                self.active_orders_max_potential_fill_usdt,
                self.worst_case_gross_exposure_usdt,
                self.margin_used_usdt,
                self.effective_leverage,
            )
        ):
            raise ContractError("risk snapshot magnitudes cannot be negative")
        expected_worst_case = (
            self.gross_eth_exposure_usdt + self.active_orders_max_potential_fill_usdt
        )
        if self.worst_case_gross_exposure_usdt != expected_worst_case:
            raise ContractError("worst-case gross exposure formula mismatch")
        expected_leverage = self.worst_case_gross_exposure_usdt / self.marked_equity_usdt
        if self.effective_leverage != expected_leverage:
            raise ContractError("effective leverage formula mismatch")
        if self.unresolved_order_count < 0:
            raise ContractError("unresolved order count cannot be negative")
        if not self.instrument_metadata_versions:
            raise ContractError("risk snapshot requires instrument metadata versions")

    @property
    def current_actual_ratio(self) -> Decimal:
        return self.net_eth_exposure_usdt / self.marked_equity_usdt


@dataclass(frozen=True)
class EventEnvelope:
    schema_version: str
    event_id: str
    trace_id: str
    correlation_id: str
    causation_id: Optional[str]
    run_id: str
    event_time: datetime
    available_at: datetime
    ingested_at: datetime
    recorded_at: datetime
    source: str
    payload_hash: str
    event_hash: str
    ordering_exception_reason: Optional[str] = None

    @classmethod
    def create(
        cls,
        *,
        schema_version: str,
        event_id: str,
        trace_id: str,
        correlation_id: str,
        causation_id: Optional[str],
        run_id: str,
        event_time: datetime,
        available_at: datetime,
        ingested_at: datetime,
        recorded_at: datetime,
        source: str,
        payload: Dict[str, Any],
        ordering_exception_reason: Optional[str] = None,
    ) -> "EventEnvelope":
        payload_digest = business_hash(payload)
        values = {
            "schema_version": schema_version,
            "event_id": event_id,
            "trace_id": trace_id,
            "correlation_id": correlation_id,
            "causation_id": causation_id,
            "run_id": run_id,
            "event_time": event_time,
            "available_at": available_at,
            "ingested_at": ingested_at,
            "recorded_at": recorded_at,
            "source": source,
            "payload_hash": payload_digest,
            "ordering_exception_reason": ordering_exception_reason,
        }
        body = {
            **values,
            "event_time": utc_datetime(event_time),
            "available_at": utc_datetime(available_at),
            "ingested_at": utc_datetime(ingested_at),
            "recorded_at": utc_datetime(recorded_at),
        }
        envelope = cls(event_hash=business_hash(body), **values)
        envelope.validate(payload)
        return envelope

    def body_for_hash(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "trace_id": self.trace_id,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "run_id": self.run_id,
            "event_time": utc_datetime(self.event_time),
            "available_at": utc_datetime(self.available_at),
            "ingested_at": utc_datetime(self.ingested_at),
            "recorded_at": utc_datetime(self.recorded_at),
            "source": self.source,
            "payload_hash": self.payload_hash,
            "ordering_exception_reason": self.ordering_exception_reason,
        }

    def validate(self, payload: Dict[str, Any]) -> None:
        if business_hash(payload) != self.payload_hash:
            raise ContractError("payload hash mismatch")
        if business_hash(self.body_for_hash()) != self.event_hash:
            raise ContractError("event hash mismatch")
        ordered = self.event_time <= self.available_at <= self.ingested_at <= self.recorded_at
        if not ordered and not self.ordering_exception_reason:
            raise ContractError("event timestamps are out of order without a reason code")
