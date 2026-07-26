"""Validate and identify the production release-artifact schemas."""

from pathlib import Path

from crypto_quant.canonical import business_hash
from crypto_quant.release_artifacts import load_release_artifact_schemas


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    schemas = load_release_artifact_schemas(root / "config")
    rendered = ",".join(
        f"{name}:{business_hash(schema)}"
        for name, schema in sorted(schemas.items())
    )
    print(f"release_artifact_schemas={len(schemas)} hashes={rendered}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
