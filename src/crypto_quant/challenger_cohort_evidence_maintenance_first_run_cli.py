"""CLI for the read-only first natural maintenance run observer."""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from .challenger_cohort_evidence_maintenance_first_run import (
    ChallengerCohortEvidenceMaintenanceFirstRunError,
    observe_challenger_cohort_evidence_maintenance_first_run,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="challenger-cohort-maintenance-first-run-observe"
    )
    parser.add_argument("--install-receipt-path", required=True)
    parser.add_argument("--manifest-path", required=True)
    parser.add_argument(
        "--trusted-source-attestation-hash", required=True
    )
    parser.add_argument(
        "--trusted-candidate-attestation-hash", required=True
    )
    parser.add_argument("--receipt-output-root", required=True)
    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    clock=None,
    launchctl_runner=None,
) -> int:
    try:
        arguments = _parser().parse_args(argv)
        result = (
            observe_challenger_cohort_evidence_maintenance_first_run(
                install_receipt_path=Path(
                    arguments.install_receipt_path
                ),
                manifest_path=Path(arguments.manifest_path),
                trusted_source_attestation_hash=(
                    arguments.trusted_source_attestation_hash
                ),
                trusted_candidate_attestation_hash=(
                    arguments.trusted_candidate_attestation_hash
                ),
                receipt_output_root=Path(
                    arguments.receipt_output_root
                ),
                clock=clock,
                _launchctl_runner=launchctl_runner,
            )
        )
    except SystemExit as error:
        return int(error.code)
    except (
        ChallengerCohortEvidenceMaintenanceFirstRunError,
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
