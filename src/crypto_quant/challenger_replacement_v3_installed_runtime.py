"""Fixed installed adapter for one natural replacement v3 opportunity."""

from contextlib import contextmanager

from .challenger_replacement_economic_plan import (
    build_challenger_replacement_economic_plan,
)
from .challenger_replacement_plan_v3 import build_challenger_replacement_plan_v3
from .challenger_replacement_public_simulation_contract import (
    build_challenger_replacement_public_simulation_contract,
)
from .challenger_replacement_simulation_contract import (
    build_challenger_replacement_simulation_contract,
)
from .challenger_replacement_v3_runtime import (
    run_challenger_replacement_v3_opportunity,
)


_SOURCE_KEYS = frozenset({
    "state", "event_root", "plan", "economic_plan",
    "predecessor_contract", "public_contract", "build_identity",
})


class ReplacementV3InstalledRuntimeError(ValueError):
    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code


@contextmanager
def _open_fixed_sources():
    """Open only a receipt-bound installation; Task 3 supplies the strict loader."""

    try:
        from .challenger_replacement_v3_activation_install import (
            open_fixed_v3_installed_sources,
        )
    except ImportError as error:
        raise ReplacementV3InstalledRuntimeError(
            "CHALLENGER_REPLACEMENT_V3_INSTALL_RECEIPT_REQUIRED"
        ) from error
    with open_fixed_v3_installed_sources() as installed:
        plan = build_challenger_replacement_plan_v3()
        economic = build_challenger_replacement_economic_plan()
        predecessor = build_challenger_replacement_simulation_contract(plan=plan)
        public = build_challenger_replacement_public_simulation_contract(
            plan=plan, economic_plan=economic, predecessor_contract=predecessor,
        )
        sources = {
            "state": installed["state"],
            "event_root": installed["event_root"],
            "plan": plan,
            "economic_plan": economic,
            "predecessor_contract": predecessor,
            "public_contract": public,
            "build_identity": installed["build_identity"],
        }
        if set(sources) != _SOURCE_KEYS:
            raise ReplacementV3InstalledRuntimeError(
                "CHALLENGER_REPLACEMENT_V3_INSTALL_CONTRACT_INVALID"
            )
        yield sources


def run_installed_v3_opportunity():
    """Run one opportunity using only fixed receipt-bound sources."""

    with _open_fixed_sources() as sources:
        if not isinstance(sources, dict) or set(sources) != _SOURCE_KEYS:
            raise ReplacementV3InstalledRuntimeError(
                "CHALLENGER_REPLACEMENT_V3_INSTALL_CONTRACT_INVALID"
            )
        return run_challenger_replacement_v3_opportunity(**sources)


def main(argv=None):
    import sys
    from .canonical import canonical_json
    if tuple(sys.argv[1:] if argv is None else argv):
        return 2
    try:
        value = run_installed_v3_opportunity()
    except (ReplacementV3InstalledRuntimeError, OSError, ValueError) as error:
        sys.stderr.write(getattr(error, "reason_code", "CHALLENGER_REPLACEMENT_V3_RUNTIME_FAILED") + "\n")
        return 1
    sys.stdout.write(canonical_json(value) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
