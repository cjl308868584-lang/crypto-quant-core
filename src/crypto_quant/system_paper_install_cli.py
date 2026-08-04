"""CLI for preflight-gated System Paper LaunchAgent installation."""

import argparse
import json
import sys
from pathlib import Path

from .system_paper_install import install_system_paper_launchd


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract-path", type=Path, required=True)
    parser.add_argument("--plist-path", type=Path, required=True)
    parser.add_argument("--preflight-receipt-path", type=Path, required=True)
    args = parser.parse_args(argv)
    result = install_system_paper_launchd(
        contract_path=args.contract_path,
        plist_path=args.plist_path,
        preflight_receipt_path=args.preflight_receipt_path,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
