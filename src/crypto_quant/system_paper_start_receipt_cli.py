"""CLI for immutable System Paper start receipt publication."""

import argparse
import json
import sys
from pathlib import Path

from .system_paper_start_receipt import publish_system_paper_start_receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract-path", type=Path, required=True)
    parser.add_argument("--plist-path", type=Path, required=True)
    parser.add_argument("--preflight-receipt-path", type=Path, required=True)
    parser.add_argument("--install-receipt-path", type=Path, required=True)
    args = parser.parse_args(argv)
    result = publish_system_paper_start_receipt(
        contract_path=args.contract_path,
        plist_path=args.plist_path,
        preflight_receipt_path=args.preflight_receipt_path,
        install_receipt_path=args.install_receipt_path,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
