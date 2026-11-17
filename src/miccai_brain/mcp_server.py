"""MCP server so Claude (or any MCP client) can query the brain.

Register with Claude Code from the miccai2026 folder (the repo's .mcp.json does this already):
  claude mcp add miccai-brain -- python -m src.miccai_brain serve
"""
from __future__ import annotations

import functools
import threading
from dataclasses import asdict

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP

from . import store
from .explore import ALL_KINDS, Explorer
from .search import Brain

INSTRUCTIONS = f"""MICCAI brain: all MICCAI 2026 papers (abstract, body, peer reviews) with an extracted graph of
concepts. Kinds: {', '.join(ALL_KINDS)} ("modality" = topic folder such as MRI, CT, Pathology).
Cite every claim with its paper_id and title. Start broad (vocabulary, topic_overview), then narrow
(neighbors, matrix, gaps), then read the actual papers (get_paper) before asserting anything.
A gap is only a candidate until you have searched for it (search_papers) and found no paper doing it."""


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
                        return fn(*args, **kwargs)
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
        hits = [asdict(h) for h in brain.search(query, modality, limit, include_reviews, mode)]
        return {"hits": hits, "warning": brain.last_warning}

    @server.tool()
    def get_paper(paper_id: str, include_reviews: bool = True) -> dict | None:
        """Full record for one paper (e.g. 0002-Paper5533): metadata, abstract, concepts, datasets,
        LLM-extracted contributions and limitations, and peer reviews. The body text is left out;
        use search_papers to find passages."""
        paper = brain.paper(paper_id, include_reviews)
        if paper:
            paper.pop("body", None)
            paper.update(explorer.claims_of(paper_id))
        return paper

    @server.tool()
    def related_papers(paper_id: str, limit: int = 10, modality: str | None = None) -> list[dict]:
        """Papers most similar to the given one, with the concepts they share."""
        return brain.related(paper_id, limit, modality)

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
                     query: str | None = None, limit: int = 40) -> list[dict]:
        """LLM-extracted contributions or limitations (kind) of papers, filtered by a concept, a topic
        and/or keywords in the claim text. Limitations are the authors' own open problems."""
        return explorer.claims(kind, concept, None, modality, query, limit)

    @server.tool()
    def limitation_themes(concept: str | None = None, modality: str | None = None, top: int = 15) -> list[dict]:
        """Recurring limitation themes (single-centre, small data, 2D only, ...) with shares and examples,
        for a concept, a topic, or the whole corpus."""
        return explorer.limitation_themes(concept, None, modality, top)

    return mcp


def serve(db_path=store.DEFAULT_DB, root=".") -> None:
    create_server(db_path, root).run()
