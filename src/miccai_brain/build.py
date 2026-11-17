"""Build (or refresh) the brain: ingest, extract, embed, link."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np

from . import store
from .chunking import chunk_paper
from .corpus import load_papers
from .embed import get_embedder
from .extract import (TAG_KINDS, load_aliases, load_dataset_patterns, load_stoplist, normalize_concept,
                      paper_concepts, paper_datasets)
from .extract_llm import llm_concepts, load_cached


def _hash(spec: str, text: str) -> str:
    return hashlib.sha1(f"{spec}\n{text}".encode()).hexdigest()


def build(root: Path, db_path: Path, embedder_spec: str | None = None, modalities=None,
          with_reviews: bool = True, neighbors: int = 8, min_similarity: float = 0.0, log=print) -> dict:
    t0 = time.time()
    root = Path(root)
    papers = load_papers(root, modalities)
    log(f"loaded {len(papers)} papers")
    aliases, patterns = load_aliases(root), load_dataset_patterns(root)
    stoplist = load_stoplist(root)
    embedder = get_embedder(embedder_spec)
    db_path = Path(db_path)
    cache = store.connect_cache(db_path)
    # Build into a fresh file; the live index is replaced only once everything succeeded.
    tmp_path = db_path.with_name(db_path.name + ".building")
    tmp_path.unlink(missing_ok=True)
    conn = store.connect(tmp_path)
    try:
        stats = _build_into(conn, cache, root, papers, aliases, patterns, stoplist, embedder,
                            with_reviews, neighbors, min_similarity, t0, log)
    except BaseException:
        conn.close()  # Windows cannot delete a file that is still open
        tmp_path.unlink(missing_ok=True)
        raise
    finally:
        cache.close()
        if hasattr(embedder, "close"):
            embedder.close()
    os.replace(tmp_path, db_path)
    log(json.dumps(stats))
    return stats


def _build_into(conn, cache, root, papers, aliases, patterns, stoplist, embedder, with_reviews, neighbors,
                min_similarity, t0, log) -> dict:

    rows = []  # (paper_id, kind, section, text, title)
    llm_papers = 0
    for paper in papers:
        conn.execute(
            "INSERT INTO papers (paper_id, title, paper_url, pdf_url, code_url, authors, abstract, body,"
            " applications, ml_tags, keywords, modalities, decision, folder) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (paper.paper_id, paper.title, paper.paper_url, paper.pdf_url, paper.code_url,
             json.dumps(paper.authors), paper.abstract, paper.body, json.dumps(paper.applications),
             json.dumps(paper.ml_tags), json.dumps(paper.keywords), json.dumps(paper.modalities),
             paper.decision, paper.folder),
        )
        conn.executemany("INSERT OR IGNORE INTO paper_modalities VALUES (?, ?)",
                         [(paper.paper_id, m) for m in paper.modalities])
        found_concepts = paper_concepts(paper, aliases)
        found_datasets = paper_datasets(paper, patterns)
        extra_concepts, extra_datasets = llm_concepts(load_cached(root, paper.paper_id))
        if extra_concepts or extra_datasets:
            llm_papers += 1
        found_concepts += [(normalize_concept(t, aliases), k) for t, k in extra_concepts]
        known = {d.lower() for d, _ in found_datasets}
        for name in extra_datasets:
            canonical = next((d for d, pat in patterns if pat.search(name)), name)
            if canonical.lower() not in known:
                known.add(canonical.lower())
                found_datasets.append((canonical, 1))
        # MICCAI tags are kept as published; author keywords and extracted terms skip the stoplist.
        found_concepts = [(c, k) for c, k in found_concepts if c and (k in TAG_KINDS or c not in stoplist)]
        conn.executemany("INSERT OR IGNORE INTO paper_concepts VALUES (?, ?, ?)",
                         [(paper.paper_id, c, k) for c, k in found_concepts])
        conn.executemany("INSERT OR IGNORE INTO paper_datasets VALUES (?, ?, ?)",
                         [(paper.paper_id, d, n) for d, n in found_datasets])
        rows.append((paper.paper_id, "abstract", "Title and abstract", f"{paper.title}\n\n{paper.abstract}", paper.title))
        for section, text in chunk_paper(paper.markdown):
            rows.append((paper.paper_id, "body", section, text, paper.title))
        if with_reviews:
            for review in paper.reviews:
                label = review.role.replace("_", " ") + (f" ({review.rating})" if review.rating else "")
                rows.append((paper.paper_id, "review", label, review.text, paper.title))
    log(f"{len(rows)} chunks")

    # Embed, reusing cached vectors for unchanged text.
    hashes = [_hash(embedder.spec, r[3]) for r in rows]
    cached = {}
    for start in range(0, len(hashes), 900):
        part = hashes[start : start + 900]
        q = f"SELECT hash, vector FROM embed_cache WHERE hash IN ({','.join('?' * len(part))})"
        cached.update({h: v for h, v in cache.execute(q, part)})
    todo = [i for i, h in enumerate(hashes) if h not in cached]
    log(f"embedding {len(todo)} new chunks ({len(rows) - len(todo)} cached) with {embedder.spec}")
    batch = int(os.environ.get("MICCAI_BRAIN_BUILD_BATCH", "256"))
    for start in range(0, len(todo), batch):
        idx = todo[start : start + batch]
        vecs = embedder.embed([rows[i][3] for i in idx])
        for i, vec in zip(idx, vecs):
            cached[hashes[i]] = store.to_blob(vec)
            cache.execute("INSERT OR REPLACE INTO embed_cache VALUES (?, ?)", (hashes[i], cached[hashes[i]]))
        cache.commit()  # progress survives a failed build
        log(f"  {min(start + batch, len(todo))}/{len(todo)}")

    for (pid, kind, section, text, title), h in zip(rows, hashes):
        cur = conn.execute("INSERT INTO chunks (paper_id, kind, section, text, hash, vector) VALUES (?,?,?,?,?,?)",
                           (pid, kind, section, text, h, cached[h]))
        conn.execute("INSERT INTO chunks_fts (rowid, title, section, text) VALUES (?,?,?,?)",
                     (cur.lastrowid, title, section, text))

    # Paper vector = title/abstract embedding blended with the mean body embedding.
    ids, mats = [], []
    for paper in papers:
        vecs = {k: [] for k in ("abstract", "body")}
        for kind, blob in conn.execute(
                "SELECT kind, vector FROM chunks WHERE paper_id = ? AND kind IN ('abstract','body')", (paper.paper_id,)):
            vecs[kind].append(store.from_blob(blob))
        parts = [np.mean(vecs[k], axis=0) for k in ("abstract", "body") if vecs[k]]
        vec = parts[0] * 0.6 + parts[1] * 0.4 if len(parts) == 2 else parts[0]
        vec = vec / max(np.linalg.norm(vec), 1e-12)
        ids.append(paper.paper_id)
        mats.append(vec)
        conn.execute("UPDATE papers SET vector = ? WHERE paper_id = ?", (store.to_blob(vec), paper.paper_id))

    # Similarity edges: top-k neighbours per paper, kept symmetric.
    if len(ids) > 1:
        matrix = np.vstack(mats)
        sims = matrix @ matrix.T
        np.fill_diagonal(sims, -1)
        k = min(neighbors, len(ids) - 1)
        for i, pid in enumerate(ids):
            for j in np.argsort(-sims[i])[:k]:
                if sims[i, j] >= min_similarity:
                    a, b = sorted((pid, ids[j]))
                    conn.execute("INSERT OR REPLACE INTO paper_edges VALUES (?, ?, ?)", (a, b, float(sims[i, j])))

    stats = {
        "papers": len(papers),
        "chunks": len(rows),
        "embedder": embedder.spec,
        "dim": embedder.dim,
        "reviews": with_reviews,
        "llm_extracted_papers": llm_papers,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "seconds": round(time.time() - t0, 1),
    }
    store.set_meta(conn, "embedder", embedder.spec)
    store.set_meta(conn, "stats", stats)
    conn.commit()
    conn.close()
    return stats
