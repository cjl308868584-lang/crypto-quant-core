"""Forward-only event-stream recorder for the preregistered V2 baseline."""

import json
import os
import sqlite3
import stat
from datetime import datetime, timedelta, timezone
from decimal import Context, Decimal, InvalidOperation, localcontext
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from jsonschema import Draft202012Validator

from .canonical import (
    business_hash,
    canonical_decimal,
    canonical_json,
    stable_id,
    utc_datetime,
)
from .evidence import artifact_self_hash
from .research_corpus import _publish_exact, _strict_json_bytes


_SCHEMA = "challenger-prequential-snapshot-v1.schema.json"
_ZERO_HASH = "0" * 64
_FOUR_HOURS = timedelta(hours=4)
_ONE_MILLISECOND = timedelta(milliseconds=1)
_START = datetime(2026, 7, 29, tzinfo=timezone.utc)
_CONTEXT = Context(prec=50)
_REGISTRATION_HASH = (
    "885b33d3a91eae1d5822fe12c16773a446c23e702f9a4110ef32f474157fa27f"
)
_WARNINGS = (
    "LOCAL_TIME_IS_NOT_EXTERNALLY_ANCHORED",
    "DECISIONS_ARE_RESEARCH_ONLY_AND_CANNOT_REACH_BROKER",
    "NO_HISTORICAL_BACKFILL",
    "NO_OUTCOME_OR_PROFITABILITY_CLAIM",
)


class ChallengerForwardError(ValueError):
    """The policy, input stream, state chain, or snapshot failed closed."""

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
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.endswith("Z"):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ChallengerForwardError(
                "CHALLENGER_FORWARD_TIME_INVALID"
            ) from error
    else:
        raise ChallengerForwardError("CHALLENGER_FORWARD_TIME_INVALID")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ChallengerForwardError("CHALLENGER_FORWARD_TIME_INVALID")
    converted = parsed.astimezone(timezone.utc)
    if converted.microsecond % 1000:
        raise ChallengerForwardError("CHALLENGER_FORWARD_TIME_INVALID")
    rendered = utc_datetime(converted)
    if isinstance(value, str) and rendered != value:
        raise ChallengerForwardError("CHALLENGER_FORWARD_TIME_INVALID")
    return converted, rendered


def _decimal(value: object, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str):
        raise ChallengerForwardError("CHALLENGER_FORWARD_NUMBER_INVALID")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ChallengerForwardError(
            "CHALLENGER_FORWARD_NUMBER_INVALID"
        ) from error
    if not parsed.is_finite() or (positive and parsed <= 0):
        raise ChallengerForwardError("CHALLENGER_FORWARD_NUMBER_INVALID")
    return parsed


def _registration() -> Dict[str, Any]:
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
        "episode_regeneration": (
            "FULL_EVENT_STREAM_REJECTED_ENTRY_DOES_NOT_CONSUME_WINDOW"
        ),
        "viewed_archive_status": "VIEWED_DEVELOPMENT_ONLY",
        "challenger_evaluation_status": (
            "NOT_RUN_PREREGISTERED_FORWARD_ONLY"
        ),
        "forward_validation_start": "2026-07-29T00:00:00.000Z",
    }
    actual = business_hash(contract)
    if actual != _REGISTRATION_HASH:
        raise ChallengerForwardError(
            "CHALLENGER_FORWARD_REGISTRATION_INVALID"
        )
    return {
        **contract,
        "hypothesis_registration_hash": actual,
    }


def challenger_forward_policy() -> Dict[str, Any]:
    contract = {
        "policy_version": "CHALLENGER_FORWARD_EVENT_STREAM_V1",
        "challenger_policy_id": (
            "SPOT_LONG_SMA20_COST_MARGIN_MOMENTUM_V2"
        ),
        "hypothesis_registration_hash": _REGISTRATION_HASH,
        "symbol": "ETHUSDT",
        "market": "SPOT",
        "interval": "4h",
        "forward_start": "2026-07-29T00:00:00.000Z",
        "cadence_seconds": 14400,
        "record_deadline_seconds": 14400,
        "warmup_bar_count": 21,
        "sma_window": 20,
        "momentum_lag_bars": 5,
        "sma20_distance_minimum": "0.005",
        "eth_log_return_5_threshold": "0",
        "minimum_hold_hours": 8,
        "vertical_exit_hours": 24,
        "historical_backfill_allowed": False,
        "broker_access": False,
    }
    return {**contract, "policy_hash": business_hash(contract)}


