---
name: miccai-brain
description: Answer research questions and find research ideas from the MICCAI 2026 brain (all accepted papers, reviews, and a concept/dataset graph). Use when asked what MICCAI 2026 papers did on a topic, which methods or datasets are used where, what is under-explored, or to propose and plan projects grounded in those papers.
---

# MICCAI brain: answers, gaps and project plans

The brain is `reports/miccai_brain/brain.sqlite`, built by `python -m src.miccai_brain build`.
Use the `miccai-brain` MCP tools when they are connected (the repo's `.mcp.json` registers them);
Call `brain_guide` (or `/brain-help`) for the full list with examples;
otherwise run the same queries with the CLI from the repo root, which prints JSON:

| Need | MCP tool | CLI |
|---|---|---|
| Find papers on a question | `search_papers` | `search "<query>" [-m MRI] [--reviews] [--mode keyword]` |
| Read one paper (+ contributions, limitations) | `get_paper` | `paper <id>` |
| Papers whose main subject is X (title/abstract) | `find_papers_about` | `about "breast, MRI\|DCE"` |
| What reviewers said about a few papers (weaknesses only) | `paper_reviews` | `reviews <id> <id>` |
| Exact spellings / most common names of a kind | `vocabulary` | `vocab <kind> [-m MRI]` |
| What goes with X (lift) | `neighbors` | `neighbors "<name>" [-k kind] [-o other_kind] [-m MRI]` |
| Coverage grid between two kinds | `coverage_matrix` | `matrix <row_kind> <col_kind> [-m MRI] [--rows ..] [--cols ..]` |
| White-space pairs | `find_gaps` | `gaps <kind_a> <kind_b> [-m MRI] [--focus text]` |
| Prior work for combining A and B | `bridge_papers` | `bridge "<A>" "<B>"` |
| Authors' own limitations / contributions | `paper_claims`, `limitation_themes` | `claims [-c concept] [-m MRI] [-q words] [--themes]` |
| What reviewers criticised for a subject, topic or concept | `reviewer_weaknesses` | `weaknesses [--about ..] [-c concept] [-m MRI]` |
| Topics, topic overview, papers with a tag, similar papers | `list_topics`, `topic_overview`, `papers_with`, `related_papers` | `topic`, `concept`, `related` |

Kinds: `task`, `method`, `anatomy`, `metric`, `keyword`, `dataset`, `modality` (topic folder such as
MRI, CT, Pathology), and the MICCAI tags `body`, `application`, `ml`. Generic architectures (U-Net,
ViT, transformer, ...) are deliberately not concepts.

Semantic search needs the query embedder (the GPU server in `.env`). If it is unreachable, hybrid
search falls back to keywords and returns a warning; every graph tool works without it.

## Token budget

The brain can return a lot of text, so query it cheaply:

- Use the summary tools first (`topic_overview`, `vocabulary`, `limitation_themes`, `reviewer_weaknesses`);
  they already count and quote across many papers.
- For a subject (breast MRI, fetal ultrasound, ...) filter with `about=` (comma = AND, `|` = synonyms),
  not `concept=`: concept tags also match benchmarks that include one dataset of that kind.
- Open at most 3 papers with `get_paper`, and read reviews with `paper_reviews` (weaknesses only),
  never `get_paper(include_reviews=true)` for several papers.
- Keep `limit`/`top` small (10 to 20) unless you need the full list.

## Answering a question

1. Search with two or three phrasings, scoped by `modality` when the question names one.
2. Open the top papers with `get_paper` before you state anything about them.
3. Answer with citations: `[paper_id] Title`, and say how many papers support each statement.
   Distinguish what a paper reports from your synthesis. Say when the brain has nothing on it.

## Finding ideas

For a full, step-by-step hunt with a saved trail, use the `miccai-ideas` skill. The short version:

Work in this order and keep notes of every query you run:

1. **Map the area.** `topic_overview` and `vocabulary` for the requested topic (or the whole corpus).
2. **Generate candidates from four sources:**
   - `find_gaps` on pairs such as method x anatomy, method x modality, task x modality,
     dataset x method. Prefer high `semantic_closeness` and high `expected`: both sides are busy and
     related, yet nobody combined them.
   - `coverage_matrix` for the same pairs, to see the zero cells in context.
   - `limitation_themes` and `paper_claims` (limitations) for the area: problems the authors
     themselves left open, repeated across many papers.
   - Reviews (`reviewer_weaknesses` for the area, `paper_reviews` for a few papers) for what reviewers keep asking for.
3. **Kill weak candidates.** For each one: `search_papers` for the combination in plain words (and
   with `include_reviews`), and `bridge_papers` to see who is closest. Drop it if a paper already does
   it, if the pair is only an artefact of naming, or if there is no public dataset to test it on
   (check `neighbors(..., other_kind="dataset")`).
4. **Write up each surviving idea** with this template:
   - **Idea** in one sentence, and why now.
   - **Evidence of the gap:** the counts (A in n papers, B in m, together k; expected e), and the
     limitations or review comments that ask for it, each cited.
   - **Closest prior work:** 3 to 5 papers from `bridge_papers` and what each lacks.
   - **Plan:** data (public datasets the brain shows for this setting), baselines (what the
     closest papers report), method sketch, evaluation (metrics the field uses here, external
     validation), risks, and a first two-week milestone.
   - **Confidence:** high, medium or low, and what would change it.
5. Rank ideas by evidence strength and feasibility, not novelty alone. A gap the data cannot test is
   not an idea yet.

## Rules

- Every factual statement about the literature cites a paper id from the brain.
- The brain covers MICCAI 2026 only: an absent combination may exist elsewhere. Say so.
- Counts come from LLM extraction and keyword tags, so spot-check any count you rely on by opening
  a few of the papers.
- Never run `extract` or `build` (paid or long) without the user asking for it.
- Keep `docs/LOCAL_RESEARCH_INTERESTS.md` private: you may use it to choose a focus, but never quote
  it or its focus in anything committed or shared.
