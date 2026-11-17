"""Export the brain as one compact JSON graph and a self-contained dashboard page."""
from __future__ import annotations

import json
from pathlib import Path

from . import store

TEMPLATE = Path(__file__).with_name("dashboard_template.html")


def export_graph(conn, min_concept_papers: int = 2, max_abstract: int = 900) -> dict:
    papers = [store.paper_row(conn, r[0]) for r in conn.execute("SELECT paper_id FROM papers ORDER BY paper_id")]
    index = {p["paper_id"]: i for i, p in enumerate(papers)}

    concept_rows = conn.execute(
        "SELECT concept, COUNT(*) n, (SELECT kind FROM paper_concepts k WHERE k.concept = p.concept GROUP BY kind"
        " ORDER BY COUNT(*) DESC, kind LIMIT 1) kind FROM paper_concepts p GROUP BY concept HAVING n >= ?"
        " ORDER BY n DESC, concept",
        (min_concept_papers,)).fetchall()
    concepts = [{"n": r["concept"], "k": r["kind"], "c": r["n"]} for r in concept_rows]
    cidx = {c["n"]: i for i, c in enumerate(concepts)}

    dataset_rows = conn.execute(
        "SELECT dataset, COUNT(*) n FROM paper_datasets GROUP BY dataset ORDER BY n DESC").fetchall()
    datasets = [{"n": r["dataset"], "c": r["n"]} for r in dataset_rows]
    didx = {d["n"]: i for i, d in enumerate(datasets)}

    pconcepts = {}
    for r in conn.execute("SELECT paper_id, concept FROM paper_concepts"):
        if r["concept"] in cidx:
            pconcepts.setdefault(r["paper_id"], []).append(cidx[r["concept"]])
    pdatasets = {}
    for r in conn.execute("SELECT paper_id, dataset FROM paper_datasets"):
        pdatasets.setdefault(r["paper_id"], []).append(didx[r["dataset"]])
    nreviews = dict(conn.execute("SELECT paper_id, COUNT(*) FROM chunks WHERE kind = 'review' GROUP BY paper_id").fetchall())

    out_papers = []
    for p in papers:
        abstract = p["abstract"]
        if len(abstract) > max_abstract:
            abstract = abstract[:max_abstract].rsplit(" ", 1)[0] + "…"
        out_papers.append({
            "id": p["paper_id"], "t": p["title"], "m": p["modalities"], "d": p["decision"],
            "u": p["paper_url"], "g": p["code_url"], "a": abstract,
            "au": ", ".join(p["authors"][:6]) + (" et al." if len(p["authors"]) > 6 else ""),
            "k": pconcepts.get(p["paper_id"], []), "s": pdatasets.get(p["paper_id"], []),
            "r": nreviews.get(p["paper_id"], 0),
        })
    edges = [[index[r["src"]], index[r["dst"]], round(r["weight"], 3)]
             for r in conn.execute("SELECT src, dst, weight FROM paper_edges")
             if r["src"] in index and r["dst"] in index]
    topics = [dict(r) for r in conn.execute(
        "SELECT modality, COUNT(*) AS papers FROM paper_modalities GROUP BY modality ORDER BY papers DESC")]
    return {"stats": store.get_meta(conn, "stats", {}), "topics": topics, "papers": out_papers,
            "concepts": concepts, "datasets": datasets, "edges": edges}


def write_dashboard(conn, out_path: Path, **kwargs) -> Path:
    data = export_graph(conn, **kwargs)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*__BRAIN_DATA__*/null", payload)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    out_path.with_suffix(".json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return out_path
