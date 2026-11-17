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
    ("Find", "find_papers_about", "Papers whose main subject matches (terms in title or abstract; | for synonyms).",
     "about, modality", "Which papers are really about breast MRI?", 'about "breast, MRI|magnetic resonance|DCE"'),
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
    ("Problems", "paper_claims", "The authors' own limitations or contributions, filtered by concept, topic, subject or words.",
     "kind, concept, modality, about, query", "What limitations do breast MRI papers admit?", "claims -c breast -m MRI"),
    ("Problems", "limitation_themes", "Recurring limitation themes with share of papers and examples.",
     "concept, modality", "What do MRI authors most often admit as limits?", "claims --themes -m MRI"),
    ("Problems", "reviewer_weaknesses", "What reviewers criticised, as themes with shares, quotes and the papers counted.",
     "about, concept, modality, paper_ids", "What do reviewers criticise in breast MRI papers?",
     'weaknesses --about "breast, MRI|magnetic resonance|DCE"'),
    ("Problems", "paper_reviews", "Compact reviewer weaknesses for a few papers (cheap way to read reviews).",
     "paper_ids, part, max_chars", "What exactly did reviewers say about 0378-Paper3872?", "reviews 0378-Paper3872"),
    ("Help", "brain_guide", "This guide.", "-", "What can the brain do?", "guide"),
]

WORKFLOWS = [
    ("Answer a question", "search_papers (2-3 phrasings) -> get_paper on the top hits -> answer citing paper_ids"),
    ("What reviewers say about a subject", "reviewer_weaknesses(about=...) -> paper_reviews on 2-3 of its papers to check"),
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
                  "For a subject (breast MRI, fetal ultrasound...) filter with about=, not concept=: tags also match general benchmarks.",
                  "Save tokens: summary tools first; open at most 3 papers with get_paper; read reviews with paper_reviews.",
                  "Outside-MICCAI novelty is never checked by these tools."],
    }


def guide_markdown(cli: bool = True) -> str:
    """cli=False leaves out the CLI column (shorter, for agents using the MCP tools)."""
    g = guide()
    lines = ["# MICCAI brain: tools at a glance", ""]
    group = None
    for t in g["tools"]:
        if t["group"] != group:
            group = t["group"]
            head = "| Tool | What it answers | Example |" + (" CLI |" if cli else "")
            lines += ["", f"## {group}", "", head, "|---|---|---|" + ("---|" if cli else "")]
        row = f"| `{t['tool']}` | {t['what']} | {t['example']} |"
        lines.append(row + (f" `{t['cli'].replace('python -m src.miccai_brain ', '')}` |" if cli else ""))
    lines += ["", "## Kinds you can ask about", ""] + [f"- **{k}**: {v}" for k, v in g["kinds"].items()]
    lines += ["", "## Typical sequences", ""] + [f"- **{w['goal']}**: {w['steps']}" for w in g["workflows"]]
    lines += ["", "## Also", ""] + [f"- `{e['name']}`: {e['what']}" for e in g["extras"]]
    lines += ["", "## Notes", ""] + [f"- {n}" for n in g["notes"]]
    return "\n".join(lines) + "\n"
