"""Command-line entry point for the frozen archive research corpus."""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from .research_corpus import (
    ResearchCorpusError,
    build_default_research_corpus_plan,
    load_research_corpus_plan,
    load_research_corpus_snapshot,
    publish_research_corpus_plan,
    run_historical_research_corpus,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crypto-quant-research-corpus",
        description=(
            "Plan or resume the fixed public, archive-only research corpus. "
            "No credentials, proxy, URL override, Broker, or order surface exists."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    plan = commands.add_parser("plan", help="publish the frozen 42-month plan")
    plan.add_argument("--output", required=True, type=Path)

    run = commands.add_parser("run", help="resume bounded public acquisition")
    run.add_argument("--state", required=True, type=Path)
    run.add_argument("--output-root", required=True, type=Path)
    run.add_argument("--worker-id", required=True)
    run.add_argument("--max-items", type=int, default=1)

    verify_plan = commands.add_parser(
        "verify-plan",
        help="verify canonical plan bytes and full frozen semantics",
    )
    verify_plan.add_argument("--input", required=True, type=Path)

    verify_snapshot = commands.add_parser(
        "verify-snapshot",
        help="verify a corpus coverage snapshot against the frozen plan",
    )
    verify_snapshot.add_argument("--input", required=True, type=Path)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "plan":
            plan = build_default_research_corpus_plan()
            publish_research_corpus_plan(plan, arguments.output)
            print(
                json.dumps(
                    {
                        "status": "PLAN_PUBLISHED",
                        "output": str(arguments.output.expanduser().resolve()),
                        "plan_hash": plan["plan_hash"],
                        "item_count": plan["summary"]["item_count"],
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            return 0
        if arguments.command == "verify-plan":
            plan = load_research_corpus_plan(arguments.input)
            print(
                json.dumps(
                    {
                        "status": "PLAN_VERIFIED",
                        "plan_hash": plan["plan_hash"],
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            return 0
        if arguments.command == "verify-snapshot":
            plan = build_default_research_corpus_plan()
            snapshot = load_research_corpus_snapshot(
                arguments.input,
                plan=plan,
            )
            print(
                json.dumps(
                    {
                        "status": "SNAPSHOT_VERIFIED",
                        "snapshot_hash": snapshot["snapshot_hash"],
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            return 0
        plan = build_default_research_corpus_plan()
        snapshot = run_historical_research_corpus(
            plan=plan,
            state_path=arguments.state,
            output_root=arguments.output_root,
            worker_id=arguments.worker_id,
            max_items=arguments.max_items,
        )
        print(
            json.dumps(
                {
                    "status": "RUN_COMPLETED",
                    "snapshot_id": snapshot["snapshot_id"],
                    "snapshot_hash": snapshot["snapshot_hash"],
                    "summary": snapshot["summary"],
                    "research_training_readiness": snapshot[
                        "research_training_readiness"
                    ],
                    "formal_pit_eligibility": snapshot[
                        "formal_pit_eligibility"
                    ],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    except ResearchCorpusError as error:
        print(error.reason_code, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
