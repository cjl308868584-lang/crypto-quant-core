"""No-argument CLI for the post-release replacement install renderer."""

import argparse
from typing import Optional, Sequence

from .canonical import canonical_json
from .challenger_replacement_install_trust import (
    render_fixed_replacement_snapshot_and_contract,
)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="crypto_quant.challenger_replacement_install_trust_cli"
    )
    parser.parse_args(argv)
    result = render_fixed_replacement_snapshot_and_contract()
    print(canonical_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