def _flat_state() -> Dict[str, Any]:
    return {
        "position_state": "FLAT",
        "episode_id_or_null": None,
        "entry_decision_time_or_null": None,
        "minimum_hold_until_or_null": None,
        "vertical_exit_at_or_null": None,
    }


def _long_state(
    *,
    episode_id: str,
    entry: str,
    minimum: str,
    vertical: str,
) -> Dict[str, Any]:
    return {
        "position_state": "LONG",
        "episode_id_or_null": episode_id,
        "entry_decision_time_or_null": entry,
        "minimum_hold_until_or_null": minimum,
        "vertical_exit_at_or_null": vertical,
    }


def _state_valid(state: object) -> bool:
    if not isinstance(state, Mapping):
        return False
    expected = {
        "position_state",
        "episode_id_or_null",
        "entry_decision_time_or_null",
        "minimum_hold_until_or_null",
        "vertical_exit_at_or_null",
    }
    if set(state) != expected:
        return False
    if state["position_state"] == "FLAT":
        return dict(state) == _flat_state()
    if state["position_state"] != "LONG":
        return False
    try:
        entry, _ = _utc(state["entry_decision_time_or_null"])
        minimum, _ = _utc(state["minimum_hold_until_or_null"])
        vertical, _ = _utc(state["vertical_exit_at_or_null"])
    except ChallengerForwardError:
        return False
    return (
        isinstance(state["episode_id_or_null"], str)
        and state["episode_id_or_null"].startswith("challenger_episode_")
        and minimum == entry + timedelta(hours=8)
        and vertical == entry + timedelta(hours=24)
    )


def _normalized_klines(
    klines: Sequence[Mapping[str, Any]],
    *,
    scheduled: datetime,
    recorded: datetime,
) -> Tuple[Dict[str, Any], ...]:
    if (
        isinstance(klines, (str, bytes))
        or not isinstance(klines, Sequence)
        or len(klines) != 21
    ):
        raise ChallengerForwardError("CHALLENGER_FORWARD_KLINES_INVALID")
    normalized = []
    previous_open = None
    for source in klines:
        if not isinstance(source, Mapping):
            raise ChallengerForwardError(
                "CHALLENGER_FORWARD_KLINES_INVALID"
            )
        try:
            opened, opened_text = _utc(source["open_time"])
            closed, closed_text = _utc(source["close_time"])
            available, available_text = _utc(source["available_at"])
            opened_price = _decimal(source["open"], positive=True)
            high = _decimal(source["high"], positive=True)
            low = _decimal(source["low"], positive=True)
            close = _decimal(source["close"], positive=True)
            row_hash = source["source_row_hash"]
        except (KeyError, TypeError) as error:
            raise ChallengerForwardError(
                "CHALLENGER_FORWARD_KLINES_INVALID"
            ) from error
        if (
            source.get("provider") != "BINANCE_PUBLIC_DATA"
            or source.get("market") != "SPOT"
            or source.get("data_family") != "KLINES"
            or source.get("symbol") != "ETHUSDT"
            or source.get("interval") != "4h"
            or closed != opened + _FOUR_HOURS - _ONE_MILLISECOND
            or available <= closed
            or available > recorded
            or (previous_open is not None and opened != previous_open + _FOUR_HOURS)
            or high < max(opened_price, close)
            or low > min(opened_price, close)
            or low > high
            or not isinstance(row_hash, str)
            or len(row_hash) != 64
            or any(character not in "0123456789abcdef" for character in row_hash)
        ):
            raise ChallengerForwardError(
                "CHALLENGER_FORWARD_KLINES_INVALID"
            )
        previous_open = opened
        normalized.append(
            {
                "provider": "BINANCE_PUBLIC_DATA",
                "market": "SPOT",
                "data_family": "KLINES",
                "symbol": "ETHUSDT",
                "interval": "4h",
                "open_time": opened_text,
                "close_time": closed_text,
                "available_at": available_text,
                "open": canonical_decimal(opened_price),
                "high": canonical_decimal(high),
                "low": canonical_decimal(low),
                "close": canonical_decimal(close),
                "source_row_hash": row_hash,
            }
        )
    if _utc(normalized[-1]["close_time"])[0] != scheduled - _ONE_MILLISECOND:
        raise ChallengerForwardError("CHALLENGER_FORWARD_SLOT_INPUT_MISMATCH")
    return tuple(normalized)


