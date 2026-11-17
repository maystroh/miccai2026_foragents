"""One-page guide to every brain tool, shared by the MCP `brain_guide` tool, the CLI `guide`
command and the /brain-help slash command. Keep it in sync when a tool is added."""
from __future__ import annotations

KINDS = {
    "task": "what the paper does (e.g. lesion segmentation, report generation)",
    "method": "how it does it (e.g. diffusion model, contrastive learning); generic architectures excluded",
    "anatomy": "organ or structure (e.g. liver, prostate)",
    "metric": "evaluation metric (e.g. dice score, auc)",
    "dataset": "named dataset (e.g. BraTS, MIMIC-CXR)",
    "modality": "topic folder (e.g. MRI, CT-XRay, ultrasounds, Histology)",
    "keyword": "author keywords",
    "body / application / ml": "official MICCAI tags",
}

# (group, tool, what it answers, key arguments, example question, CLI equivalent)
TOOLS = [
    ("Find", "search_papers", "Papers matching a question (keyword + semantic). Falls back to keywords if the GPU server is down.",
     "query, modality, include_reviews, mode", "Which papers handle missing MRI sequences?",
     'search "missing MRI sequences" -m MRI'),
    ("Find", "get_paper", "Everything on one paper: abstract, concepts, datasets, contributions, limitations, reviews.",
     "paper_id", "What did 0920-Paper1730 do and what did reviewers say?", "paper 0920-Paper1730"),
    ("Find", "related_papers", "Most similar papers to one paper, with shared concepts.",
     "paper_id, modality", "What is closest to 0378-Paper3872?", "related 0378-Paper3872"),
    ("Find", "papers_with", "Papers tagged with a concept or using a dataset.",
     "concept_or_dataset, modality", "Which papers use MAMA-MIA?", 'concept "MAMA-MIA"'),
    ("Map", "list_topics", "All topics (modality folders) with paper counts.", "-", "What topics exist?", "topic"),
    ("Map", "topic_overview", "Top concepts, tags and datasets of one topic.", "modality", "What does ultrasound work focus on?",
     "topic ultrasounds"),
    ("Map", "vocabulary", "Most frequent names of one kind, with counts (also gives exact spellings).",
     "kind, modality", "Which methods dominate MRI?", "vocab method -m MRI"),
    ("Map", "neighbors", "What goes with X more than chance (lift).", "name, kind, other_kind, modality",
     "Which datasets go with diffusion models?", 'neighbors "diffusion model" -o dataset'),
    ("Map", "coverage_matrix", "Paper counts for every pair of two kinds; zeros are candidate gaps.",
     "row_kind, col_kind, modality, rows, cols", "Which methods are used in which topics?", "matrix method modality"),
    ("Gaps", "find_gaps", "Pairs that are each common, rarely combined, and semantically close.",
     "kind_a, kind_b, modality, min_papers, max_together, focus", "What method x topic combinations are missing?",
     "gaps method modality --min-papers 8"),
    ("Gaps", "bridge_papers", "Papers that combine A and B, and the closest one-sided papers (prior work).",
     "name_a, name_b", "Who is closest to combining report generation and ultrasound?",
     'bridge "radiology report generation" ultrasounds'),
    ("Problems", "paper_claims", "The authors' own limitations or contributions, filtered by concept, topic or words.",
     "kind, concept, modality, query", "What limitations do breast MRI papers admit?", "claims -c breast -m MRI"),
    ("Problems", "limitation_themes", "Recurring limitation themes with share of papers and examples.",
     "concept, modality", "What do MRI authors most often admit as limits?", "claims --themes -m MRI"),
    ("Problems", "reviewer_weaknesses", "What reviewers criticised for a topic or concept, with quotes.",
     "concept, modality", "What do reviewers attack in breast papers?", "weaknesses -c breast"),
    ("Help", "brain_guide", "This guide.", "-", "What can the brain do?", "guide"),
]

WORKFLOWS = [
    ("Answer a question", "search_papers (2-3 phrasings) -> get_paper on the top hits -> answer citing paper_ids"),
    ("Understand a topic", "topic_overview -> vocabulary (task, method, dataset) -> limitation_themes -> reviewer_weaknesses"),
    ("Find an idea", "find_gaps / coverage_matrix -> search_papers to check it is really missing -> bridge_papers for prior work"),
    ("Stress-test a plan", "reviewer_weaknesses for its topic -> /advisor <idea file>"),
]

EXTRAS = [
    ("/brain-help", "show this guide"),
    ("miccai-brain skill", "how to answer questions with citations"),
    ("miccai-ideas skill", "step-by-step idea hunt, saved in runs/<date>-<slug>/"),
    ("/advisor <idea file>", "adversarial MICCAI-style review by the miccai-advisor agent (Opus, high effort)"),
]


def guide() -> dict:
    return {
        "tools": [{"group": g, "tool": t, "what": w, "args": a, "example": e, "cli": f"python -m src.miccai_brain {c}"}
                  for g, t, w, a, e, c in TOOLS],
        "kinds": KINDS,
        "workflows": [{"goal": g, "steps": s} for g, s in WORKFLOWS],
        "extras": [{"name": n, "what": w} for n, w in EXTRAS],
        "notes": ["Every graph tool works offline; only semantic search needs the GPU server.",
                  "Counts come from Haiku extraction and tags: open a few papers before relying on a number.",
                  "Outside-MICCAI novelty is never checked by these tools."],
    }


def guide_markdown() -> str:
    g = guide()
    lines = ["# MICCAI brain: tools at a glance", ""]
    group = None
    for t in g["tools"]:
        if t["group"] != group:
            group = t["group"]
            lines += ["", f"## {group}", "", "| Tool | What it answers | Example | CLI |", "|---|---|---|---|"]
        lines.append(f"| `{t['tool']}` | {t['what']} | {t['example']} | `{t['cli'].replace('python -m src.miccai_brain ', '')}` |")
    lines += ["", "## Kinds you can ask about", ""] + [f"- **{k}**: {v}" for k, v in g["kinds"].items()]
    lines += ["", "## Typical sequences", ""] + [f"- **{w['goal']}**: {w['steps']}" for w in g["workflows"]]
    lines += ["", "## Also", ""] + [f"- `{e['name']}`: {e['what']}" for e in g["extras"]]
    lines += ["", "## Notes", ""] + [f"- {n}" for n in g["notes"]]
    return "\n".join(lines) + "\n"
