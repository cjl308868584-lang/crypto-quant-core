"""One-shot CLI for current public USD-M perpetual context."""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from .perpetual_context import (
    PerpetualContextError,
    publish_perpetual_context,
)
from .runtime_health import RuntimeHealthError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="perpetual-context-capture")
    parser.add_argument("--output-root", required=True)
    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    server_time_transport=None,
    futures_transport=None,
) -> int:
    parser = _parser()
    try:
        arguments = parser.parse_args(argv)
        result = publish_perpetual_context(
            output_root=Path(arguments.output_root),
            server_time_transport=server_time_transport,
            futures_transport=futures_transport,
        )
    except SystemExit as error:
        return int(error.code)
    except (
        OSError,
        PerpetualContextError,
        RuntimeHealthError,
        TypeError,
        ValueError,
    ) as error:
        print(
            json.dumps(
                {"error": str(error)},
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
