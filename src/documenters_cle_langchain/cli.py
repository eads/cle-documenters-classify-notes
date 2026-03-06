from __future__ import annotations

import argparse
from pathlib import Path

from .app import AgentScaffoldApp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="documenters-cle-langchain",
        description="Scaffold CLI for document classification and extraction flows.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    classify = subparsers.add_parser(
        "classify",
        help="Classify docs into A/B buckets (recent vs old in v1).",
    )
    classify.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="Path to a local JSON/CSV manifest of docs to process.",
    )
    classify.add_argument(
        "--cutoff-days",
        type=int,
        default=365,
        help="Age threshold in days for recent vs old split.",
    )

    extract = subparsers.add_parser(
        "extract",
        help="Run extraction workflow on B documents.",
    )
    extract.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to local input list for B documents.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    app = AgentScaffoldApp()

    if args.command == "classify":
        run = app.classify(manifest=args.manifest, cutoff_days=args.cutoff_days)
        print(f"classify manifest={run.manifest} cutoff_days={run.cutoff_days}")
        print(run.note)
        return 0

    if args.command == "extract":
        run = app.extract(input_file=args.input)
        print(f"extract input={run.input_file}")
        print(run.note)
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2