def challenger_decision_hash(decision: Mapping[str, Any]) -> str:
    return artifact_self_hash(decision, "decision_hash")


def _prior_decision_valid(decision: Mapping[str, Any]) -> bool:
    try:
        return (
            isinstance(decision, Mapping)
            and decision.get("decision_hash")
            == challenger_decision_hash(decision)
            and _state_valid(decision["state_after"])
            and decision.get("policy_hash")
            == challenger_forward_policy()["policy_hash"]
            and decision.get("hypothesis_registration_hash")
            == _REGISTRATION_HASH
        )
    except (KeyError, TypeError, ValueError):
        return False


def build_challenger_forward_decision(
    *,
    klines: Sequence[Mapping[str, Any]],
    scheduled_for: str,
    recorded_at: str,
    previous_decision: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate one contiguous prequential slot without any Broker authority."""

    scheduled, scheduled_text = _utc(scheduled_for)
    recorded, recorded_text = _utc(recorded_at)
    if (
        scheduled < _START
        or scheduled.minute
        or scheduled.second
        or scheduled.microsecond
        or scheduled.hour % 4
        or recorded < scheduled
        or recorded >= scheduled + _FOUR_HOURS
    ):
        raise ChallengerForwardError("CHALLENGER_FORWARD_SLOT_INVALID")
    if previous_decision is None:
        if scheduled != _START:
            raise ChallengerForwardError(
                "CHALLENGER_FORWARD_GENESIS_SLOT_INVALID"
            )
        sequence = 1
        previous_hash = _ZERO_HASH
        state_before = _flat_state()
    else:
        if not _prior_decision_valid(previous_decision):
            raise ChallengerForwardError(
                "CHALLENGER_FORWARD_PREVIOUS_INVALID"
            )
        prior_scheduled, _ = _utc(previous_decision["scheduled_for"])
        if scheduled != prior_scheduled + _FOUR_HOURS:
            raise ChallengerForwardError(
                "CHALLENGER_FORWARD_CONTINUITY_INVALID"
            )
        sequence = previous_decision["sequence"] + 1
        previous_hash = previous_decision["decision_hash"]
        state_before = dict(previous_decision["state_after"])
    normalized = _normalized_klines(
        klines,
        scheduled=scheduled,
        recorded=recorded,
    )
    if (
        previous_decision is not None
        and list(normalized[:-1])
        != list(previous_decision.get("input_klines", [])[1:])
    ):
        raise ChallengerForwardError(
            "CHALLENGER_FORWARD_INPUT_REVISION"
        )
    closes = tuple(_decimal(row["close"], positive=True) for row in normalized)
    latest = closes[-1]
    sma = sum(closes[:-1], Decimal("0")) / Decimal("20")
    with localcontext(_CONTEXT):
        distance = latest / sma - Decimal("1")
        momentum = (latest / closes[-6]).ln()
    distance_pass = distance >= Decimal("0.005")
    momentum_pass = momentum > 0
    facts_root = business_hash(list(normalized))
    if state_before["position_state"] == "FLAT":
        if distance_pass and momentum_pass:
            action = "ENTER_LONG"
            episode_id = stable_id(
                "challenger_episode",
                {
                    "policy_hash": challenger_forward_policy()["policy_hash"],
                    "entry_decision_time": scheduled_text,
                    "facts_root_hash": facts_root,
                },
            )
            state_after = _long_state(
                episode_id=episode_id,
                entry=scheduled_text,
                minimum=utc_datetime(scheduled + timedelta(hours=8)),
                vertical=utc_datetime(scheduled + timedelta(hours=24)),
            )
        else:
            action = "REJECT_ENTRY"
            state_after = _flat_state()
    else:
        minimum = _utc(state_before["minimum_hold_until_or_null"])[0]
        vertical = _utc(state_before["vertical_exit_at_or_null"])[0]
        if scheduled < minimum:
            action = "HOLD_LONG_MINIMUM"
            state_after = state_before
        elif latest <= sma:
            action = "EXIT_LONG_SMA20"
            state_after = _flat_state()
        elif scheduled >= vertical:
            action = "EXIT_LONG_VERTICAL_24H"
            state_after = _flat_state()
        else:
            action = "HOLD_LONG"
            state_after = state_before
    policy = challenger_forward_policy()
    identity = {
        "sequence": sequence,
        "scheduled_for": scheduled_text,
        "previous_decision_hash": previous_hash,
        "facts_root_hash": facts_root,
        "policy_hash": policy["policy_hash"],
    }
    decision = {
        "schema_version": "1.0.0",
        "decision_id": stable_id("challenger_decision", identity),
        "decision_hash": _ZERO_HASH,
        "sequence": sequence,
        "scheduled_for": scheduled_text,
        "recorded_at": recorded_text,
        "previous_decision_hash": previous_hash,
        "policy_hash": policy["policy_hash"],
        "hypothesis_registration_hash": _REGISTRATION_HASH,
        "input_facts_root_hash": facts_root,
        "input_klines": list(normalized),
        "features": {
            "latest_close": canonical_decimal(latest),
            "prior_sma20": canonical_decimal(sma),
            "eth_sma20_distance": canonical_decimal(distance),
            "eth_log_return_5": canonical_decimal(momentum),
        },
        "entry_conditions": {
            "sma20_distance_minimum": "0.005",
            "sma20_distance_pass": distance_pass,
            "eth_log_return_5_threshold": "0",
            "eth_log_return_5_pass": momentum_pass,
        },
        "state_before": state_before,
        "action": action,
        "state_after": state_after,
        "decision_eligibility": "LOCAL_PREQUENTIAL_RESEARCH_ONLY",
        "broker_eligibility": "INELIGIBLE_NO_BROKER_ACCESS",
    }
    decision["decision_hash"] = challenger_decision_hash(decision)
    return decision


def challenger_decision_reasons(
    decision: Mapping[str, Any],
    *,
    previous_decision: Optional[Mapping[str, Any]],
) -> Tuple[str, ...]:
    reasons = []
    try:
        if decision.get("decision_hash") != challenger_decision_hash(decision):
            reasons.append("CHALLENGER_FORWARD_DECISION_HASH_MISMATCH")
        rebuilt = build_challenger_forward_decision(
            klines=decision["input_klines"],
            scheduled_for=decision["scheduled_for"],
            recorded_at=decision["recorded_at"],
            previous_decision=previous_decision,
        )
        if business_hash(rebuilt) != business_hash(decision):
            reasons.append("CHALLENGER_FORWARD_DECISION_SEMANTIC_MISMATCH")
    except (KeyError, TypeError, ValueError, ChallengerForwardError):
        reasons.append("CHALLENGER_FORWARD_DECISION_INVALID")
    return tuple(sorted(set(reasons)))


class ChallengerForwardState:
    """Owner-only append-only WAL of consecutive challenger decisions."""

    def __init__(self, path: Path):
        requested_path = Path(path).expanduser()
        if requested_path.is_symlink():
            raise ChallengerForwardError("CHALLENGER_FORWARD_STATE_INVALID")
        self.path = requested_path.resolve()
        if self.path.exists() and (
            self.path.is_symlink()
            or not stat.S_ISREG(self.path.stat().st_mode)
        ):
            raise ChallengerForwardError("CHALLENGER_FORWARD_STATE_INVALID")
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        self._connection = sqlite3.connect(str(self.path))
        os.chmod(self.path, 0o600)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._initialize()
        self.replay()
        self._secure_sqlite_files()

    def _secure_sqlite_files(self) -> None:
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(f"{self.path}{suffix}")
            if candidate.exists():
                os.chmod(candidate, 0o600)

    def _initialize(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                policy_hash TEXT NOT NULL,
                registration_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS decisions (
                sequence INTEGER PRIMARY KEY,
                scheduled_for TEXT NOT NULL UNIQUE,
                decision_id TEXT NOT NULL UNIQUE,
                decision_hash TEXT NOT NULL UNIQUE,
                decision_bytes BLOB NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS decisions_no_update
            BEFORE UPDATE ON decisions
            BEGIN
                SELECT RAISE(ABORT, 'CHALLENGER_FORWARD_APPEND_ONLY');
            END;
            CREATE TRIGGER IF NOT EXISTS decisions_no_delete
            BEFORE DELETE ON decisions
            BEGIN
                SELECT RAISE(ABORT, 'CHALLENGER_FORWARD_APPEND_ONLY');
            END;
            """
        )
        policy = challenger_forward_policy()
        existing = self._connection.execute(
            "SELECT policy_hash, registration_hash FROM metadata WHERE singleton=1"
        ).fetchone()
        if existing is None:
            self._connection.execute(
                "INSERT INTO metadata(singleton, policy_hash, registration_hash) "
                "VALUES(1, ?, ?)",
                (policy["policy_hash"], _REGISTRATION_HASH),
            )
            self._connection.commit()
            self._secure_sqlite_files()
        elif (
            existing["policy_hash"] != policy["policy_hash"]
            or existing["registration_hash"] != _REGISTRATION_HASH
        ):
            raise ChallengerForwardError(
                "CHALLENGER_FORWARD_STATE_BINDING_MISMATCH"
            )

    def close(self) -> None:
        self._connection.close()
        self._secure_sqlite_files()

    def __enter__(self) -> "ChallengerForwardState":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def _rows(self) -> Tuple[sqlite3.Row, ...]:
        return tuple(
            self._connection.execute(
                "SELECT sequence, scheduled_for, decision_id, decision_hash, "
                "decision_bytes FROM decisions ORDER BY sequence"
            ).fetchall()
        )

    def replay(self) -> Tuple[Mapping[str, Any], ...]:
        decisions = []
        previous = None
        for expected, row in enumerate(self._rows(), 1):
            try:
                decision = _strict_json_bytes(bytes(row["decision_bytes"]))
            except Exception as error:
                raise ChallengerForwardError(
                    "CHALLENGER_FORWARD_STATE_CORRUPT"
                ) from error
            if (
                row["sequence"] != expected
                or row["scheduled_for"] != decision.get("scheduled_for")
                or row["decision_id"] != decision.get("decision_id")
                or row["decision_hash"] != decision.get("decision_hash")
                or challenger_decision_reasons(
                    decision,
                    previous_decision=previous,
                )
            ):
                raise ChallengerForwardError(
                    "CHALLENGER_FORWARD_STATE_CORRUPT"
                )
            decisions.append(decision)
            previous = decision
        return tuple(decisions)

    def append(
        self,
        *,
        klines: Sequence[Mapping[str, Any]],
        scheduled_for: str,
        recorded_at: str,
    ) -> Mapping[str, Any]:
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            existing = self._connection.execute(
                "SELECT sequence, decision_bytes FROM decisions "
                "WHERE scheduled_for=?",
                (scheduled_for,),
            ).fetchone()
            if existing is not None:
                prior = (
                    self._connection.execute(
                        "SELECT decision_bytes FROM decisions WHERE sequence=?",
                        (existing["sequence"] - 1,),
                    ).fetchone()
                    if existing["sequence"] > 1
                    else None
                )
                previous = (
                    _strict_json_bytes(bytes(prior["decision_bytes"]))
                    if prior is not None
                    else None
                )
                candidate = build_challenger_forward_decision(
                    klines=klines,
                    scheduled_for=scheduled_for,
                    recorded_at=recorded_at,
                    previous_decision=previous,
                )
                stored = _strict_json_bytes(bytes(existing["decision_bytes"]))
                if canonical_json(candidate) != canonical_json(stored):
                    raise ChallengerForwardError(
                        "CHALLENGER_FORWARD_SLOT_CONFLICT"
                    )
                self._connection.rollback()
                self._secure_sqlite_files()
                return stored
            rows = self._rows()
            previous = (
                _strict_json_bytes(bytes(rows[-1]["decision_bytes"]))
                if rows
                else None
            )
            decision = build_challenger_forward_decision(
                klines=klines,
                scheduled_for=scheduled_for,
                recorded_at=recorded_at,
                previous_decision=previous,
            )
            payload = canonical_json(decision).encode("utf-8")
            self._connection.execute(
                "INSERT INTO decisions(sequence, scheduled_for, decision_id, "
                "decision_hash, decision_bytes) VALUES(?, ?, ?, ?, ?)",
                (
                    decision["sequence"],
                    decision["scheduled_for"],
                    decision["decision_id"],
                    decision["decision_hash"],
                    payload,
                ),
            )
            self._connection.commit()
            self._secure_sqlite_files()
            return decision
        except Exception:
            if self._connection.in_transaction:
                self._connection.rollback()
            raise


