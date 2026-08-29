"""Refresh deterministic hashes without changing frozen release versions."""

import json
import os
import tempfile
from pathlib import Path

from crypto_quant.build import EvaluatorBuild
from crypto_quant.canonical import business_hash
from crypto_quant.evidence import artifact_self_hash


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "config" / "evaluator-build-manifest-v1.json"
EXPECTED_MANIFEST_VERSION = "1.76.0"
EXPECTED_PACKAGE_VERSION = "0.78.4"


def main() -> int:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest.get("manifest_version") != EXPECTED_MANIFEST_VERSION:
        raise SystemExit("refusing to change frozen manifest version")
    if manifest.get("package_version") != EXPECTED_PACKAGE_VERSION:
        raise SystemExit("refusing to change frozen package version")
    paths = EvaluatorBuild.expected_file_paths(ROOT)
    hashes = EvaluatorBuild.file_hashes(ROOT, paths)
    manifest["file_hashes"] = hashes
    manifest["build_input_tree_hash"] = business_hash(hashes)
    manifest["manifest_hash"] = "0" * 64
    manifest["manifest_hash"] = artifact_self_hash(
        manifest, "manifest_hash"
    )
    body = (
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=False,
        )
        + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".evaluator-build-manifest-",
        suffix=".json",
        dir=str(MANIFEST_PATH.parent),
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, MANIFEST_PATH)
        directory_descriptor = os.open(
            str(MANIFEST_PATH.parent), os.O_RDONLY
        )
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if temporary.exists():
            temporary.unlink()
    print(
        json.dumps(
            {
                "build_input_count": len(hashes),
                "build_input_tree_hash": manifest[
                    "build_input_tree_hash"
                ],
                "manifest_hash": manifest["manifest_hash"],
                "manifest_version": manifest["manifest_version"],
                "package_version": manifest["package_version"],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
