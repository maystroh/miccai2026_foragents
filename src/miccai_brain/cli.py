"""Command line entry point: python -m src.miccai_brain <command>."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from . import load_dotenv, store

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
    # Graph analytics (no embedder, no paid model). All print JSON so agents can parse them.
    v = sub.add_parser("vocab", help="most frequent names of one kind (task, method, anatomy, dataset, modality, ...)")
    v.add_argument("kind")
    v.add_argument("-m", "--modality")
    v.add_argument("-n", "--top", type=int, default=50)
    nb = sub.add_parser("neighbors", help="what co-occurs with a concept/dataset/modality, ranked by lift")
    nb.add_argument("name")
    nb.add_argument("-k", "--kind")
    nb.add_argument("-o", "--other-kind")
    nb.add_argument("-m", "--modality")
    nb.add_argument("-n", "--top", type=int, default=20)
    mx = sub.add_parser("matrix", help="coverage counts between two kinds (e.g. method anatomy)")
    mx.add_argument("row_kind")
    mx.add_argument("col_kind")
    mx.add_argument("-m", "--modality")
    mx.add_argument("--rows", nargs="*")
    mx.add_argument("--cols", nargs="*")
    g = sub.add_parser("gaps", help="white-space pairs: both common, rarely together, semantically close")
    g.add_argument("kind_a")
    g.add_argument("kind_b")
    g.add_argument("-m", "--modality")
    g.add_argument("--min-papers", type=int, default=5)
    g.add_argument("--max-together", type=int, default=1)
    g.add_argument("--focus")
    g.add_argument("-n", "--top", type=int, default=25)
    br = sub.add_parser("bridge", help="papers combining A and B, and the closest one-sided papers")
    br.add_argument("a")
    br.add_argument("b")
    br.add_argument("-n", "--top", type=int, default=10)
    cl = sub.add_parser("claims", help="LLM-extracted limitations or contributions")
    cl.add_argument("--kind", choices=["limitation", "contribution"], default="limitation")
    cl.add_argument("-c", "--concept")
    cl.add_argument("-m", "--modality")
    cl.add_argument("-q", "--query")
    cl.add_argument("-n", "--limit", type=int, default=40)
    cl.add_argument("--themes", action="store_true", help="group limitations into recurring themes")
    cl.add_argument("--reload", action="store_true", help="refill the claims table from the LLM cache")
    w = sub.add_parser("weaknesses", help="what reviewers criticise for a concept and/or topic")
    w.add_argument("-c", "--concept")
    w.add_argument("-m", "--modality")
    w.add_argument("-n", "--top", type=int, default=15)
    x = sub.add_parser("extract", help="LLM extraction of tasks/methods/datasets via OpenRouter (cached; run before build)")
    x.add_argument("--root", default=".")
    x.add_argument("--model", help="OpenRouter model id (default: $MICCAI_BRAIN_LLM_MODEL)")
    x.add_argument("--modality", action="append")
    x.add_argument("--limit", type=int, help="only this many papers (pilot)")
    x.add_argument("--workers", type=int, default=4)
    x.add_argument("--force", action="store_true")
    x.add_argument("--max-cost", type=float, default=5.0, help="stop once this many USD are spent in this run (default: %(default)s)")
    x.add_argument("--spent", action="store_true", help="only print the total cost recorded in the cache")

    args = parser.parse_args(argv)
    load_dotenv(Path(getattr(args, "root", ".")) / ".env")
    load_dotenv(".env")
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
        if args.spent:
            from .extract_llm import spent
            print(json.dumps(spent(Path(args.root))))
            return 0
        usage = extract_all(Path(args.root), load_papers(Path(args.root), args.modality), model,
                            args.workers, args.force, args.limit, args.max_cost)
        print(json.dumps(usage))
        return 1 if usage["failed"] else 0
    if args.cmd == "serve":
        from .mcp_server import serve
        serve(args.db)
        return 0

    if args.cmd in ("vocab", "neighbors", "matrix", "gaps", "bridge", "claims", "weaknesses"):
        from .explore import Explorer, load_claims
        conn = store.connect(args.db)
        if args.cmd == "claims" and args.reload:
            print(f"{load_claims(conn, '.')} claims loaded", flush=True)
        ex = Explorer(conn, ".")
        if args.cmd == "vocab":
            out = ex.vocabulary(args.kind, args.modality, args.top)
        elif args.cmd == "neighbors":
            out = ex.neighbors(args.name, args.kind, args.other_kind, args.modality, args.top)
        elif args.cmd == "matrix":
            out = ex.matrix(args.row_kind, args.col_kind, args.modality, rows=args.rows, cols=args.cols)
        elif args.cmd == "gaps":
            out = ex.gaps(args.kind_a, args.kind_b, args.modality, args.min_papers, args.max_together, args.top, args.focus)
        elif args.cmd == "bridge":
            out = ex.bridges(args.a, args.b, top=args.top)
        elif args.cmd == "weaknesses":
            out = ex.reviewer_weaknesses(args.concept, None, args.modality, args.top)
        elif args.themes:
            out = ex.limitation_themes(args.concept, None, args.modality)
        else:
            out = ex.claims(args.kind, args.concept, None, args.modality, args.query, args.limit)
        print(json.dumps(out, indent=1, ensure_ascii=False))
        return 0

    from .search import Brain
    brain = Brain(args.db)
    if args.cmd == "search":
        hits = brain.search(args.query, args.modality, args.limit, args.reviews, args.mode)
        if brain.last_warning:
            print(f"warning: {brain.last_warning}", file=__import__("sys").stderr)
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
