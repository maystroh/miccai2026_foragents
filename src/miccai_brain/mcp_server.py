"""MCP server so Claude (or any MCP client) can query the brain.

Register with Claude Code from the miccai2026 folder (the repo's .mcp.json does this already):
  claude mcp add miccai-brain -- python -m src.miccai_brain serve
"""
from __future__ import annotations

import functools
import inspect
import json
import threading
from dataclasses import asdict

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP

from . import store
from .explore import ALL_KINDS, Explorer
from .guide import guide_markdown
from .search import Brain

INSTRUCTIONS = f"""MICCAI brain: all MICCAI 2026 papers (abstract, peer reviews) with an extracted concept graph.
Kinds: {', '.join(ALL_KINDS)} ("modality" = topic folder such as MRI, CT, Pathology). brain_guide lists every tool.
Cite every claim with its paper_id. Save tokens: summary tools first (topic_overview, vocabulary, limitation_themes,
reviewer_weaknesses); for a subject filter with about= (find_papers_about) rather than concept=; open at most 3 papers
with get_paper; read reviews with paper_reviews, not get_paper(include_reviews=True). A gap is only a candidate until
search_papers finds no paper doing it."""


def _slim(value):
    """Drop empty fields and round floats so tool results stay small."""
    if isinstance(value, float):
        return round(value, 3)
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            item = _slim(item)
            if item is not None and item != "" and item != [] and item != {}:
                out[key] = item
        return out
    if isinstance(value, (list, tuple)):
        return [_slim(item) for item in value]
    return value


def compact(value) -> str:
    """One-line JSON: the MCP runtime would otherwise send indented JSON, and lists twice (text + structured)."""
    if isinstance(value, str):
        return value
    return json.dumps(_slim(value), ensure_ascii=False, separators=(",", ":"), default=str)


def _lean_paper(paper: dict) -> dict:
    concepts: dict[str, list] = {}
    for c in paper.pop("concepts", []):
        concepts.setdefault(c["kind"], []).append(c["concept"])
    authors = paper.get("authors") or []
    for key in ("body", "pdf_url", "folder"):
        paper.pop(key, None)
    paper["authors"] = authors[:3] + (["et al."] if len(authors) > 3 else [])
    paper["concepts"] = concepts
    paper["datasets"] = [d["dataset"] for d in paper.get("datasets", [])]
    return paper


