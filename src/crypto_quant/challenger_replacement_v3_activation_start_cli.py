"""Observe and publish the fixed first-natural-opportunity receipt."""

import sys
from .canonical import canonical_json
from .challenger_replacement_v3_activation_start import (
    ChallengerReplacementV3ActivationStartError, publish_fixed_v3_start_receipt,
)


def main(argv=None):
    if tuple(sys.argv[1:] if argv is None else argv):
        return 2
    try:
        value = publish_fixed_v3_start_receipt()
    except (ChallengerReplacementV3ActivationStartError, OSError, ValueError) as error:
        sys.stderr.write(getattr(error, "reason_code", "CHALLENGER_REPLACEMENT_V3_START_FAILED") + "\n")
        return 1
    sys.stdout.write(canonical_json(value) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
