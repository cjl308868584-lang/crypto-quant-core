"""Render, but never install, the cohort evidence maintenance LaunchAgent."""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from .challenger_cohort_evidence_maintenance_launchd import (
    ChallengerCohortEvidenceMaintenanceLaunchdError,
    publish_challenger_cohort_evidence_maintenance_launchd_contract,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="challenger-cohort-evidence-maintenance-launchd-render"
    )
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--python-executable", required=True)
    parser.add_argument("--install-receipt-path", required=True)
    parser.add_argument("--contract-path", required=True)
    parser.add_argument("--plist-path", required=True)
    parser.add_argument("--output-root", required=True)
    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    clock=None,
    strategy_loader=None,
) -> int:
    parser = _parser()
    try:
        arguments = parser.parse_args(argv)
        result = (
            publish_challenger_cohort_evidence_maintenance_launchd_contract(
                output_root=Path(arguments.output_root),
                repository_root=Path(arguments.repository_root),
                runtime_root=Path(arguments.runtime_root),
                python_executable=Path(arguments.python_executable),
                install_receipt_path=Path(
                    arguments.install_receipt_path
                ),
                contract_path=Path(arguments.contract_path),
                plist_path=Path(arguments.plist_path),
                clock=clock,
                _strategy_loader=strategy_loader,
            )
        )
    except SystemExit as error:
        return int(error.code)
    except (
        ChallengerCohortEvidenceMaintenanceLaunchdError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        print(
            json.dumps(
                {"error": str(error)},
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
