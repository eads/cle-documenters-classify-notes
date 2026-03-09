from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")

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

    fetch = subparsers.add_parser(
        "fetch",
        help="Fetch all Google Docs from a Drive folder and write a manifest JSON.",
    )
    fetch.add_argument(
        "--folder",
        default=os.environ.get("ROOT_DRIVE_FOLDER"),
        required=not os.environ.get("ROOT_DRIVE_FOLDER"),
        help="Google Drive folder ID to fetch docs from (defaults to ROOT_DRIVE_FOLDER env var).",
    )
    fetch.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output path for the manifest JSON file.",
    )
    fetch.add_argument(
        "--year",
        type=int,
        default=None,
        help="Only fetch docs from this year folder (e.g. 2026).",
    )
    fetch.add_argument(
        "--month",
        default=None,
        help="Only fetch docs from this month folder (e.g. March). Requires --year.",
    )
    fetch.add_argument(
        "--api-key",
        default=None,
        help="Google API key (sufficient for publicly shared folders). Overrides env vars.",
    )
    fetch.add_argument(
        "--credentials",
        type=Path,
        default=None,
        help="Path to service account JSON key (for private/org-restricted content).",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    app = AgentScaffoldApp()

    if args.command == "classify":
        run = app.classify(manifest=args.manifest, cutoff_days=args.cutoff_days)
        print(f"classify manifest={run.manifest} cutoff_days={run.cutoff_days}")
        print(
            "summary "
            f"total={run.total_docs} "
            f"parseable={run.parseable_docs} "
            f"needs_review={run.needs_review_docs}"
        )
        if run.llm_handoff_docs:
            print(f"llm_handoff doc_ids={','.join(run.llm_handoff_docs)}")
        print(run.note)
        return 0

    if args.command == "extract":
        run = app.extract(input_file=args.input)
        print(f"extract input={run.input_file}")
        print(run.note)
        return 0

    if args.command == "fetch":
        from .gdrive import GoogleDocsClient

        if args.api_key:
            client = GoogleDocsClient(api_key=args.api_key)
        elif args.credentials:
            client = GoogleDocsClient(credentials_file=args.credentials)
        else:
            client = GoogleDocsClient.from_env()
        print(f"fetch folder={args.folder} year={args.year} month={args.month}")
        docs, failures = client.fetch_folder(args.folder, year=args.year, month=args.month)

        manifest = [
            {
                "doc_id": doc.gdoc_id,
                "gdoc_id": doc.gdoc_id,
                "name": doc.name,
                "web_url": doc.web_url,
                "folder_path": doc.folder_path,
                "modified_time": doc.modified_time,
                "text": doc.text,
                "text_checksum": doc.text_checksum,
            }
            for doc in docs
        ]
        args.out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        print(f"fetched={len(docs)} failed={len(failures)} out={args.out}")
        for meta, err in failures:
            print(f"  FAILED {meta.name} ({meta.gdoc_id}): {err}", file=sys.stderr)
        return 0 if not failures else 1

    parser.error(f"Unknown command: {args.command}")
    return 2
