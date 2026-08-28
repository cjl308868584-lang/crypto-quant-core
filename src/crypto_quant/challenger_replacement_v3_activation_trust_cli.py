"""Print the credential-free v3 activation candidate."""

import sys

from .canonical import canonical_json
from .challenger_replacement_v3_activation_trust import (
    ChallengerReplacementV3ActivationTrustError,
    render_fixed_v3_activation_candidate,
)


def main(argv=None):
    if tuple(sys.argv[1:] if argv is None else argv):
        return 2
    try:
        value = render_fixed_v3_activation_candidate()
    except ChallengerReplacementV3ActivationTrustError as error:
        sys.stderr.write(error.reason_code + "\n")
        return 1
    sys.stdout.write(canonical_json(value) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
