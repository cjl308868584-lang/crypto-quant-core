"""Risk, target supersession, intent, and child-attempt domain contracts."""

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from .canonical import business_hash, canonical_decimal, stable_id, utc_datetime
from .contracts import (
    DeploymentStage,
    Direction,
    PortfolioRiskSnapshot,
    StrategyProposal,
    TargetAction,
    TargetPosition,
)
from .decimal_math import RiskRatio, as_decimal
from .errors import ContractError


class RegistryStatus(str, Enum):
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class RiskLockScope(str, Enum):
    GLOBAL = "GLOBAL"
    ACCOUNT = "ACCOUNT"
    INSTRUMENT = "INSTRUMENT"
    MODEL = "MODEL"


class RiskLockType(str, Enum):
    STARTUP = "STARTUP"
    DATA_STALE = "DATA_STALE"
    MODEL_INVALID = "MODEL_INVALID"
    ORDER_UNKNOWN = "ORDER_UNKNOWN"
    POSITION_MISMATCH = "POSITION_MISMATCH"
    CONNECTIVITY = "CONNECTIVITY"
    DAILY_LOSS = "DAILY_LOSS"
    DRAWDOWN_10 = "DRAWDOWN_10"
    DRAWDOWN_12 = "DRAWDOWN_12"
    DRAWDOWN_15 = "DRAWDOWN_15"
    DRAWDOWN_20 = "DRAWDOWN_20"
    DISASTER_STOP_MISSING = "DISASTER_STOP_MISSING"
    PROTECTIVE_REPLACE = "PROTECTIVE_REPLACE"
    COMPLIANCE = "COMPLIANCE"
    EXTERNAL_POSITION = "EXTERNAL_POSITION"
    MANUAL = "MANUAL"


class RiskDecisionAction(str, Enum):
    HOLD_CURRENT = "HOLD_CURRENT"
    FREEZE_INCREASES = "FREEZE_INCREASES"
    ALLOW = "ALLOW"
    CLAMP = "CLAMP"
    REDUCE_ONLY = "REDUCE_ONLY"
    FLATTEN = "FLATTEN"
    BLOCK = "BLOCK"


class IntentStatus(str, Enum):
    PLANNED = "PLANNED"
    ACTIVE = "ACTIVE"
    SATISFIED = "SATISFIED"
    CANCELED = "CANCELED"
    EXPIRED = "EXPIRED"
    BLOCKED_UNKNOWN = "BLOCKED_UNKNOWN"


class OrderPolicy(str, Enum):
    MARKET = "MARKET"
    AGGRESSIVE_LIMIT = "AGGRESSIVE_LIMIT"
    PASSIVE_LIMIT = "PASSIVE_LIMIT"


class AttemptReason(str, Enum):
    INITIAL = "INITIAL"
    REPRICE = "REPRICE"
    RESIDUAL = "RESIDUAL"


class TargetAcceptance(str, Enum):
    ACCEPTED = "ACCEPTED"
    DUPLICATE = "DUPLICATE"
    IGNORED_STALE = "IGNORED_STALE"


class ProposalAcceptance(str, Enum):
    ACCEPTED = "ACCEPTED"
    DUPLICATE = "DUPLICATE"


_STAGE_MULTIPLIERS = {
    DeploymentStage.CANDIDATE: Decimal("0"),
    DeploymentStage.SHADOW: Decimal("0"),
    DeploymentStage.PAPER: Decimal("0"),
    DeploymentStage.CANARY_25: Decimal("0.25"),
    DeploymentStage.CANARY_50: Decimal("0.5"),
    DeploymentStage.CANARY_75: Decimal("0.75"),
    DeploymentStage.CHAMPION: Decimal("1"),
}


