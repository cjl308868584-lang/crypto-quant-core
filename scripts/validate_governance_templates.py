"""Validate every Phase 0 governance template and prove it is unapproved."""

from pathlib import Path

from crypto_quant.governance import GovernanceTemplateBundle


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    result = GovernanceTemplateBundle.load(root / "config").result()
    if result.lifecycle_status != "TEMPLATE_UNAPPROVED":
        raise SystemExit("governance templates unexpectedly became approved")
    if result.production_eligible:
        raise SystemExit("governance templates unexpectedly became production eligible")
    print(
        f"governance_templates={result.template_count} "
        f"status={result.lifecycle_status} "
        f"production_eligible={str(result.production_eligible).lower()} "
        f"hash={result.bundle_hash}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
