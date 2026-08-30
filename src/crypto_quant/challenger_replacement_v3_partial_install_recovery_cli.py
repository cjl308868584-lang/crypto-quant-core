"""Publish the fixed v0.78.7 partial-install recovery receipt."""

import sys

from .canonical import canonical_json
from .challenger_replacement_v3_partial_install_recovery import (
    ChallengerReplacementPartialInstallRecoveryError,
    publish_fixed_v3_partial_install_recovery_receipt,
)


def main(argv=None):
    if tuple(sys.argv[1:] if argv is None else argv):
        return 2
    try:
        result = publish_fixed_v3_partial_install_recovery_receipt()
    except ChallengerReplacementPartialInstallRecoveryError as error:
        sys.stderr.write(error.reason_code + "\n")
        return 1
    sys.stdout.write(canonical_json(result) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
