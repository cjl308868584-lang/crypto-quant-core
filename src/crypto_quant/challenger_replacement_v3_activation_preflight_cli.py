"""Publish the fixed v3 activation preflight receipt."""

import sys

from .canonical import canonical_json
from .challenger_replacement_v3_activation_preflight import (
    ChallengerReplacementV3ActivationPreflightError,
    publish_fixed_v3_activation_preflight,
)


def main(argv=None):
    if tuple(sys.argv[1:] if argv is None else argv):
        return 2
    try:
        result = publish_fixed_v3_activation_preflight()
    except (ChallengerReplacementV3ActivationPreflightError, OSError, ValueError) as error:
        sys.stderr.write(getattr(error, "reason_code", "CHALLENGER_REPLACEMENT_V3_PREFLIGHT_FAILED") + "\n")
        return 1
    sys.stdout.write(canonical_json(result) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
