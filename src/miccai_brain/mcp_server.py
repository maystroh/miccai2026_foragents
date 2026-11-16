"""MCP server so Claude (or any MCP client) can query the brain.

Register with Claude Code from the miccai2026 folder:
  claude mcp add miccai-brain -- python -m src.miccai_brain serve
"""
from __future__ import annotations

from dataclasses import asdict

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP

from . import store
from .search import Brain


def create_server(db_path=store.DEFAULT_DB) -> FastMCP:
    brain = Brain(db_path)
    server = FastMCP("miccai-brain")

    @server.tool()
    def search_papers(query: str, modality: str | None = None, limit: int = 10, include_reviews: bool = False) -> list[dict]:
        """Hybrid keyword + semantic search over MICCAI 2026 papers. modality is a topic folder
        name such as MRI, EHR or Diffusion-MRI. include_reviews also matches peer-review text."""
        return [asdict(h) for h in brain.search(query, modality, limit, include_reviews)]

    @server.tool()
    def get_paper(paper_id: str, include_reviews: bool = True) -> dict | None:
        """Full record for one paper (e.g. 0002-Paper5533): metadata, abstract, concepts, datasets, reviews."""
        return brain.paper(paper_id, include_reviews)

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
        """Top author keywords, MICCAI tags and datasets for one topic."""
        return brain.topic_overview(modality, top)

    @server.tool()
    def papers_with(concept_or_dataset: str, modality: str | None = None) -> list[dict]:
        """Papers tagged with a concept (author keyword or MICCAI tag) or using a dataset."""
        return brain.concept_papers(concept_or_dataset, modality)

    return server


def serve(db_path=store.DEFAULT_DB) -> None:
    create_server(db_path).run()
