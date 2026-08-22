import argparse
from typing import Optional, Sequence
from .canonical import canonical_json
from .challenger_replacement_install_preflight import publish_fixed_replacement_install_preflight
def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="crypto_quant.challenger_replacement_install_preflight_cli")
    parser.parse_args(argv)
    print(canonical_json(publish_fixed_replacement_install_preflight()))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