def _sha256(value: str, field_name: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ContractError(f"{field_name} must be a lowercase SHA-256 digest")


def _same_direction_or_zero(left: Decimal, right: Decimal) -> bool:
    return left == 0 or right == 0 or left.is_signed() == right.is_signed()


def _freeze_cap(current: Decimal, requested: Decimal) -> Decimal:
    if not _same_direction_or_zero(current, requested):
        return Decimal("0")
    if abs(requested) <= abs(current):
        return requested
    return current


@dataclass(frozen=True)
class DeploymentRegistryRecord:
    schema_version: str
    deployment_line_id: str
    release_route: str
    recipe_release_id: str
    recipe_release_hash: str
    direction: Direction
    venue: str
    stage: DeploymentStage
    authoritative_stage_multiplier: RiskRatio
    approved_production_capital_usdt: Decimal
    break_even_capital_lcb_root_usdt: Decimal
    actual_deployable_capital_usdt_at_approval: Decimal
    capital_gate_evidence_hash: str
    active_model_bundle_id_or_no_ai_base_version: str
    approved_fallback_record_id_or_null: Optional[str]
    effective_from: datetime
    expires_at: datetime
    release_gate_policy_hash: str
    required_policy_bundle_hash: str
    approval_evidence_hash: str
    status: RegistryStatus

    def __post_init__(self) -> None:
        if self.stage not in _STAGE_MULTIPLIERS:
            raise ContractError("deployment stage has no V1 authoritative multiplier")
        if self.authoritative_stage_multiplier.value != _STAGE_MULTIPLIERS[self.stage]:
            raise ContractError("stage multiplier does not match the frozen deployment stage")
        approved = as_decimal(self.approved_production_capital_usdt)
        break_even = as_decimal(self.break_even_capital_lcb_root_usdt)
        actual = as_decimal(self.actual_deployable_capital_usdt_at_approval)
        if approved <= 0 or break_even <= 0:
            raise ContractError("approved and break-even capital must be positive")
        if actual < approved or actual < break_even:
            raise ContractError("approval capital must satisfy approved and break-even gates")
        if self.expires_at <= self.effective_from:
            raise ContractError("deployment registry expiry must follow effective_from")
        if self.release_route not in ("BASELINE_ONLY", "AI_ENHANCED"):
            raise ContractError("unknown release route")
        for field_name in (
            "recipe_release_hash",
            "capital_gate_evidence_hash",
            "release_gate_policy_hash",
            "required_policy_bundle_hash",
            "approval_evidence_hash",
        ):
            _sha256(getattr(self, field_name), field_name)
        object.__setattr__(self, "approved_production_capital_usdt", approved)
        object.__setattr__(self, "break_even_capital_lcb_root_usdt", break_even)
        object.__setattr__(
            self,
            "actual_deployable_capital_usdt_at_approval",
            actual,
        )

    def is_effective(self, at: datetime) -> bool:
        return (
            self.status is RegistryStatus.ACTIVE
            and self.effective_from <= at < self.expires_at
        )


@dataclass(frozen=True)
class RiskLock:
    schema_version: str
    lock_type: RiskLockType
    scope: RiskLockScope
    scope_id: str
    activated_at: datetime
    trigger_value: str
    policy_version: str
    allowed_actions: Tuple[RiskDecisionAction, ...]
    release_condition: str
    requires_manual_release: bool
    released_at: Optional[datetime] = None
    release_reason: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.allowed_actions:
            raise ContractError("RiskLock must declare allowed actions")
        if not {
            RiskDecisionAction.REDUCE_ONLY,
            RiskDecisionAction.FLATTEN,
        }.issubset(self.allowed_actions):
            raise ContractError("RiskLock cannot block protective reduction or flatten")
        if (self.released_at is None) != (self.release_reason is None):
            raise ContractError("released_at and release_reason must appear together")
        if self.released_at is not None and self.released_at < self.activated_at:
            raise ContractError("RiskLock cannot be released before activation")

    @property
    def lock_id(self) -> str:
        return stable_id(
            "lock",
            {
                "schema_version": self.schema_version,
                "lock_type": self.lock_type.value,
                "scope": self.scope.value,
                "scope_id": self.scope_id,
                "activated_at": utc_datetime(self.activated_at),
                "trigger_value": self.trigger_value,
                "policy_version": self.policy_version,
            },
        )

    @property
    def active(self) -> bool:
        return self.released_at is None

    def release(
        self,
        *,
        released_at: datetime,
        release_reason: str,
        manual_approved: bool,
    ) -> "RiskLock":
        if not self.active:
            raise ContractError("RiskLock is already released")
        if self.requires_manual_release and not manual_approved:
            raise ContractError("RiskLock requires manual release approval")
        return replace(
            self,
            released_at=released_at,
            release_reason=release_reason,
        )


@dataclass(frozen=True)
class RiskDecision:
    schema_version: str
    input_target_id: str
    portfolio_risk_snapshot_id: str
    action: RiskDecisionAction
    before_target_ratio_or_null: Optional[Decimal]
    after_target_ratio: Decimal
    current_actual_ratio: Decimal
    before_notional_usdt: Decimal
    after_notional_usdt: Decimal
    approved_deployment_stage: DeploymentStage
    authoritative_stage_multiplier: RiskRatio
    stage_capped_target_ratio: Decimal
    deployment_registry_version: str
    triggered_limits: Tuple[str, ...]
    active_lock_ids: Tuple[str, ...]
    daily_loss_ratio: Decimal
    current_drawdown: RiskRatio
    available_equity_usdt: Decimal
    policy_version: str
    reason_codes: Tuple[str, ...]

    def __post_init__(self) -> None:
        numeric_fields = (
            "after_target_ratio",
            "current_actual_ratio",
            "before_notional_usdt",
            "after_notional_usdt",
            "stage_capped_target_ratio",
            "daily_loss_ratio",
            "available_equity_usdt",
        )
        for field_name in numeric_fields:
            object.__setattr__(self, field_name, as_decimal(getattr(self, field_name)))
        before = (
            None
            if self.before_target_ratio_or_null is None
            else as_decimal(self.before_target_ratio_or_null)
        )
        object.__setattr__(self, "before_target_ratio_or_null", before)
        if before is not None:
            if abs(self.after_target_ratio) > abs(before):
                raise ContractError("RiskDecision cannot increase target magnitude")
            if not _same_direction_or_zero(before, self.after_target_ratio):
                raise ContractError("RiskDecision cannot reverse target direction")
        if not _same_direction_or_zero(
            self.current_actual_ratio,
            self.after_target_ratio,
        ):
            raise ContractError("RiskDecision cannot directly reverse actual direction")
        if abs(self.after_target_ratio) > Decimal("1"):
            raise ContractError("RiskDecision after ratio cannot exceed 1x")
        expected_multiplier = _STAGE_MULTIPLIERS.get(self.approved_deployment_stage)
        if (
            expected_multiplier is None
            or self.authoritative_stage_multiplier.value != expected_multiplier
        ):
            raise ContractError("RiskDecision stage multiplier is not authoritative")
        if self.action is RiskDecisionAction.FLATTEN and self.after_target_ratio != 0:
            raise ContractError("FLATTEN RiskDecision must target zero")
        if self.action is RiskDecisionAction.HOLD_CURRENT:
            if self.after_target_ratio != self.current_actual_ratio:
                raise ContractError("HOLD_CURRENT must equal actual exposure")
        if self.action in (
            RiskDecisionAction.FREEZE_INCREASES,
            RiskDecisionAction.REDUCE_ONLY,
            RiskDecisionAction.BLOCK,
        ) and abs(self.after_target_ratio) > abs(self.current_actual_ratio):
            raise ContractError("locked RiskDecision cannot increase actual risk")
        if self.available_equity_usdt < 0:
            raise ContractError("available equity cannot be negative")

    def business_payload(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "input_target_id": self.input_target_id,
            "portfolio_risk_snapshot_id": self.portfolio_risk_snapshot_id,
            "action": self.action.value,
            "before_target_ratio_or_null": (
                None
                if self.before_target_ratio_or_null is None
                else canonical_decimal(self.before_target_ratio_or_null)
            ),
            "after_target_ratio": canonical_decimal(self.after_target_ratio),
            "current_actual_ratio": canonical_decimal(self.current_actual_ratio),
            "before_notional_usdt": canonical_decimal(self.before_notional_usdt),
            "after_notional_usdt": canonical_decimal(self.after_notional_usdt),
            "approved_deployment_stage": self.approved_deployment_stage.value,
            "authoritative_stage_multiplier": str(
                self.authoritative_stage_multiplier
            ),
            "stage_capped_target_ratio": canonical_decimal(
                self.stage_capped_target_ratio
            ),
            "deployment_registry_version": self.deployment_registry_version,
            "triggered_limits": self.triggered_limits,
            "active_lock_ids": self.active_lock_ids,
            "daily_loss_ratio": canonical_decimal(self.daily_loss_ratio),
            "current_drawdown": str(self.current_drawdown),
            "available_equity_usdt": canonical_decimal(self.available_equity_usdt),
            "policy_version": self.policy_version,
            "reason_codes": self.reason_codes,
        }

    @property
    def risk_decision_id(self) -> str:
        return stable_id("risk", self.business_payload())

    @property
    def risk_decision_hash(self) -> str:
        return business_hash(self.business_payload())


class RiskGate:
    """Deterministically apply registry, capital, lock, and 1x limits."""

    _FLATTEN_LOCKS = {
        RiskLockType.DAILY_LOSS,
        RiskLockType.DRAWDOWN_15,
        RiskLockType.DRAWDOWN_20,
    }

    def evaluate(
        self,
        *,
        target: TargetPosition,
        snapshot: PortfolioRiskSnapshot,
        deployment: DeploymentRegistryRecord,
        active_locks: Tuple[RiskLock, ...],
        deployment_registry_version: str,
        policy_version: str,
    ) -> RiskDecision:
        if not deployment.is_effective(target.decision_time):
            raise ContractError("deployment record is not active for target decision time")
        if not target.instrument_id.startswith(f"{deployment.venue}:"):
            raise ContractError("target venue differs from deployment approval")
        if target.target_action in (TargetAction.SET_TARGET, TargetAction.REDUCE_TO):
            if target.direction is not deployment.direction:
                raise ContractError("target direction differs from deployment approval")
            before = as_decimal(target.signed_target_ratio_or_null)
            stage_capped = before * deployment.authoritative_stage_multiplier.value
            requested = stage_capped
        elif target.target_action is TargetAction.FLATTEN:
            before = Decimal("0")
            stage_capped = Decimal("0")
            requested = Decimal("0")
        else:
            before = None
            stage_capped = snapshot.current_actual_ratio
            requested = snapshot.current_actual_ratio

        current = snapshot.current_actual_ratio
        limits = []
        reasons = []
        live_locks = tuple(lock for lock in active_locks if lock.active)
        lock_types = {lock.lock_type for lock in live_locks}

        capital_ready = (
            snapshot.actual_deployable_capital_usdt
            >= deployment.approved_production_capital_usdt
            and snapshot.actual_deployable_capital_usdt
            >= deployment.break_even_capital_lcb_root_usdt
        )
        freeze = target.target_action is TargetAction.FREEZE_INCREASES
        flatten = bool(lock_types & self._FLATTEN_LOCKS)
        if not capital_ready:
            freeze = True
            limits.append("CAPITAL_READINESS")
        if not snapshot.reconciliation_clean or snapshot.unresolved_order_count > 0:
            freeze = True
            limits.append("RECONCILIATION_OR_UNKNOWN")
        if live_locks and not flatten:
            freeze = True
            limits.extend(sorted(lock_type.value for lock_type in lock_types))

        if flatten or target.target_action is TargetAction.FLATTEN:
            after = Decimal("0")
            action = RiskDecisionAction.FLATTEN
            reasons.append("HARD_RISK_OR_EXPLICIT_FLATTEN")
        else:
            after = requested
            if RiskLockType.DRAWDOWN_12 in lock_types:
                drawdown_cap = min(abs(after), abs(current), Decimal("0.5"))
                after = drawdown_cap.copy_sign(
                    current if current != 0 else after
                )
                limits.append("DRAWDOWN_12_HALF_APPROVED_CAP")
            if freeze:
                after = _freeze_cap(current, after)
            active_order_ratio = (
                snapshot.active_orders_max_potential_fill_usdt
                / snapshot.marked_equity_usdt
            )
            remaining_capacity = max(Decimal("0"), Decimal("1") - active_order_ratio)
            if abs(after) > remaining_capacity:
                after = remaining_capacity.copy_sign(after)
                limits.append("MAX_EFFECTIVE_LEVERAGE_1X")
            if snapshot.effective_leverage > Decimal("1"):
                freeze = True
                after = _freeze_cap(current, after)
                limits.append("CURRENT_WORST_CASE_LEVERAGE_ABOVE_1X")
            if target.target_action in (
                TargetAction.NO_DECISION,
                TargetAction.HOLD_CURRENT,
            ) and not freeze and after == current:
                action = RiskDecisionAction.HOLD_CURRENT
            elif freeze:
                action = (
                    RiskDecisionAction.REDUCE_ONLY
                    if abs(after) < abs(current)
                    else RiskDecisionAction.FREEZE_INCREASES
                )
            elif before is not None and after == before:
                action = RiskDecisionAction.ALLOW
            else:
                action = RiskDecisionAction.CLAMP

        if before is not None and abs(after) > abs(before):
            after = before
            action = RiskDecisionAction.CLAMP
            limits.append("INPUT_TARGET_MAGNITUDE")
        if before is not None and not _same_direction_or_zero(before, after):
            after = Decimal("0")
            action = RiskDecisionAction.REDUCE_ONLY
            limits.append("NO_DIRECTION_REVERSAL")

        approved_capital = deployment.approved_production_capital_usdt
        if target.target_notional_usdt_or_null is None:
            before_notional = current * approved_capital
        else:
            before_notional = before * approved_capital
        after_notional = after * approved_capital
        if not reasons:
            reasons.append("POLICY_EVALUATED")
        return RiskDecision(
            schema_version=target.schema_version,
            input_target_id=target.target_id,
            portfolio_risk_snapshot_id=snapshot.portfolio_risk_snapshot_id,
            action=action,
            before_target_ratio_or_null=before,
            after_target_ratio=after,
            current_actual_ratio=current,
            before_notional_usdt=before_notional,
            after_notional_usdt=after_notional,
            approved_deployment_stage=deployment.stage,
            authoritative_stage_multiplier=deployment.authoritative_stage_multiplier,
            stage_capped_target_ratio=stage_capped,
            deployment_registry_version=deployment_registry_version,
            triggered_limits=tuple(sorted(set(limits))),
            active_lock_ids=tuple(sorted(lock.lock_id for lock in live_locks)),
            daily_loss_ratio=snapshot.daily_loss_ratio,
            current_drawdown=snapshot.current_drawdown,
            available_equity_usdt=snapshot.actual_deployable_capital_usdt,
            policy_version=policy_version,
            reason_codes=tuple(reasons),
        )


@dataclass(frozen=True)
class ExecutionIntent:
    schema_version: str
    risk_decision_id: str
    target_id: str
    instrument_id: str
    exchange_position_before: Decimal
    desired_position: Decimal
    delta_quantity: Decimal
    reduce_only: bool
    order_policy: OrderPolicy
    max_slippage_bps: Decimal
    deadline: datetime
    created_at: datetime
    intent_status: IntentStatus
    instrument_metadata_version: str

    def __post_init__(self) -> None:
        before = as_decimal(self.exchange_position_before)
        desired = as_decimal(self.desired_position)
        delta = as_decimal(self.delta_quantity)
        slippage = as_decimal(self.max_slippage_bps)
        if delta != desired - before:
            raise ContractError("intent delta must equal desired minus actual position")
        if delta == 0:
            raise ContractError("zero-delta ExecutionIntent is not an economic intent")
        if not _same_direction_or_zero(before, desired):
            raise ContractError("direction reversal requires a separate flat-confirmed intent")
        expected_reduce_only = abs(desired) < abs(before)
        if self.reduce_only != expected_reduce_only:
            raise ContractError("reduce_only does not match the actual position delta")
        if slippage < 0:
            raise ContractError("max slippage cannot be negative")
        if self.deadline <= self.created_at:
            raise ContractError("intent deadline must follow created_at")
        object.__setattr__(self, "exchange_position_before", before)
        object.__setattr__(self, "desired_position", desired)
        object.__setattr__(self, "delta_quantity", delta)
        object.__setattr__(self, "max_slippage_bps", slippage)

    def business_payload(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "risk_decision_id": self.risk_decision_id,
            "target_id": self.target_id,
            "instrument_id": self.instrument_id,
            "exchange_position_before": canonical_decimal(
                self.exchange_position_before
            ),
            "desired_position": canonical_decimal(self.desired_position),
            "delta_quantity": canonical_decimal(self.delta_quantity),
            "reduce_only": self.reduce_only,
            "order_policy": self.order_policy.value,
            "max_slippage_bps": canonical_decimal(self.max_slippage_bps),
            "deadline": utc_datetime(self.deadline),
            "created_at": utc_datetime(self.created_at),
            "intent_status": self.intent_status.value,
            "instrument_metadata_version": self.instrument_metadata_version,
        }

    @property
    def intent_id(self) -> str:
        return stable_id("intent", self.business_payload())

    @property
    def idempotency_key(self) -> str:
        return stable_id(
            "idem",
            {
                "risk_decision_id": self.risk_decision_id,
                "target_id": self.target_id,
                "instrument_id": self.instrument_id,
                "delta_quantity": canonical_decimal(self.delta_quantity),
            },
        )

    @property
    def intent_hash(self) -> str:
        return business_hash(self.business_payload())

    def assert_lineage(
        self,
        *,
        target: TargetPosition,
        risk_decision: RiskDecision,
        execution_reference_price_usdt: Decimal,
    ) -> None:
        if self.target_id != target.target_id:
            raise ContractError("ExecutionIntent target lineage mismatch")
        if self.risk_decision_id != risk_decision.risk_decision_id:
            raise ContractError("ExecutionIntent risk lineage mismatch")
        if risk_decision.input_target_id != target.target_id:
            raise ContractError("RiskDecision target lineage mismatch")
        if risk_decision.action is RiskDecisionAction.BLOCK:
            raise ContractError("BLOCK RiskDecision cannot create an ExecutionIntent")
        reference_price = as_decimal(execution_reference_price_usdt)
        if reference_price <= 0:
            raise ContractError("execution reference price must be positive")
        desired_notional = abs(self.desired_position * reference_price)
        if desired_notional > abs(risk_decision.after_notional_usdt):
            raise ContractError(
                "ExecutionIntent desired position exceeds approved risk notional"
            )


@dataclass(frozen=True)
class ChildOrderAttempt:
    schema_version: str
    intent_id: str
    attempt_no: int
    planned_quantity: Decimal
    planned_price_or_market: Optional[Decimal]
    created_reason: AttemptReason
    supersedes_attempt_id_or_null: Optional[str]

    def __post_init__(self) -> None:
        quantity = as_decimal(self.planned_quantity)
        price = (
            None
            if self.planned_price_or_market is None
            else as_decimal(self.planned_price_or_market)
        )
        if self.attempt_no < 1:
            raise ContractError("attempt_no must start at 1")
        if quantity <= 0:
            raise ContractError("attempt quantity must be positive")
        if price is not None and price <= 0:
            raise ContractError("attempt price must be positive or null for market")
        if self.attempt_no == 1:
            if (
                self.created_reason is not AttemptReason.INITIAL
                or self.supersedes_attempt_id_or_null is not None
            ):
                raise ContractError("first attempt must be INITIAL without supersession")
        elif self.supersedes_attempt_id_or_null is None:
            raise ContractError("subsequent attempt must supersede its predecessor")
        object.__setattr__(self, "planned_quantity", quantity)
        object.__setattr__(self, "planned_price_or_market", price)

    def business_payload(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "intent_id": self.intent_id,
            "attempt_no": self.attempt_no,
            "planned_quantity": canonical_decimal(self.planned_quantity),
            "planned_price_or_market": (
                "MARKET"
                if self.planned_price_or_market is None
                else canonical_decimal(self.planned_price_or_market)
            ),
            "created_reason": self.created_reason.value,
            "supersedes_attempt_id_or_null": self.supersedes_attempt_id_or_null,
        }

    @property
    def attempt_id(self) -> str:
        return stable_id("attempt", self.business_payload())

    @property
    def client_order_id(self) -> str:
        return f"cq{business_hash({'intent_id': self.intent_id, 'attempt_no': self.attempt_no})[:30]}"


class TargetBook:
    """Append-only current-target projection with explicit supersession."""

    def __init__(self) -> None:
        self._current: Dict[Tuple[str, str], TargetPosition] = {}

    def accept(self, target: TargetPosition) -> TargetAcceptance:
        key = (target.account_id, target.economic_asset)
        current = self._current.get(key)
        if current is None:
            if target.supersedes_target_id_or_null is not None:
                raise ContractError("first target cannot supersede an unknown target")
            self._current[key] = target
            return TargetAcceptance.ACCEPTED
        if target.target_sequence < current.target_sequence:
            return TargetAcceptance.IGNORED_STALE
        if target.target_sequence == current.target_sequence:
            if target.target_id == current.target_id:
                return TargetAcceptance.DUPLICATE
            raise ContractError("same target_sequence has conflicting business content")
        if target.supersedes_target_id_or_null != current.target_id:
            raise ContractError("new target must explicitly supersede current target")
        self._current[key] = target
        return TargetAcceptance.ACCEPTED

    def current(self, account_id: str, economic_asset: str) -> Optional[TargetPosition]:
        return self._current.get((account_id, economic_asset))


class ProposalBook:
    """Enforce one formal Proposal fact per strategy/instrument/decision key."""

    def __init__(self) -> None:
        self._proposals: Dict[Tuple[str, str, str], str] = {}

    def accept(self, proposal: StrategyProposal) -> ProposalAcceptance:
        key = (
            proposal.strategy_id,
            proposal.instrument_id,
            utc_datetime(proposal.created_at),
        )
        current_id = self._proposals.get(key)
        if current_id is None:
            self._proposals[key] = proposal.proposal_id
            return ProposalAcceptance.ACCEPTED
        if current_id == proposal.proposal_id:
            return ProposalAcceptance.DUPLICATE
        raise ContractError(
            "strategy/instrument/decision_time reused with different Proposal content"
        )


class AttemptBook:
    """Enforce one sequential ChildOrderAttempt chain per stable intent."""

    def __init__(self) -> None:
        self._attempts: Dict[str, Tuple[ChildOrderAttempt, ...]] = {}

    def register(
        self,
        attempt: ChildOrderAttempt,
        *,
        predecessor_terminal: bool,
        predecessor_residual_reconciled: bool,
        remaining_intent_quantity: Decimal,
    ) -> None:
        remaining = as_decimal(remaining_intent_quantity)
        if remaining <= 0:
            raise ContractError("remaining intent quantity must be positive")
        if attempt.planned_quantity > remaining:
            raise ContractError("attempt quantity exceeds reconciled remaining intent")
        chain = self._attempts.get(attempt.intent_id, ())
        if not chain:
            if attempt.attempt_no != 1:
                raise ContractError("first registered attempt must be attempt_no=1")
            self._attempts[attempt.intent_id] = (attempt,)
            return
        previous = chain[-1]
        if attempt.attempt_no == previous.attempt_no:
            if attempt.attempt_id == previous.attempt_id:
                return
            raise ContractError("attempt number reused with different content")
        if attempt.attempt_no != previous.attempt_no + 1:
            raise ContractError("attempt numbers must be contiguous")
        if attempt.supersedes_attempt_id_or_null != previous.attempt_id:
            raise ContractError("attempt must supersede the previous attempt")
        if not (predecessor_terminal or predecessor_residual_reconciled):
            raise ContractError("previous attempt remains unresolved or UNKNOWN")
        self._attempts[attempt.intent_id] = chain + (attempt,)

    def chain(self, intent_id: str) -> Tuple[ChildOrderAttempt, ...]:
        return self._attempts.get(intent_id, ())
