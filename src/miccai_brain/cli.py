"""Command line entry point: python -m src.miccai_brain <command>."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from . import store

DEFAULT_HTML = Path("reports/miccai_brain/brain.html")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="miccai_brain", description="Hybrid search and topic graphs over MICCAI 2026 papers.")
    parser.add_argument("--db", default=str(store.DEFAULT_DB), help="SQLite file (default: %(default)s)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="ingest papers and reviews, embed, link, and write the dashboard")
    b.add_argument("--root", default=".", help="miccai2026 folder holding Published_papers/ and Published_reviews/")
    b.add_argument("--embedder", help="provider:model (default: $MICCAI_BRAIN_EMBEDDER)")
    b.add_argument("--modality", action="append", help="limit to these modality folders (repeatable)")
    b.add_argument("--no-reviews", action="store_true")
    b.add_argument("--neighbors", type=int, default=8)
    b.add_argument("--html", default=str(DEFAULT_HTML))

    s = sub.add_parser("search", help="hybrid search")
    s.add_argument("query")
    s.add_argument("-m", "--modality")
    s.add_argument("-n", "--limit", type=int, default=10)
    s.add_argument("--reviews", action="store_true", help="also search review texts")
    s.add_argument("--mode", choices=["hybrid", "keyword", "vector"], default="hybrid")
    s.add_argument("--json", action="store_true")

    p = sub.add_parser("paper", help="show one paper with concepts, datasets and reviews")
    p.add_argument("paper_id")
    r = sub.add_parser("related", help="papers most similar to one paper")
    r.add_argument("paper_id")
    r.add_argument("-m", "--modality")
    r.add_argument("-n", "--limit", type=int, default=10)
    t = sub.add_parser("topic", help="overview of one modality (or list all with no argument)")
    t.add_argument("modality", nargs="?")
    c = sub.add_parser("concept", help="papers tagged with a concept or dataset")
    c.add_argument("name")
    c.add_argument("-m", "--modality")
    d = sub.add_parser("dashboard", help="rewrite the dashboard HTML from the existing database")
    d.add_argument("--html", default=str(DEFAULT_HTML))
    sub.add_parser("serve", help="run the MCP server over stdio")
    x = sub.add_parser("extract", help="LLM extraction of tasks/methods/datasets via OpenRouter (cached; run before build)")
    x.add_argument("--root", default=".")
    x.add_argument("--model", help="OpenRouter model id (default: $MICCAI_BRAIN_LLM_MODEL)")
    x.add_argument("--modality", action="append")
    x.add_argument("--limit", type=int, help="only this many papers (pilot)")
    x.add_argument("--workers", type=int, default=4)
    x.add_argument("--force", action="store_true")

    args = parser.parse_args(argv)
    if args.cmd == "build":
        from .build import build
        from .graph import write_dashboard
        build(Path(args.root), Path(args.db), args.embedder, args.modality, not args.no_reviews, args.neighbors)
        out = write_dashboard(store.connect(args.db), Path(args.html))
        print(f"dashboard: {out}")
        return 0
    if args.cmd == "dashboard":
        from .graph import write_dashboard
        print(write_dashboard(store.connect(args.db), Path(args.html)))
        return 0
    if args.cmd == "extract":
        import os
        from .corpus import load_papers
        from .extract_llm import extract_all
        model = args.model or os.environ.get("MICCAI_BRAIN_LLM_MODEL")
        if not model:
            parser.error("give --model or set MICCAI_BRAIN_LLM_MODEL")
        usage = extract_all(Path(args.root), load_papers(Path(args.root), args.modality), model,
                            args.workers, args.force, args.limit)
        print(json.dumps(usage))
        return 1 if usage["failed"] else 0
    if args.cmd == "serve":
        from .mcp_server import serve
        serve(args.db)
        return 0

    from .search import Brain
    brain = Brain(args.db)
    if args.cmd == "search":
        hits = brain.search(args.query, args.modality, args.limit, args.reviews, args.mode)
        if args.json:
            print(json.dumps([asdict(h) for h in hits], indent=2, ensure_ascii=False))
        for i, h in enumerate(hits if not args.json else [], 1):
            print(f"{i:2}. [{h.paper_id}] {h.title}\n    {', '.join(h.modalities)} | score {h.score} | {h.sources} | {h.kind}: {h.section}\n    {h.snippet}\n")
    elif args.cmd == "paper":
        print(json.dumps(brain.paper(args.paper_id), indent=2, ensure_ascii=False))
    elif args.cmd == "related":
        for row in brain.related(args.paper_id, args.limit, args.modality):
            print(f"{row['similarity']:.3f}  [{row['paper_id']}] {row['title']}  shared: {', '.join(row['shared_concepts'][:5])}")
    elif args.cmd == "topic":
        print(json.dumps(brain.topic_overview(args.modality) if args.modality else brain.topics(), indent=2, ensure_ascii=False))
    elif args.cmd == "concept":
        for row in brain.concept_papers(args.name, args.modality):
            print(f"[{row['paper_id']}] {row['title']}")
    return 0
