"""Verify the frozen evaluator inputs and estimator golden vectors."""

from pathlib import Path

from crypto_quant.release import PolicyBundle


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    bundle = PolicyBundle.load(root / "config")
    report = bundle.estimators.run_golden_vectors()
    build = bundle.evaluator_build
    covered = (
        build.executable_estimator_count
        + build.unavailable_estimator_count
    )

    if not report.passed:
        raise SystemExit(
            f"estimator golden vectors failed: {report.failed_vector_ids}"
        )
    if covered != len(bundle.catalog["algorithms"]):
        raise SystemExit("estimator registry does not cover the Metric Catalog")

    print(
        f"evaluator_build={build.manifest_id}@{build.manifest_version} "
        f"hash={build.build_hash}"
    )
    print(
        f"estimators=executable:{build.executable_estimator_count},"
        f"unavailable:{build.unavailable_estimator_count} "
        f"golden_vectors={report.vector_count} "
        f"golden_report={report.report_hash}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
