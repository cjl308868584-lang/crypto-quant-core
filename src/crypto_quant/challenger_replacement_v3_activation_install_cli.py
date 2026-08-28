"""Execute the fixed v3 bootstrap-only installation ceremony."""

import sys

from .canonical import canonical_json
from .challenger_replacement_v3_activation_install import (
    ChallengerReplacementV3ActivationInstallError,
    install_fixed_v3_simulation_launch_agent,
)


def main(argv=None):
    if tuple(sys.argv[1:] if argv is None else argv):
        return 2
    try:
        result = install_fixed_v3_simulation_launch_agent()
    except (ChallengerReplacementV3ActivationInstallError, OSError, ValueError) as error:
        sys.stderr.write(getattr(error, "reason_code", "CHALLENGER_REPLACEMENT_V3_INSTALL_FAILED") + "\n")
        return 1
    sys.stdout.write(canonical_json(result) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
