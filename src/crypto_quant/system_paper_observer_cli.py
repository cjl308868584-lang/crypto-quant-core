"""Read-only CLI for observing the first natural System Paper slot."""

import argparse
import json
import sys
from pathlib import Path

from .system_paper_observer import observe_system_paper_first_slot


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract-path", type=Path, required=True)
    parser.add_argument("--plist-path", type=Path, required=True)
    parser.add_argument("--preflight-receipt-path", type=Path, required=True)
    parser.add_argument("--install-receipt-path", type=Path, required=True)
    args = parser.parse_args(argv)
    result = observe_system_paper_first_slot(
        contract_path=args.contract_path,
        plist_path=args.plist_path,
        preflight_receipt_path=args.preflight_receipt_path,
        install_receipt_path=args.install_receipt_path,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