def challenger_snapshot_hash(snapshot: Mapping[str, Any]) -> str:
    return artifact_self_hash(snapshot, "snapshot_hash")


def build_challenger_prequential_snapshot(
    *,
    state: ChallengerForwardState,
    recorded_at: str,
) -> Dict[str, Any]:
    _, recorded_text = _utc(recorded_at)
    decisions = list(state.replay())
    if not decisions:
        raise ChallengerForwardError("CHALLENGER_FORWARD_NO_DECISIONS")
    last_recorded = _utc(decisions[-1]["recorded_at"])[0]
    if _utc(recorded_text)[0] < last_recorded:
        raise ChallengerForwardError("CHALLENGER_FORWARD_TIME_INVALID")
    actions = {}
    for decision in decisions:
        actions[decision["action"]] = actions.get(decision["action"], 0) + 1
    policy = challenger_forward_policy()
    decisions_root = business_hash(decisions)
    identity = {
        "policy_hash": policy["policy_hash"],
        "decisions_root_hash": decisions_root,
        "chain_end_hash": decisions[-1]["decision_hash"],
    }
    snapshot = {
        "$schema": "./challenger-prequential-snapshot-v1.schema.json",
        "schema_version": "1.0.0",
        "snapshot_id": stable_id("challenger_prequential_snapshot", identity),
        "snapshot_hash": _ZERO_HASH,
        "recorded_at": recorded_text,
        "policy": policy,
        "hypothesis_registration": _registration(),
        "decisions": decisions,
        "decisions_root_hash": decisions_root,
        "decision_chain_end_hash": decisions[-1]["decision_hash"],
        "summary": {
            "decision_count": len(decisions),
            "first_scheduled_for": decisions[0]["scheduled_for"],
            "last_scheduled_for": decisions[-1]["scheduled_for"],
            "entry_count": actions.get("ENTER_LONG", 0),
            "rejected_entry_count": actions.get("REJECT_ENTRY", 0),
            "minimum_hold_count": actions.get("HOLD_LONG_MINIMUM", 0),
            "hold_count": actions.get("HOLD_LONG", 0),
            "sma_exit_count": actions.get("EXIT_LONG_SMA20", 0),
            "vertical_exit_count": actions.get(
                "EXIT_LONG_VERTICAL_24H",
                0,
            ),
            "ending_position_state": decisions[-1]["state_after"][
                "position_state"
            ],
            "missed_slot_count": 0,
        },
        "continuity_status": "CONTIGUOUS_FROM_REGISTERED_START",
        "state_integrity": "VERIFIED_APPEND_ONLY_WAL_AND_SEMANTIC_REPLAY",
        "external_time_anchoring_status": "UNANCHORED_LOCAL_CLOCK",
        "forward_evidence_eligibility": (
            "LOCAL_PREQUENTIAL_RESEARCH_ONLY"
        ),
        "paper_eligibility": "INELIGIBLE_NO_OUTCOME_OR_EXTERNAL_TIME_ANCHOR",
        "release_oos_eligibility": "INELIGIBLE_FORWARD_COLLECTION_ONLY",
        "profitability_eligibility": "INELIGIBLE",
        "warnings": list(_WARNINGS),
    }
    snapshot["snapshot_hash"] = challenger_snapshot_hash(snapshot)
    if tuple(_validator().iter_errors(snapshot)):
        raise ChallengerForwardError("CHALLENGER_FORWARD_SNAPSHOT_SCHEMA_INVALID")
    return snapshot


