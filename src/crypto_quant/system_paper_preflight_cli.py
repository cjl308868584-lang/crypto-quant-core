"""CLI for the fixed System Paper machine preflight."""

import argparse
import json
import sys
from pathlib import Path

from .system_paper_preflight import run_system_paper_preflight


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract-path", type=Path, required=True)
    parser.add_argument("--plist-path", type=Path, required=True)
    args = parser.parse_args(argv)
    result = run_system_paper_preflight(
        contract_path=args.contract_path,
        plist_path=args.plist_path,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
