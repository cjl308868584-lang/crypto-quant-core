"""Install the fixed cohort evidence maintenance LaunchAgent."""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from .challenger_cohort_evidence_maintenance_install import (
    ChallengerCohortEvidenceMaintenanceInstallError,
    install_challenger_cohort_evidence_maintenance_launchd,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="challenger-cohort-evidence-maintenance-install"
    )
    parser.add_argument("--deployment-manifest-path", required=True)
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
) -> int:
    parser = _parser()
    try:
        arguments = parser.parse_args(argv)
        result = (
            install_challenger_cohort_evidence_maintenance_launchd(
                manifest_path=Path(
                    arguments.deployment_manifest_path
                ),
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
            )
        )
    except SystemExit as error:
        return int(error.code)
    except (
        ChallengerCohortEvidenceMaintenanceInstallError,
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
