"""Fixed-source, read-only v0.76 economic evaluator entry point."""

import sys

from .canonical import canonical_json
from .challenger_replacement_economic_evaluation import ChallengerReplacementEconomicEvaluationError


def _load_fixed_evaluation_result():
    from .challenger_replacement_v3_observer import (
        _evaluate_fixed_economic_result,
    )
    return _evaluate_fixed_economic_result()


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--help"]:
        print("usage: challenger-replacement-economic-evaluation")
        return 0
    if args:
        print("ECONOMIC_EVALUATION_ARGUMENTS_FORBIDDEN", file=sys.stderr)
        return 2
    try:
        result = _load_fixed_evaluation_result()
        if not isinstance(result, dict):
            raise ChallengerReplacementEconomicEvaluationError(
                "ECONOMIC_EVALUATION_FIXED_SOURCES_INVALID"
            )
    except OSError:
        print("ECONOMIC_EVALUATION_NOT_ACTIVATED", file=sys.stderr)
        return 3
    except ChallengerReplacementEconomicEvaluationError as error:
        print(error.reason_code, file=sys.stderr)
        return 1
    print(canonical_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
