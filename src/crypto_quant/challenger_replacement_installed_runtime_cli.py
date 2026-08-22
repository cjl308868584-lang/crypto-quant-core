"""Zero-argument entry point for the fixed installed replacement runtime."""

import sys

from .canonical import canonical_json
from .challenger_replacement_installed_runtime import (
    ReplacementInstalledRuntimeError,
    run_fixed_replacement_installed_invocation,
)
from .challenger_replacement_live_input import ChallengerReplacementLiveInputError
from .challenger_replacement_runtime import ChallengerReplacementRuntimeError


def main(argv=None):
    if tuple(sys.argv[1:] if argv is None else argv):
        sys.stderr.write("CHALLENGER_REPLACEMENT_INSTALLED_RUNTIME_ARGUMENTS_FORBIDDEN\n")
        return 2
    try:
        result = run_fixed_replacement_installed_invocation()
    except (ReplacementInstalledRuntimeError, ChallengerReplacementLiveInputError,
            ChallengerReplacementRuntimeError) as error:
        sys.stderr.write(error.reason_code + "\n")
        return 1
    sys.stdout.write(canonical_json(result) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
