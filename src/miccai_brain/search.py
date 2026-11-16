"""Hybrid search: FTS5 BM25 + cosine vectors, fused per paper with reciprocal rank fusion."""
from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass, field

import numpy as np

from . import store
from .embed import get_embedder

RRF_K = 60
STOPWORDS = set("a an and are as at be by for from in is it of on or that the this to with we our using via".split())


@dataclass
class Hit:
    paper_id: str
    title: str
    score: float
    modalities: list[str]
    snippet: str
    section: str
    kind: str
    sources: dict = field(default_factory=dict)  # {"bm25": rank, "vector": rank}


class Brain:
    def __init__(self, db_path=store.DEFAULT_DB, embedder_spec: str | None = None):
        self.conn = store.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        # Queries can use a different (compatible) embedder than the build, e.g. the same Qwen3
        # model run locally with sentence-transformers instead of the GPU server.
        self.embedder_spec = (embedder_spec or os.environ.get("MICCAI_BRAIN_QUERY_EMBEDDER")
                              or store.get_meta(self.conn, "embedder"))
        self._embedder = None
        self._matrix = None

    @property
    def embedder(self):
        if self._embedder is None:
            self._embedder = get_embedder(self.embedder_spec)
        return self._embedder

    def _load_vectors(self):
        if self._matrix is None:
            rows = self.conn.execute("SELECT id, paper_id, kind, vector FROM chunks").fetchall()
            self._ids = np.array([r["id"] for r in rows])
            self._papers = [r["paper_id"] for r in rows]
            self._kinds = [r["kind"] for r in rows]
            self._matrix = np.vstack([store.from_blob(r["vector"]) for r in rows]) if rows else np.zeros((0, 1))
        return self._matrix

    def _allowed(self, modality: str | None) -> set[str] | None:
        if not modality:
            return None
        rows = self.conn.execute("SELECT paper_id FROM paper_modalities WHERE lower(modality) = lower(?)", (modality,))
        return {r[0] for r in rows}

    def _bm25(self, query: str, kinds, allowed, limit=400) -> list[tuple[int, str]]:
        tokens = [t for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9\-]*", query) if t.lower() not in STOPWORDS]
        if not tokens:
            return []
        match = " OR ".join('"' + t.replace('"', "") + '"' for t in tokens)
        rows = self.conn.execute(
            "SELECT c.id, c.paper_id, c.kind FROM chunks_fts f JOIN chunks c ON c.id = f.rowid "
            "WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts, 4.0, 2.0, 1.0) LIMIT ?", (match, limit)).fetchall()
        return [(r["id"], r["paper_id"]) for r in rows
                if r["kind"] in kinds and (allowed is None or r["paper_id"] in allowed)]

    def _vector(self, query: str, kinds, allowed, limit=400) -> list[tuple[int, str]]:
        matrix = self._load_vectors()
        if not len(matrix):
            return []
        qvec = self.embedder.embed([query], query=True)[0]
        sims = matrix @ qvec
        out = []
        for i in np.argsort(-sims):
            if self._kinds[i] in kinds and (allowed is None or self._papers[i] in allowed):
                out.append((int(self._ids[i]), self._papers[i]))
                if len(out) >= limit:
                    break
        return out

    def search(self, query: str, modality: str | None = None, limit: int = 10, include_reviews: bool = False,
               mode: str = "hybrid") -> list[Hit]:
        kinds = {"abstract", "body"} | ({"review"} if include_reviews else set())
        allowed = self._allowed(modality)
        lists = {}
        if mode in ("hybrid", "keyword"):
            lists["bm25"] = self._bm25(query, kinds, allowed)
        if mode in ("hybrid", "vector"):
            lists["vector"] = self._vector(query, kinds, allowed)
        scores: dict[str, float] = {}
        best_chunk: dict[str, tuple[float, int]] = {}
        sources: dict[str, dict] = {}
        for name, ranked in lists.items():
            seen = set()
            rank = 0
            for chunk_id, pid in ranked:
                contrib = 1.0 / (RRF_K + rank + 1)
                if pid not in seen:  # paper-level rank: first chunk only
                    seen.add(pid)
                    scores[pid] = scores.get(pid, 0.0) + contrib
                    sources.setdefault(pid, {})[name] = rank + 1
                    rank += 1
                if pid not in best_chunk or contrib > best_chunk[pid][0]:
                    best_chunk[pid] = (contrib, chunk_id)
        ordered = sorted(scores, key=scores.get, reverse=True)[:limit]
        hits = []
        for pid in ordered:
            paper = store.paper_row(self.conn, pid)
            chunk = self.conn.execute("SELECT kind, section, text FROM chunks WHERE id = ?", (best_chunk[pid][1],)).fetchone()
            hits.append(Hit(pid, paper["title"], round(scores[pid], 5), paper["modalities"],
                            snippet(chunk["text"], query), chunk["section"], chunk["kind"], sources[pid]))
        return hits

    def paper(self, paper_id: str, with_reviews: bool = True) -> dict | None:
        paper = store.paper_row(self.conn, paper_id)
        if not paper:
            return None
        paper["concepts"] = [dict(r) for r in self.conn.execute(
            "SELECT concept, kind FROM paper_concepts WHERE paper_id = ?", (paper_id,))]
        paper["datasets"] = [dict(r) for r in self.conn.execute(
            "SELECT dataset, mentions FROM paper_datasets WHERE paper_id = ? ORDER BY mentions DESC", (paper_id,))]
        if with_reviews:
            paper["reviews"] = [dict(r) for r in self.conn.execute(
                "SELECT section AS role, text FROM chunks WHERE paper_id = ? AND kind = 'review' ORDER BY id", (paper_id,))]
        return paper

    def related(self, paper_id: str, limit: int = 10, modality: str | None = None) -> list[dict]:
        allowed = self._allowed(modality)
        rows = self.conn.execute(
            "SELECT CASE WHEN src = ? THEN dst ELSE src END AS other, weight FROM paper_edges "
            "WHERE src = ? OR dst = ? ORDER BY weight DESC", (paper_id, paper_id, paper_id)).fetchall()
        out = []
        for r in rows:
            if allowed is not None and r["other"] not in allowed:
                continue
            p = store.paper_row(self.conn, r["other"])
            shared = [x[0] for x in self.conn.execute(
                "SELECT a.concept FROM paper_concepts a JOIN paper_concepts b ON a.concept = b.concept "
                "WHERE a.paper_id = ? AND b.paper_id = ?", (paper_id, r["other"]))]
            out.append({"paper_id": r["other"], "title": p["title"], "similarity": round(r["weight"], 3),
                        "shared_concepts": shared, "modalities": p["modalities"]})
            if len(out) >= limit:
                break
        return out

    def topics(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT modality, COUNT(*) AS papers FROM paper_modalities GROUP BY modality ORDER BY papers DESC")]

    def topic_overview(self, modality: str, top: int = 15) -> dict:
        allowed = self._allowed(modality) or set()
        if not allowed:
            return {"modality": modality, "papers": 0}
        marks = ",".join("?" * len(allowed))
        concepts = self.conn.execute(
            f"SELECT concept, COUNT(*) n FROM paper_concepts WHERE paper_id IN ({marks}) AND kind NOT IN ('body','application','ml') "
            f"GROUP BY concept ORDER BY n DESC LIMIT ?", (*allowed, top)).fetchall()
        tags = self.conn.execute(
            f"SELECT concept, kind, COUNT(*) n FROM paper_concepts WHERE paper_id IN ({marks}) AND kind IN ('body','application','ml') "
            f"GROUP BY concept, kind ORDER BY n DESC LIMIT ?", (*allowed, top)).fetchall()
        datasets = self.conn.execute(
            f"SELECT dataset, COUNT(*) n FROM paper_datasets WHERE paper_id IN ({marks}) "
            f"GROUP BY dataset ORDER BY n DESC LIMIT ?", (*allowed, top)).fetchall()
        return {"modality": modality, "papers": len(allowed),
                "top_concepts": [dict(r) for r in concepts], "top_tags": [dict(r) for r in tags],
                "top_datasets": [dict(r) for r in datasets]}

    def concept_papers(self, concept: str, modality: str | None = None, limit: int = 50) -> list[dict]:
        allowed = self._allowed(modality)
        rows = self.conn.execute(
            "SELECT DISTINCT p.paper_id, p.title FROM papers p JOIN paper_concepts c ON c.paper_id = p.paper_id "
            "WHERE c.concept = lower(?) UNION SELECT DISTINCT p.paper_id, p.title FROM papers p "
            "JOIN paper_datasets d ON d.paper_id = p.paper_id WHERE lower(d.dataset) = lower(?)", (concept, concept))
        return [dict(r) for r in rows if allowed is None or r["paper_id"] in allowed][:limit]


def snippet(text: str, query: str, width: int = 320) -> str:
    text = re.sub(r"\s+", " ", text)
    terms = [t.lower() for t in re.findall(r"\w{3,}", query) if t.lower() not in STOPWORDS]
    lower = text.lower()
    pos = min((lower.find(t) for t in terms if lower.find(t) >= 0), default=0)
    start = max(0, pos - width // 3)
    out = text[start : start + width]
    return ("…" if start else "") + out + ("…" if start + width < len(text) else "")
