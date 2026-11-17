---
name: miccai-ideas
description: Run a step-by-step research-idea hunt over the MICCAI 2026 brain with the user, saving every step in a run folder. Use when the user wants to find research directions, explore gaps, or turn the brain's findings into project plans. For a quick factual question use miccai-brain instead.
---

# MICCAI ideas: a step-by-step hunt with a saved trail

The goal is twice: good project ideas, and a written record of how they were reached (which questions
were asked, which tools answered them, what was dropped and why), so the user can see and refine their
own research process. Use the `miccai-brain` tools (see that skill for the tool list).

Work **one step at a time**. At the end of each step, write the step's file, show the user a short
summary and the decision they need to make, and wait. Do not run ahead to later steps.

## The run folder

`runs/<YYYY-MM-DD>-<slug>/`, created at step 1 from `references/templates.md`:

| File | Holds |
|---|---|
| `plan.md` | question, scope, constraints, focus, stopping rule |
| `log.md` | every step: the question asked, the tool call or query, what came back, the decision taken and why |
| `evidence-map.md` | each claim the run relies on: claim, paper_id + section or query, supports / contradicts |
| `ideas/<nn>-<slug>.md` | one file per surviving idea, from the idea template |
| `ideas/<nn>-<slug>.review.md` | the advisor's review |
| `decision-brief.md` | the shortlist the user agreed on, and what is still open |

`log.md` is the most important file: write it as you go, not at the end.

## Steps

Follow the token budget in the `miccai-brain` skill: summary tools first, at most 3 `get_paper` calls
per step, reviews through `paper_reviews`.


1. **Frame.** Ask the user, in one message: the area (topic, task, anatomy, or open), what they can do
   (data they have, compute, months available), what kind of contribution they want (method, benchmark,
   clinical study, dataset), and what would make an idea not worth it. Write `plan.md`. Stopping rule:
   at most 3 rounds of candidate generation unless the user says otherwise.
2. **Map the area.** Filter by subject with `about=` (see `find_papers_about`). `topic_overview`, `vocabulary` (tasks, methods, datasets), `limitation_themes`,
   `reviewer_weaknesses` for the area. Report what is crowded, what is thin, what authors and reviewers
   complain about. Ask the user what surprised them.
3. **Generate candidates** from four sources, at least two candidates per source when they exist:
   `find_gaps` / `coverage_matrix` (white space), `paper_claims` limitations (open problems authors name),
   `reviewer_weaknesses` (what reviewers keep asking for), and the user's own intuition from step 2.
   List them in a table with the evidence counts. The user picks which to examine.
4. **Check inside MICCAI.** For each picked candidate: `search_papers` in plain words (also with
   `include_reviews=true`) and `bridge_papers`. Drop it if a paper already does it or if it is a naming
   artefact. Record each drop and the reason in `log.md`.
5. **Write each survivor** as `ideas/<nn>-<slug>.md` with the idea template, including **how it could
   fail** (below). Every literature statement cites a paper_id.
6. **Advisor review.** Run `/advisor runs/<run>/ideas/<nn>-<slug>.md` for each idea (the
   `miccai-advisor` agent, Opus at high effort). Show the verdicts. The user decides which changes to
   accept; update the idea file and note the decision in `log.md`.
7. **Shortlist.** The user picks the ideas to pursue. Write `decision-brief.md`.

## How it could fail (in every idea file)

Before any experiment, write down three things in plain words:

- **The boring explanation:** the simplest reason the expected gain could appear without the idea being
  right (a stronger baseline, data leakage, an easier test set, more parameters).
- **The kill result:** the result that would make the team stop, fixed in advance. Example: "if
  zero-filling the missing sequences is within 1 AUC point of our method on the held-out cohort, drop it."
- **The untouched test:** which cohort or split stays unseen until the final evaluation.

## Outside-MICCAI novelty

Not checked during the hunt: the team cannot yet reach the literature APIs reliably. Every idea file
and the decision brief carry the line `Outside-MICCAI novelty: not checked (do before committing)`.
When the user agrees on a shortlist, remind them that this check is the first task for each idea.

## Rules

- Cite paper_ids for every statement about the literature; counts come from tools, never memory.
- Keep `docs/LOCAL_RESEARCH_INTERESTS.md` private: use it to suggest a focus, never copy it into a
  committed file. Run folders that reflect private interests stay uncommitted unless the user says so.
- Never run `build` or `extract` (long or paid) during a hunt.
