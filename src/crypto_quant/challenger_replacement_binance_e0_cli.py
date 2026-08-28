"""Closed command surface for the Binance-only E0 boundary."""

import re
import sys

from .canonical import canonical_json
from .challenger_replacement_binance_e0_orchestration import (
    BinanceE0OrchestrationError,
    run_fixed_binance_account_preflight,
    run_fixed_binance_emergency_stop,
    run_fixed_binance_private_opportunity,
)


_OPPORTUNITY = re.compile(
    r"^ETHUSDT@[0-9]{4}-[0-9]{2}-[0-9]{2}T(?:00|04|08|12|16|20):00:00\.000Z$"
)


def main(argv=None):
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    command = None
    if arguments == ("account-preflight",):
        command = (run_fixed_binance_account_preflight, ())
    elif (len(arguments) == 2 and arguments[0] in {
            "private-runtime", "emergency-stop",
    } and _OPPORTUNITY.fullmatch(arguments[1])):
        selected = (run_fixed_binance_private_opportunity
                    if arguments[0] == "private-runtime"
                    else run_fixed_binance_emergency_stop)
        command = (selected, (arguments[1],))
    if command is None:
        return 2
    try:
        result = command[0](*command[1])
    except (BinanceE0OrchestrationError, OSError, TypeError, ValueError) as error:
        sys.stderr.write(getattr(
            error, "reason_code", "BINANCE_E0_OPERATION_FAILED",
        ) + "\n")
        return 1
    sys.stdout.write(canonical_json(result) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