def challenger_snapshot_reasons(
    snapshot: Mapping[str, Any],
) -> Tuple[str, ...]:
    reasons = []
    if not isinstance(snapshot, Mapping):
        return ("CHALLENGER_FORWARD_SNAPSHOT_INVALID",)
    try:
        if tuple(_validator().iter_errors(snapshot)):
            reasons.append("CHALLENGER_FORWARD_SNAPSHOT_SCHEMA_INVALID")
        if snapshot.get("snapshot_hash") != challenger_snapshot_hash(snapshot):
            reasons.append("CHALLENGER_FORWARD_SNAPSHOT_HASH_MISMATCH")
        decisions = snapshot["decisions"]
        previous = None
        for decision in decisions:
            reasons.extend(
                challenger_decision_reasons(
                    decision,
                    previous_decision=previous,
                )
            )
            previous = decision
        if business_hash(decisions) != snapshot["decisions_root_hash"]:
            reasons.append("CHALLENGER_FORWARD_DECISIONS_ROOT_MISMATCH")
        if decisions[-1]["decision_hash"] != snapshot[
            "decision_chain_end_hash"
        ]:
            reasons.append("CHALLENGER_FORWARD_CHAIN_END_MISMATCH")
        policy = challenger_forward_policy()
        if snapshot["policy"] != policy:
            reasons.append("CHALLENGER_FORWARD_POLICY_MISMATCH")
        if snapshot["hypothesis_registration"] != _registration():
            reasons.append("CHALLENGER_FORWARD_REGISTRATION_MISMATCH")
        expected_actions = {}
        for decision in decisions:
            expected_actions[decision["action"]] = (
                expected_actions.get(decision["action"], 0) + 1
            )
        expected_summary = {
            "decision_count": len(decisions),
            "first_scheduled_for": decisions[0]["scheduled_for"],
            "last_scheduled_for": decisions[-1]["scheduled_for"],
            "entry_count": expected_actions.get("ENTER_LONG", 0),
            "rejected_entry_count": expected_actions.get("REJECT_ENTRY", 0),
            "minimum_hold_count": expected_actions.get(
                "HOLD_LONG_MINIMUM",
                0,
            ),
            "hold_count": expected_actions.get("HOLD_LONG", 0),
            "sma_exit_count": expected_actions.get("EXIT_LONG_SMA20", 0),
            "vertical_exit_count": expected_actions.get(
                "EXIT_LONG_VERTICAL_24H",
                0,
            ),
            "ending_position_state": decisions[-1]["state_after"][
                "position_state"
            ],
            "missed_slot_count": 0,
        }
        if snapshot["summary"] != expected_summary:
            reasons.append("CHALLENGER_FORWARD_SUMMARY_MISMATCH")
    except (KeyError, TypeError, ValueError, ChallengerForwardError):
        reasons.append("CHALLENGER_FORWARD_SNAPSHOT_SEMANTIC_INVALID")
    return tuple(sorted(set(reasons)))


def publish_challenger_prequential_snapshot(
    *,
    snapshot: Mapping[str, Any],
    output_path: Path,
) -> None:
    if challenger_snapshot_reasons(snapshot):
        raise ChallengerForwardError("CHALLENGER_FORWARD_SNAPSHOT_INVALID")
    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    try:
        _publish_exact(path, canonical_json(snapshot).encode("utf-8"))
    except ValueError as error:
        raise ChallengerForwardError(
            "CHALLENGER_FORWARD_SNAPSHOT_PUBLISH_CONFLICT"
        ) from error


def load_challenger_prequential_snapshot(
    path: Path,
) -> Mapping[str, Any]:
    try:
        snapshot = _strict_json_bytes(
            Path(path).expanduser().resolve().read_bytes()
        )
    except (OSError, ValueError) as error:
        raise ChallengerForwardError(
            "CHALLENGER_FORWARD_SNAPSHOT_READ_FAILED"
        ) from error
    if challenger_snapshot_reasons(snapshot):
        raise ChallengerForwardError("CHALLENGER_FORWARD_SNAPSHOT_INVALID")
    return snapshot
