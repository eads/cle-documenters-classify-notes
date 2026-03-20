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

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="documenters-cle-langchain",
        description="CLI for document fetch, dedup, extraction, and classification.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    pipeline = subparsers.add_parser(
        "pipeline",
        help="Run the full pipeline: dedup → extract → gate → classify.",
    )
    pipeline.add_argument(
        "--manifest", type=Path, required=True,
        help="Manifest JSON produced by the fetch command.",
    )
    pipeline.add_argument(
        "--out", type=Path, required=True,
        help="Output JSON path for pipeline results.",
    )
    pipeline.add_argument(
        "--model", default="gpt-5-mini",
        help="OpenAI model for the civic infrastructure classifier.",
    )
    pipeline.add_argument(
        "--fallback-model", default="gpt-5.4",
        help="Stronger model used for ambiguous docs (score in [0.3, 0.7]).",
    )
    pipeline.add_argument(
        "--csv-out", type=Path, default=None,
        help="Optional CSV output: web_url, name, date, agency, <topic>_score per row.",
    )
    pipeline.add_argument(
        "--sheets-folder",
        default=os.environ.get("CLASSIFIER_OUTPUT_FOLDER"),
        help="Drive folder ID to create a new output sheet in (defaults to CLASSIFIER_OUTPUT_FOLDER env var).",
    )
    pipeline.add_argument(
        "--year", type=int, default=None,
        help="Year filter applied during fetch — used in the sheet title.",
    )
    pipeline.add_argument(
        "--month", default=None,
        help="Month filter applied during fetch — used in the sheet title.",
    )

    dedup = subparsers.add_parser(
        "dedup",
        help="Deduplicate an existing manifest JSON in place (or to a new file).",
    )
    dedup.add_argument("--input", type=Path, required=True, help="Manifest JSON to deduplicate.")
    dedup.add_argument("--out", type=Path, default=None, help="Output path (defaults to --input, overwrites in place).")
    dedup.add_argument("--review", type=Path, default=None, help="Write a markdown review file listing kept/dropped docs with Drive URLs.")

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

        raw_docs = [
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
        manifest, n_dupes, _ = _dedup_manifest(raw_docs)
        args.out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        print(f"fetched={len(docs)} deduped={n_dupes} kept={len(manifest)} failed={len(failures)} out={args.out}")
        for meta, err in failures:
            print(f"  FAILED {meta.name} ({meta.gdoc_id}): {err}", file=sys.stderr)
        return 0 if not failures else 1

    if args.command == "pipeline":
        from .pipeline import run_pipeline
        from .classifiers import MeetingClassifier
        import dataclasses

        classifier = MeetingClassifier(model=args.model, fallback_model=args.fallback_model)
        result = run_pipeline(manifest_path=args.manifest, classifier=classifier)

        c = result.counts
        print(
            f"pipeline done — "
            f"dedup_removed={c.dedup_decisions} "
            f"total={c.total_after_dedup} "
            f"passed={c.passed_gate} "
            f"skipped={c.skipped} "
            f"any_topic_match={c.any_topic_match}"
        )
        if result.skipped:
            print("skipped docs:")
            for s in result.skipped:
                print(f"  {s.name} missing={s.missing_fields}")

        output = {
            "counts": dataclasses.asdict(result.counts),
            "results": [dataclasses.asdict(r) for r in result.results],
            "skipped": [dataclasses.asdict(s) for s in result.skipped],
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"results written to {args.out}")
        if args.csv_out:
            _write_csv(result.results, args.csv_out)
            print(f"CSV written to {args.csv_out}")
        if args.sheets_folder:
            from .gsheets import upload_results
            title = _sheet_title(args.year, args.month)
            url = upload_results(result.results, folder_id=args.sheets_folder, title=title)
            print(f"sheet created: {url}")
        return 0

    if args.command == "dedup":
        raw = json.loads(args.input.read_text(encoding="utf-8"))
        manifest, n_dupes, decisions = _dedup_manifest(raw)
        out = args.out or args.input
        out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"dedup input={args.input} removed={n_dupes} kept={len(manifest)} out={out}")
        if args.review:
            args.review.parent.mkdir(parents=True, exist_ok=True)
            args.review.write_text(_render_review(decisions), encoding="utf-8")
            if decisions:
                print(f"review written to {args.review}")
            else:
                print(f"no duplicates found — empty review written to {args.review}")
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


def _sheet_title(year: int | None, month: str | None) -> str:
    from datetime import datetime
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    if year and month:
        return f"Classifier Output — {ts} ({year}/{month})"
    if year:
        return f"Classifier Output — {ts} ({year})"
    return f"Classifier Output — {ts}"


def _dedup_manifest(rows: list[dict]) -> tuple[list[dict], int, list]:
    """Run deduplication on raw manifest dicts. Returns (deduped_rows, n_removed, decisions)."""
    from .manifest import load_manifest
    from .dedup import deduplicate
    import tempfile, pathlib

    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        json.dump(rows, f)
        tmp = pathlib.Path(f.name)

    try:
        docs = load_manifest(tmp)
    finally:
        tmp.unlink()

    deduped, decisions = deduplicate(docs)
    deduped_ids = {d.doc_id for d in deduped}
    result = [r for r in rows if r["doc_id"] in deduped_ids]
    return result, len(rows) - len(result), decisions


def _score_label(score: float) -> str:
    from .classifiers import AMBIGUOUS_LO, AMBIGUOUS_HI
    if score > AMBIGUOUS_HI:
        return "certain"
    if score < AMBIGUOUS_LO:
        return "unlikely"
    return "ambiguous"


def _write_csv(results: list, path: Path) -> None:
    import csv
    if not results:
        return
    slugs = list(results[0].topics.keys())
    category_cols = []
    for s in slugs:
        category_cols += [f"{s}_score", f"{s}_label", f"{s}_identified"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["web_url", "name", "date", "agency", "model_used"] + category_cols)
        for r in results:
            row = [r.web_url, r.name, r.date or r.date_raw, r.agency, r.model_used]
            for s in slugs:
                cat = r.topics[s]
                row.append(cat["score"])
                row.append(_score_label(cat["score"]))
                row.append("; ".join(cat.get("identified", [])))
            writer.writerow(row)


def _render_review(decisions: list) -> str:
    lines = [
        "# Deduplication Review",
        "",
        "Docs grouped as duplicates by the pipeline. "
        "Verify the kept version is correct — default is newest by modification time.",
        "",
    ]
    if not decisions:
        lines.append("No duplicates found.")
        return "\n".join(lines)
    for d in decisions:
        lines.append(f"## {d.kept.name}")
        lines.append(f"- **reason**: {d.reason}")
        lines.append(f"- **KEPT** (modified {d.kept.modified_time}): [{d.kept.name}]({d.kept.web_url})")
        for dropped in d.dropped:
            lines.append(f"- dropped (modified {dropped.modified_time}): [{dropped.name}]({dropped.web_url})")
        lines.append("")
    return "\n".join(lines)
