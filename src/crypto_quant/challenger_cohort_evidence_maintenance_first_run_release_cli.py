"""CLI for exact-byte release of the first maintenance run receipt."""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from .challenger_cohort_evidence_maintenance_first_run_release import (
    ChallengerCohortEvidenceMaintenanceFirstRunReleaseError,
    release_challenger_cohort_evidence_maintenance_first_run_receipt,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="challenger-cohort-maintenance-first-run-release"
    )
    parser.add_argument("--runtime-receipt-path", required=True)
    parser.add_argument("--install-receipt-path", required=True)
    parser.add_argument("--manifest-path", required=True)
    parser.add_argument(
        "--trusted-source-attestation-hash", required=True
    )
    parser.add_argument(
        "--trusted-candidate-attestation-hash", required=True
    )
    parser.add_argument("--artifact-output-path", required=True)
    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    receipt_loader=None,
) -> int:
    try:
        arguments = _parser().parse_args(argv)
        result = (
            release_challenger_cohort_evidence_maintenance_first_run_receipt(
                runtime_receipt_path=Path(
                    arguments.runtime_receipt_path
                ),
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
                artifact_output_path=Path(
                    arguments.artifact_output_path
                ),
                _receipt_loader=receipt_loader,
            )
        )
    except SystemExit as error:
        return int(error.code)
    except (
        ChallengerCohortEvidenceMaintenanceFirstRunReleaseError,
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
