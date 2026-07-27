"""One-shot local CLI for a Paper/account-cost binding."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from .market_data_cli import _publish_immutable
from .paper_cost_binding import (
    PaperCostBindingError,
    build_paper_account_cost_binding,
    paper_account_cost_binding_reasons,
    paper_account_cost_binding_trust_hash,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paper-account-cost-binding")
    parser.add_argument("--paper-run", required=True)
    parser.add_argument("--paper-trust-hash-file", required=True)
    parser.add_argument("--account-snapshot", required=True)
    parser.add_argument("--account-trust-hash-file", required=True)
    parser.add_argument("--output-root", required=True)
    return parser


def _json(path: str):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise PaperCostBindingError(
                    "PAPER_COST_JSON_DUPLICATE_KEY"
                )
            result[key] = value
        return result

    def reject_number(_value):
        raise PaperCostBindingError("PAPER_COST_JSON_FLOAT_FORBIDDEN")

    return json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=pairs,
        parse_float=reject_number,
        parse_constant=reject_number,
    )


def _trust(path: str) -> str:
    value = Path(path).read_text(encoding="ascii")
    if value.endswith("\n"):
        value = value[:-1]
    return value


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    clock=None,
) -> int:
    parser = _parser()
    try:
        arguments = parser.parse_args(argv)
        now = (clock or (lambda: datetime.now(timezone.utc)))()
        if (
            not isinstance(now, datetime)
            or now.tzinfo is None
            or now.utcoffset() is None
        ):
            raise PaperCostBindingError("PAPER_COST_TIME_INVALID")
        created_at = (
            now.astimezone(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
        binding = build_paper_account_cost_binding(
            offline_paper_run=_json(arguments.paper_run),
            offline_paper_trusted_attestation_hash=_trust(
                arguments.paper_trust_hash_file
            ),
            account_commission_snapshot=_json(
                arguments.account_snapshot
            ),
            account_commission_trusted_attestation_hash=_trust(
                arguments.account_trust_hash_file
            ),
            created_at=created_at,
        )
        trust_hash = paper_account_cost_binding_trust_hash(binding)
        if paper_account_cost_binding_reasons(
            binding,
            trust_hash,
            offline_paper_trusted_attestation_hash=(
                binding["source_attestations"][
                    "offline_paper_trusted_attestation_hash"
                ]
            ),
            account_commission_trusted_attestation_hash=(
                binding["source_attestations"][
                    "account_commission_trusted_attestation_hash"
                ]
            ),
        ):
            raise PaperCostBindingError("PAPER_COST_BINDING_INVALID")
        artifact_name = binding["binding_id"].lower() + ".json"
        artifact_bytes = json.dumps(
            binding, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        created = _publish_immutable(
            Path(arguments.output_root),
            artifact_name,
            artifact_bytes,
            output_directory="paper-cost",
        )
        path = (
            Path(arguments.output_root).resolve()
            / "paper-cost"
            / artifact_name
        )
        os.chmod(path, 0o600)
        summary = {
            "outcome": "BOUND",
            "artifact_path": str(path),
            "artifact_created": created,
            "binding_id": binding["binding_id"],
            "binding_hash": binding["binding_hash"],
            "trust_hash": trust_hash,
            "paper_eligibility": binding["paper_eligibility"],
            "production_eligibility": binding[
                "production_eligibility"
            ],
        }
    except SystemExit as error:
        return int(error.code)
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        PaperCostBindingError,
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
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
