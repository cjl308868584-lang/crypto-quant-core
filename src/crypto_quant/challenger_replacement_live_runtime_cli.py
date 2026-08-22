"""Zero-business-argument entry point for the replacement live runtime."""

import sys

from .canonical import canonical_json
from .challenger_replacement_live_input import (
    ChallengerReplacementLiveInputError,
    acquire_challenger_replacement_live_capture,
)
from .challenger_replacement_runtime import ChallengerReplacementRuntimeError
from .challenger_replacement_runtime import (
    ChallengerReplacementRuntimeState,
    resume_challenger_replacement_slot,
    run_challenger_replacement_cohort_slot,
)

_ARGUMENTS_FORBIDDEN = "CHALLENGER_REPLACEMENT_LIVE_RUNTIME_ARGUMENTS_FORBIDDEN"

def _load_fixed_runtime_contract():
    raise ChallengerReplacementRuntimeError(
        "CHALLENGER_REPLACEMENT_RUNTIME_CONTRACT_UNAVAILABLE"
    )

def _run_live_invocation():
    contract = _load_fixed_runtime_contract()
    if (
        not isinstance(contract, dict)
        or set(contract) != {"state", "worker_id"}
        or not isinstance(contract["state"], ChallengerReplacementRuntimeState)
        or not isinstance(contract["worker_id"], str)
        or not contract["worker_id"]
    ):
        raise ChallengerReplacementRuntimeError(
            "CHALLENGER_REPLACEMENT_RUNTIME_CONTRACT_INVALID"
        )
    state = contract["state"]
    projection = state.replay()
    if projection["active_slot_id"] is not None:
        result = resume_challenger_replacement_slot(
            state=state, worker_id=contract["worker_id"]
        )
    else:
        capture = acquire_challenger_replacement_live_capture(state=state)
        result = run_challenger_replacement_cohort_slot(
            state=state,
            live_capture=capture,
            worker_id=contract["worker_id"],
        )
    projection = state.replay()
    slot = result["source_bundle"]["slot"]
    return {
        "event_count": len(projection["events"]),
        "next_required_slot": projection["next_required_slot"],
        "reason_code": "CHALLENGER_REPLACEMENT_SLOT_SUCCEEDED_VERIFIED",
        "scheduled_for": slot["scheduled_for"],
        "slot_id": slot["slot_id"],
        "status": "CHALLENGER_REPLACEMENT_LIVE_RUNTIME_SUCCEEDED",
        "terminal_stage": result["stage"],
    }

def main(argv=None):
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    if arguments:
        sys.stderr.write(_ARGUMENTS_FORBIDDEN + "\n")
        return 2
    try:
        summary = _run_live_invocation()
    except ChallengerReplacementLiveInputError as error:
        sys.stderr.write(error.reason_code + "\n")
        return 75 if error.reason_code in {
            "CHALLENGER_REPLACEMENT_LIVE_INPUT_RETRIES_EXHAUSTED",
            "CHALLENGER_REPLACEMENT_LIVE_INPUT_TRANSPORT_FAILURE",
        } else 1
    except ChallengerReplacementRuntimeError as error:
        sys.stderr.write(error.reason_code + "\n")
        return 1
    sys.stdout.write(canonical_json(summary) + "\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
