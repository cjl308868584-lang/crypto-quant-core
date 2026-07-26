"""Validate release artifacts and prove that the baseline fails closed."""

from pathlib import Path

from crypto_quant.release import PolicyBundle


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    bundle = PolicyBundle.load(root / "config")
    readiness = bundle.readiness()
    gate_count = sum(len(gates) for gates in bundle.flat_gate_groups().values())
    print(
        f"policy={readiness.policy_id}@{readiness.policy_version} "
        f"gates={gate_count} result={readiness.result} hash={readiness.result_hash}"
    )
    for reason in readiness.reason_codes:
        print(f"reason={reason}")
    if readiness.result != "FAIL":
        raise SystemExit("design baseline unexpectedly allowed production PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
