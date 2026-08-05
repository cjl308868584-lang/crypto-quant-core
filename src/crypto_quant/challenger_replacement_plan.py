"""Frozen preregistration for an isolated replacement Challenger cohort.

Building or loading this plan grants no runtime authority and performs no
production-path inspection, network request, process invocation, or state write.
"""

import copy
import json
import os
import stat
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_json, stable_id
from .errors import CanonicalizationError
from .evidence import artifact_self_hash


_SCHEMA = "challenger-replacement-plan-v1.schema.json"
_ZERO_HASH = "0" * 64
_MAX_PLAN_BYTES = 256 * 1024
_MAX_SAFE_INTEGER = (1 << 53) - 1


class ChallengerReplacementPlanError(ValueError):
    """The replacement Challenger plan failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _with_policy_hash(policy: Mapping[str, Any]) -> Dict[str, Any]:
    result = dict(policy)
    result["policy_hash"] = business_hash(policy)
    return result


def challenger_replacement_plan_hash(plan: Mapping[str, Any]) -> str:
    """Hash the plan while excluding only its self-hash field."""

    return artifact_self_hash(plan, "plan_hash")


def _identity(plan: Mapping[str, Any]) -> Mapping[str, Any]:
    predecessor = plan["predecessor"]
    return {
        "foundation_peeled_commit": plan["foundation"]["peeled_commit"],
        "foundation_manifest_hash": plan["foundation"]["manifest_hash"],
        "failure_receipt_id": predecessor["failure_receipt"]["receipt_id"],
        "failure_receipt_hash": predecessor["failure_receipt"]["receipt_hash"],
        "decommission_receipt_id": predecessor["decommission_receipt"][
            "receipt_id"
        ],
        "decommission_receipt_hash": predecessor["decommission_receipt"][
            "receipt_hash"
        ],
        "scope_policy_hash": plan["scope"]["policy_hash"],
        "decision_policy_hash": plan["decision_policy"]["policy_hash"],
        "cohort_policy_hash": plan["cohort_policy"]["policy_hash"],
        "isolation_policy_hash": plan["isolation_policy"]["policy_hash"],
        "evidence_policy_hash": plan["evidence_policy"]["policy_hash"],
    }


def build_challenger_replacement_plan() -> Dict[str, Any]:
    """Build the sole replacement-v1 plan without runtime side effects."""

    foundation = {
        "release_tag": "v0.61.0",
        "peeled_commit": "0811402ae4f9baebf905f548336ca2c29885ce9c",
        "package_version": "0.61.0",
        "manifest_version": "1.55.0",
        "build_input_tree_hash": "b786255726e606fd8409ad668675ae35cefbb88a4d29f80d2cb8b92323812d76",
        "manifest_hash": "e084ac0aa126824204f6f40fb89db52cd274e96abb96fd512ad6fdccd29eadb6",
        "manifest_file_sha256": "8e3b0f455238de170d55836ab0b76b1e2b41a894e540bf07c0e422a59e6e5296",
    }
    predecessor = {
        "failure_receipt": {
            "path": "artifacts/challenger-forward/challenger-cohort-missed-slot-failure-receipt-v0.54.0.json",
            "file_sha256": "7907b97d4447039c686f53dc62694c37836417b4ae555d3322b16478319b85ae",
            "receipt_id": "challenger_cohort_failure_receipt_955e47c773683f1ae4ba7997a84badc373d3daf5afb24763bdc88d1b95d30545",
            "receipt_hash": "3b2bcc2651bb80f58fb44d08ac4dfb2bdd9ab6c3ada4cfd83de00627ec8480b3",
            "failure_reason": "CHALLENGER_RUNNER_MISSED_SLOT",
            "eligibility": "PERMANENTLY_INELIGIBLE_CONTINUITY_GAP",
        },
        "decommission_receipt": {
            "path": "artifacts/challenger-forward/challenger-cohort-decommission-receipt-v0.54.0.json",
            "file_sha256": "540b831797228c950d954ee75b183fbeac08d63679463e14121fefc44fdf851f",
            "receipt_id": "challenger_cohort_decommission_receipt_30f87c50715e9f4c09b9b21072cb8c3f6fecf932d2703300adcf153fbab9323e",
            "receipt_hash": "56cfaa3f44b23e6dbc282f5947676ea93b4b92a89dcf90539a19eeb865b0bae7",
            "service_identity": "gui/501/local.crypto-quant.challenger-forward",
            "service_label": "local.crypto-quant.challenger-forward",
            "service_state_after": "NOT_LOADED",
            "service_eligibility": "DECOMMISSIONED",
        },
        "cohort_plan": {
            "path": "artifacts/challenger-forward/challenger-episode-cohort-plan-v0.43.0.json",
            "file_sha256": "a431fe2d316d8c9a647a4c45de280644e60554719603b5506670cef8a02ee7ff",
            "plan_id": "challenger_episode_cohort_plan_56fa3d25d37d5445e7c29ad7cda6cd4dac622e036ee0a017c5790fb33142ab1c",
            "plan_hash": "20575f808b0e1bb4d1f26e01cd92acae59a77c1a28f28058a9d456cdabdf5201",
        },
        "evaluation_plan": {
            "path": "artifacts/challenger-forward/challenger-cohort-evaluation-plan-v0.44.0.json",
            "file_sha256": "49e3b7642e163bb95c4ce01bc1c8d95a23b0cefce277d2f99f2e69029207a4d8",
            "plan_id": "challenger_cohort_evaluation_plan_54a5456345f57219e2ee8763fd35dd4c753e843d31709f342e283fd4026eb037",
            "plan_hash": "a6901e7e721682e6d3e7ded9000b5f183ed35e694b7036c7b596c0555a3ab440",
        },
    }
    scope = _with_policy_hash(
        {
            "mode": "REPLACEMENT_CHALLENGER_CONFIRMATORY",
            "cohort_generation": "replacement-v1",
            "route": "BASELINE_ONLY",
            "symbol": "ETHUSDT",
            "venue": "BINANCE_SPOT",
            "market": "SPOT",
            "direction": "LONG_ONLY",
            "predecessor_policy_id": "SPOT_LONG_SMA20_COST_MARGIN_MOMENTUM_V2",
            "predecessor_policy_hash": "2ef83c7c73fff8b163d9bad8527921bd0d87e60595680236e936254536c800e4",
            "hypothesis_registration_hash": "885b33d3a91eae1d5822fe12c16773a446c23e702f9a4110ef32f474157fa27f",
        }
    )
    decision_policy = _with_policy_hash(
        {
            "version": "CHALLENGER_REPLACEMENT_SMA20_MOMENTUM_V1",
            "interval": "4h",
            "warmup_bar_count": 21,
            "sma_window": 20,
            "momentum_lag_bars": 5,
            "sma20_distance_operator": "GTE",
            "sma20_distance_minimum": "0.005",
            "eth_log_return_5_operator": "GT",
            "eth_log_return_5_threshold": "0",
            "entry_rule": "ALL_CONDITIONS_REQUIRED",
            "minimum_hold_hours": 8,
            "before_minimum_action": "HOLD_LONG_MINIMUM",
            "post_minimum_sma_exit_rule": "LATEST_CLOSE_LTE_PRIOR_SMA20",
            "vertical_exit_hours": 24,
            "same_slot_sma_exit_precedes_vertical": True,
            "rejected_entry_episode_created": False,
            "same_threshold_semantics_as_predecessor": True,
            "old_fixed_forward_start_reused": False,
        }
    )
    cohort_policy = _with_policy_hash(
        {
            "duration_days": 90,
            "slot_cadence_seconds": 14_400,
            "required_slot_count": 540,
            "maximum_episode_hours": 24,
            "active_episode_after_window": "FOLLOW_TO_NATURAL_EXIT",
            "start_source": "FIRST_VERIFIED_NATURAL_SLOT_FROM_START_RECEIPT",
            "start_inclusive": None,
            "end_exclusive": None,
            "observation_tail_end": None,
            "all_slots_required": True,
            "historical_backfill_allowed": False,
            "manual_slot_allowed": False,
            "window_reset_allowed": False,
            "window_extension_allowed": False,
            "optional_stopping_allowed": False,
        }
    )
    isolation_policy = _with_policy_hash(
        {
            "service_label": "local.crypto-quant.challenger-replacement-v1",
            "service_identity": "gui/501/local.crypto-quant.challenger-replacement-v1",
            "runtime_root": "/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1",
            "target_plist": "/Users/chenm4/Library/LaunchAgents/local.crypto-quant.challenger-replacement-v1.plist",
            "relative_paths": {
                "state": "state/challenger-replacement.sqlite",
                "stdout": "log/challenger-replacement.stdout.log",
                "stderr": "log/challenger-replacement.stderr.log",
                "source_bundles": "artifacts/source-bundles",
                "decisions": "artifacts/decisions",
                "deployment_contract": "deployment/contract.json",
                "deployment_plist": "deployment/local.crypto-quant.challenger-replacement-v1.plist",
                "preflight_receipts": "preflight-receipts",
                "install_receipts": "install-receipts",
                "start_receipts": "start-receipts",
                "episode_receipts": "episode-receipts",
                "archives": "archives",
                "results": "results",
                "indexes": "indexes",
                "evaluations": "evaluations",
            },
            "forbidden_runtime_roots": [
                "/Users/chenm4/Library/Application Support/CryptoQuant/challenger-forward-v1",
                "/Users/chenm4/Library/Application Support/CryptoQuant/system-paper-v1",
                "/tmp",
                "/private/tmp",
            ],
            "directory_mode_octal": "0700",
            "file_mode_octal": "0600",
            "single_hardlink_required": True,
            "no_overwrite_required": True,
            "symlink_ancestors_forbidden": True,
            "repository_or_worktree_root_allowed": False,
            "cross_root_inode_reuse_allowed": False,
        }
    )
    evidence_policy = _with_policy_hash(
        {
            "predecessor_failure_preserved": True,
            "predecessor_decommission_preserved": True,
            "old_decisions_migrated": False,
            "old_episodes_migrated": False,
            "old_receipts_migrated": False,
            "old_archives_migrated": False,
            "old_results_migrated": False,
            "old_pnl_migrated": False,
            "old_elapsed_days_migrated": False,
            "old_slot_backfill_allowed": False,
            "all_stream_inclusion_required": True,
            "interim_economics_withheld": True,
            "evaluation_method_source": "PREDECESSOR_V0_44_PLAN_REQUIRES_REPLACEMENT_EVALUATOR",
            "first_natural_slot_required": True,
        }
    )
    plan: Dict[str, Any] = {
        "$schema": "./challenger-replacement-plan-v1.schema.json",
        "schema_version": "1.0.0",
        "plan_id": "challenger_replacement_plan_" + _ZERO_HASH,
        "plan_hash": _ZERO_HASH,
        "foundation": foundation,
        "predecessor": predecessor,
        "scope": scope,
        "decision_policy": decision_policy,
        "cohort_policy": cohort_policy,
        "isolation_policy": isolation_policy,
        "evidence_policy": evidence_policy,
        "authority": {
            "credentials_allowed": False,
            "account_requests_allowed": False,
            "broker_requests_allowed": False,
            "real_orders_allowed": False,
            "production_activation": False,
            "runtime_install_authorized": False,
            "replacement_start_authorized": False,
            "runner_invocation_count": 0,
            "market_request_count": 0,
            "state_write_count": 0,
        },
        "status": "PLAN_FROZEN_REPLACEMENT_NOT_STARTED",
        "eligibility": {
            "runtime": "INELIGIBLE_NOT_IMPLEMENTED",
            "deployment": "INELIGIBLE_NOT_IMPLEMENTED",
            "replacement_start": "INELIGIBLE_NOT_AUTHORIZED",
            "cohort_evaluation": "INELIGIBLE_90_DAY_EVIDENCE_NOT_STARTED",
            "canary": "INELIGIBLE",
            "profitability": "INELIGIBLE",
            "ai_advantage": "INELIGIBLE",
        },
        "warnings": [
            "OLD_COHORT_PERMANENTLY_FAILED_NO_BACKFILL",
            "REPLACEMENT_RUNTIME_NOT_IMPLEMENTED",
            "REPLACEMENT_NOT_INSTALLED_OR_STARTED",
            "NO_INTERIM_ECONOMIC_REPORTING",
            "NO_PROFITABILITY_OR_AI_ADVANTAGE_CLAIM",
            "CANARY_NOT_AUTHORIZED",
        ],
    }
    plan["plan_id"] = stable_id("challenger_replacement_plan", _identity(plan))
    plan["plan_hash"] = challenger_replacement_plan_hash(plan)
    if tuple(_validator().iter_errors(plan)):
        raise ChallengerReplacementPlanError(
            "CHALLENGER_REPLACEMENT_PLAN_SCHEMA_INVALID"
        )
    return plan


def challenger_replacement_plan_reasons(
    plan: Mapping[str, Any],
) -> Tuple[str, ...]:
    """Return deterministic fail-closed reason codes for plan semantics."""

    reasons = []
    try:
        if tuple(_validator().iter_errors(plan)):
            reasons.append("CHALLENGER_REPLACEMENT_PLAN_SCHEMA_INVALID")
        if plan.get("plan_hash") != challenger_replacement_plan_hash(plan):
            reasons.append("CHALLENGER_REPLACEMENT_PLAN_HASH_MISMATCH")
        for section_name in (
            "scope",
            "decision_policy",
            "cohort_policy",
            "isolation_policy",
            "evidence_policy",
        ):
            section = dict(plan[section_name])
            claimed = section.pop("policy_hash")
            if claimed != business_hash(section):
                reasons.append(
                    "CHALLENGER_REPLACEMENT_PLAN_POLICY_HASH_MISMATCH"
                )
        if business_hash(plan) != business_hash(build_challenger_replacement_plan()):
            reasons.append("CHALLENGER_REPLACEMENT_PLAN_SEMANTIC_MISMATCH")
    except (KeyError, TypeError, ValueError, ChallengerReplacementPlanError):
        reasons.append("CHALLENGER_REPLACEMENT_PLAN_SEMANTIC_INVALID")
    return tuple(sorted(set(reasons)))


def _copy_plan(plan: Mapping[str, Any]) -> Dict[str, Any]:
    return copy.deepcopy(dict(plan))


def _strict_json_bytes(body: bytes) -> Mapping[str, Any]:
    if not isinstance(body, bytes) or not body or len(body) > _MAX_PLAN_BYTES:
        raise ChallengerReplacementPlanError(
            "CHALLENGER_REPLACEMENT_PLAN_JSON_INVALID"
        )

    def pairs(items):
        result = {}
        for key, value in items:
            if not isinstance(key, str) or not key.isascii():
                raise ChallengerReplacementPlanError(
                    "CHALLENGER_REPLACEMENT_PLAN_JSON_INVALID"
                )
            if key in result:
                raise ChallengerReplacementPlanError(
                    "CHALLENGER_REPLACEMENT_PLAN_JSON_DUPLICATE_KEY"
                )
            result[key] = value
        return result

    def reject_number(_value):
        raise ChallengerReplacementPlanError(
            "CHALLENGER_REPLACEMENT_PLAN_JSON_FLOAT_FORBIDDEN"
        )

    def parse_integer(value):
        parsed = int(value)
        if abs(parsed) > _MAX_SAFE_INTEGER:
            raise ChallengerReplacementPlanError(
                "CHALLENGER_REPLACEMENT_PLAN_JSON_INVALID"
            )
        return parsed

    try:
        value = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_int=parse_integer,
            parse_float=reject_number,
            parse_constant=reject_number,
        )
    except ChallengerReplacementPlanError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ChallengerReplacementPlanError(
            "CHALLENGER_REPLACEMENT_PLAN_JSON_INVALID"
        ) from error
    if not isinstance(value, Mapping):
        raise ChallengerReplacementPlanError(
            "CHALLENGER_REPLACEMENT_PLAN_JSON_INVALID"
        )
    return value


def _read_owner_controlled_regular_file(path: Path) -> bytes:
    try:
        before = path.lstat()
    except (OSError, ValueError) as error:
        raise ChallengerReplacementPlanError(
            "CHALLENGER_REPLACEMENT_PLAN_PATH_INVALID"
        ) from error
    mode = stat.S_IMODE(before.st_mode)
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_uid != os.getuid()
        or before.st_nlink != 1
        or mode & 0o022
        or before.st_size <= 0
        or before.st_size > _MAX_PLAN_BYTES
    ):
        raise ChallengerReplacementPlanError(
            "CHALLENGER_REPLACEMENT_PLAN_PATH_INVALID"
        )
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ChallengerReplacementPlanError(
            "CHALLENGER_REPLACEMENT_PLAN_PATH_INVALID"
        ) from error
    try:
        opened = os.fstat(descriptor)
        if (
            (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.getuid()
            or opened.st_nlink != 1
            or stat.S_IMODE(opened.st_mode) & 0o022
            or opened.st_size != before.st_size
        ):
            raise ChallengerReplacementPlanError(
                "CHALLENGER_REPLACEMENT_PLAN_PATH_INVALID"
            )
        chunks = []
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                raise ChallengerReplacementPlanError(
                    "CHALLENGER_REPLACEMENT_PLAN_PATH_INVALID"
                )
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        if (
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            != (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
                opened.st_mtime_ns,
            )
            or after.st_ctime_ns != opened.st_ctime_ns
            or not stat.S_ISREG(after.st_mode)
            or after.st_uid != os.getuid()
            or after.st_nlink != 1
            or stat.S_IMODE(after.st_mode) & 0o022
        ):
            raise ChallengerReplacementPlanError(
                "CHALLENGER_REPLACEMENT_PLAN_PATH_INVALID"
            )
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def load_challenger_replacement_plan(path: Path) -> Dict[str, Any]:
    """Load only owner-controlled canonical bytes for the one frozen plan."""

    plan_path = Path(path)
    if not plan_path.is_absolute():
        raise ChallengerReplacementPlanError(
            "CHALLENGER_REPLACEMENT_PLAN_PATH_INVALID"
        )
    body = _read_owner_controlled_regular_file(plan_path)
    plan = dict(_strict_json_bytes(body))
    try:
        canonical = canonical_json(plan).encode("utf-8")
    except (CanonicalizationError, RecursionError) as error:
        raise ChallengerReplacementPlanError(
            "CHALLENGER_REPLACEMENT_PLAN_JSON_INVALID"
        ) from error
    if body not in (canonical, canonical + b"\n"):
        raise ChallengerReplacementPlanError(
            "CHALLENGER_REPLACEMENT_PLAN_CANONICAL_BYTES_REQUIRED"
        )
    reasons = challenger_replacement_plan_reasons(plan)
    if reasons:
        raise ChallengerReplacementPlanError(reasons[0])
    return _copy_plan(plan)
