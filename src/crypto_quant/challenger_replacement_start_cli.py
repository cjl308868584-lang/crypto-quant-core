"""No-argument first-slot observation and start-receipt entry point."""

import sys

from .canonical import canonical_json
from .challenger_replacement_start import (
    ChallengerReplacementStartError,
    publish_fixed_replacement_start_receipt,
)


def main(argv=None):
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    if arguments:
        sys.stderr.write("CHALLENGER_REPLACEMENT_START_ARGUMENTS_FORBIDDEN\n")
        return 2
    try:
        result = publish_fixed_replacement_start_receipt()
    except ChallengerReplacementStartError as error:
        sys.stderr.write(error.reason_code + "\n")
        return 1
    sys.stdout.write(canonical_json(result) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
