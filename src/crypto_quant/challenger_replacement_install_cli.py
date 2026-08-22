import argparse
from typing import Optional, Sequence
from .canonical import canonical_json
from .challenger_replacement_install import install_fixed_replacement_launch_agent
def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="crypto_quant.challenger_replacement_install_cli")
    parser.parse_args(argv)
    print(canonical_json(install_fixed_replacement_launch_agent()))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