def create_server(db_path=store.DEFAULT_DB, root=".") -> FastMCP:
    # The MCP runtime calls sync tools from worker threads: share one connection behind a lock.
    brain = Brain(db_path, check_same_thread=False)
    explorer = Explorer(brain.conn, root)
    lock = threading.Lock()
    try:
        mcp = FastMCP("miccai-brain", instructions=INSTRUCTIONS)
    except TypeError:
        mcp = FastMCP("miccai-brain")

    class _Locked:
        @staticmethod
        def tool():
            def register(fn):
                @functools.wraps(fn)
                def run(*args, **kwargs):
                    with lock:
                        return compact(fn(*args, **kwargs))
                del run.__wrapped__
                run.__signature__ = inspect.signature(fn).replace(return_annotation=str)
                run.__annotations__ = {**fn.__annotations__, "return": str}
                try:
                    return mcp.tool(structured_output=False)(run)
                except TypeError:  # older mcp
                    return mcp.tool()(run)
            return register

    server = _Locked()

    @server.tool()
    def search_papers(query: str, modality: str | None = None, limit: int = 10, include_reviews: bool = False,
                      mode: str = "hybrid") -> dict:
        """Hybrid keyword + semantic search over MICCAI 2026 papers. modality is a topic folder
        name such as MRI, EHR or Diffusion-MRI. include_reviews also matches peer-review text.
        mode: hybrid (default), keyword, or vector. If the embedding server is unreachable, hybrid
        falls back to keyword results and says so in "warning"."""
        hits = []
        for h in brain.search(query, modality, limit, include_reviews, mode):
            hit = asdict(h)
            hit.pop("sources", None)
            hits.append(hit)
        return {"hits": hits, "warning": brain.last_warning}

    @server.tool()
    def get_paper(paper_id: str, include_reviews: bool = False) -> dict | None:
        """One paper (e.g. 0002-Paper5533): metadata, abstract, concepts, datasets, LLM-extracted
        contributions and limitations. Reviews are left out by default because they are long: use
        paper_reviews for the weaknesses of several papers at once. The body text is never included."""
        paper = brain.paper(paper_id, include_reviews)
        if paper:
            paper = _lean_paper(paper)
            paper.update(explorer.claims_of(paper_id))
        return paper

    @server.tool()
    def related_papers(paper_id: str, limit: int = 10, modality: str | None = None) -> list[dict]:
        """Papers most similar to the given one, with up to 5 concepts they share."""
        out = brain.related(paper_id, limit, modality)
        for row in out:
            row["shared_concepts"] = row["shared_concepts"][:5]
        return out

    @server.tool()
    def list_topics() -> list[dict]:
        """All topics (modality folders) with their paper counts."""
        return brain.topics()

    @server.tool()
    def topic_overview(modality: str, top: int = 15) -> dict:
        """Top concepts, MICCAI tags and datasets for one topic."""
        return brain.topic_overview(modality, top)

    @server.tool()
    def papers_with(concept_or_dataset: str, modality: str | None = None) -> list[dict]:
        """Papers tagged with a concept (task, method, anatomy, keyword, MICCAI tag) or using a dataset."""
        return brain.concept_papers(concept_or_dataset, modality)

    @server.tool()
    def vocabulary(kind: str, modality: str | None = None, top: int = 50) -> list[dict]:
        """Most frequent names of one kind with paper counts. kind: task, method, anatomy, metric,
        keyword, dataset, modality, body, application or ml. Use it to learn the exact spellings."""
        return explorer.vocabulary(kind, modality, top)

    @server.tool()
    def neighbors(name: str, kind: str | None = None, other_kind: str | None = None,
                  modality: str | None = None, top: int = 20) -> dict:
        """What co-occurs with a concept, dataset or modality, ranked by lift (how much more often
        than chance). other_kind limits the answer to one kind, e.g. the datasets used with a method."""
        return explorer.neighbors(name, kind, other_kind, modality, top)

    @server.tool()
    def coverage_matrix(row_kind: str, col_kind: str, modality: str | None = None, rows: list[str] | None = None,
                        cols: list[str] | None = None, top_rows: int = 15, top_cols: int = 12) -> dict:
        """Paper counts for every (row, col) pair of two kinds, e.g. method x anatomy or method x
        modality. Zero cells between busy rows and columns are candidate gaps."""
        return explorer.matrix(row_kind, col_kind, modality, top_rows, top_cols, rows, cols)

    @server.tool()
    def find_gaps(kind_a: str, kind_b: str, modality: str | None = None, min_papers: int = 5,
                  max_together: int = 1, focus: str | None = None, top: int = 25) -> list[dict]:
        """White-space pairs: A and B each appear in at least min_papers papers, appear together in at
        most max_together, and their papers are semantically close (so the combination is plausible).
        Ranked by closeness x expected co-occurrence. focus keeps only A names containing that text."""
        return explorer.gaps(kind_a, kind_b, modality, min_papers, max_together, top, focus)

    @server.tool()
    def bridge_papers(name_a: str, name_b: str, kind_a: str | None = None, kind_b: str | None = None,
                      top: int = 10) -> dict:
        """Papers that already combine A and B, and the one-sided papers closest to their midpoint:
        the prior work a project combining A and B would build on."""
        return explorer.bridges(name_a, name_b, kind_a, kind_b, top)

    @server.tool()
    def paper_claims(kind: str = "limitation", concept: str | None = None, modality: str | None = None,
                     query: str | None = None, about: str | None = None, paper_ids: list[str] | None = None,
                     limit: int = 20) -> list[dict]:
        """LLM-extracted contributions or limitations (kind) of papers. Filters combine: concept tag, topic
        (modality), about (main subject in title/abstract, see find_papers_about), paper_ids, and keywords
        in the claim text (query)."""
        return explorer.claims(kind, concept, None, modality, query, limit, about, paper_ids)

    @server.tool()
    def limitation_themes(concept: str | None = None, modality: str | None = None, about: str | None = None,
                          paper_ids: list[str] | None = None, top: int = 15) -> list[dict]:
        """Recurring limitation themes (single-centre, small data, 2D only, ...) with shares and examples.
        Same filters as paper_claims."""
        return explorer.limitation_themes(concept, None, modality, top, about, paper_ids)

    @server.tool()
    def reviewer_weaknesses(concept: str | None = None, modality: str | None = None, about: str | None = None,
                            paper_ids: list[str] | None = None, top: int = 15) -> dict:
        """What MICCAI 2026 reviewers criticised: weakness themes (novelty, baselines, small data, ablation,
        statistics, ...) with the share of reviewed papers hit, short quotes, and the papers counted.
        For a subject such as breast MRI use about="breast, MRI|magnetic resonance|DCE" (main subject),
        not concept="breast", which also matches benchmarks that include one breast dataset."""
        return explorer.reviewer_weaknesses(concept, None, modality, top, 3, about, paper_ids)

    @server.tool()
    def find_papers_about(about: str, modality: str | None = None, limit: int = 100) -> list[dict]:
        """Papers whose main subject matches: every comma-separated term must appear in the title or
        abstract, and "|" separates synonyms. Example: "breast, MRI|magnetic resonance|DCE"."""
        return explorer.find_papers_about(about, modality, limit)

    @server.tool()
    def paper_reviews(paper_ids: list[str], part: str = "weaknesses", max_chars: int = 1200) -> list[dict]:
        """Compact reviews for up to ~10 papers: each reviewer's rating and weaknesses (part="all" for the
        full review), cut to max_chars, plus the start of the meta review. Use this instead of get_paper
        with include_reviews to read what reviewers said."""
        return explorer.paper_reviews(paper_ids, part, max_chars)

    @server.tool()
    def brain_guide() -> dict:
        """Start here: every brain tool with what it answers, an example question and the CLI equivalent,
        plus the kinds of concepts, typical tool sequences and related commands."""
        return guide_markdown(cli=False)

    return mcp


def serve(db_path=store.DEFAULT_DB, root=".") -> None:
    create_server(db_path, root).run()
