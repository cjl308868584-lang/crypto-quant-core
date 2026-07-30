"""Prepare a private, non-installed maintenance execution snapshot."""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from .challenger_cohort_evidence_maintenance_deployment import (
    ChallengerCohortEvidenceMaintenanceDeploymentError,
    prepare_challenger_cohort_evidence_maintenance_deployment,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="challenger-cohort-evidence-maintenance-deployment"
    )
    parser.add_argument("--source-contract-path", required=True)
    parser.add_argument("--source-plist-path", required=True)
    parser.add_argument(
        "--trusted-source-attestation-hash", required=True
    )
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
        result = prepare_challenger_cohort_evidence_maintenance_deployment(
            source_contract_path=Path(arguments.source_contract_path),
            source_plist_path=Path(arguments.source_plist_path),
            trusted_source_attestation_hash=(
                arguments.trusted_source_attestation_hash
            ),
            output_root=Path(arguments.output_root),
            clock=clock,
            _strategy_loader=strategy_loader,
        )
    except SystemExit as error:
        return int(error.code)
    except (
        ChallengerCohortEvidenceMaintenanceDeploymentError,
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
