"""Measure what each brain MCP tool returns to the model, in characters (~4 chars per token).
Usage (repo root): python -m src.miccai_brain.measure [db] [root] ["about terms"] > sizes.json
Run it before and after a change to see how many characters (~4 per token) each tool costs."""
import asyncio, json, sqlite3, sys

from .mcp_server import create_server

db = sys.argv[1] if len(sys.argv) > 1 else "reports/miccai_brain/brain.sqlite"
root = sys.argv[2] if len(sys.argv) > 2 else "."
c = sqlite3.connect(db)
pids = [r[0] for r in c.execute("SELECT DISTINCT paper_id FROM chunks WHERE kind='review' ORDER BY paper_id LIMIT 3")]
mod = c.execute("SELECT modality, COUNT(*) n FROM paper_modalities GROUP BY modality ORDER BY n DESC").fetchone()[0]
def top(kind):
    r = c.execute("SELECT concept, COUNT(*) n FROM paper_concepts WHERE kind=? GROUP BY concept ORDER BY n DESC", (kind,)).fetchone()
    return r[0] if r else c.execute("SELECT concept, COUNT(*) n FROM paper_concepts GROUP BY concept ORDER BY n DESC").fetchone()[0]
method, anat = top("method"), top("anatomy")
about = "breast, MRI|magnetic resonance|DCE" if len(sys.argv) < 4 else sys.argv[3]
calls = [
    ("brain_guide", {}),
    ("search_papers", {"query": "missing MRI sequences", "mode": "keyword"}),
    ("search_papers", {"query": "breast MRI reviewer", "include_reviews": True, "mode": "keyword"}),
    ("get_paper", {"paper_id": pids[0]}),
    ("get_paper", {"paper_id": pids[0], "include_reviews": True}),
    ("related_papers", {"paper_id": pids[0]}),
    ("list_topics", {}),
    ("topic_overview", {"modality": mod}),
    ("papers_with", {"concept_or_dataset": anat}),
    ("find_papers_about", {"about": about}),
    ("vocabulary", {"kind": "method", "modality": mod}),
    ("neighbors", {"name": method, "other_kind": "dataset"}),
    ("coverage_matrix", {"row_kind": "method", "col_kind": "modality"}),
    ("find_gaps", {"kind_a": "method", "kind_b": "modality"}),
    ("bridge_papers", {"name_a": method, "name_b": mod}),
    ("paper_claims", {"modality": mod}),
    ("limitation_themes", {"modality": mod}),
    ("reviewer_weaknesses", {"about": about}),
    ("paper_reviews", {"paper_ids": pids}),
]

async def main():
    mcp = create_server(db, root)
    out = {}
    for name, args in calls:
        try:
            res = await mcp.call_tool(name, args)
        except Exception as e:
            out[f"{name} {json.dumps(args)}"] = f"error: {e}"; continue
        content, structured = (res if isinstance(res, tuple) else (getattr(res, "content", res), getattr(res, "structured_content", None)))
        text = sum(len(getattr(b, "text", "")) for b in content)
        extra = len(json.dumps(structured, separators=(",", ":"))) if structured else 0
        out[f"{name} {json.dumps(args, ensure_ascii=False)}"] = {"text": text, "structured": extra, "total": text + extra}
    print(json.dumps(out, indent=1))
asyncio.run(main())
