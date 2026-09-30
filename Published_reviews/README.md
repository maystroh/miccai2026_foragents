# MICCAI 2026 paper reviews

`Published_reviews/` mirrors the modality folders in `Published_papers/`.
Each modality contains `reviews.csv`, with one row per paper and these review
fields:

- Reviewer 1–3 strengths, weaknesses, and rating
- Author feedback
- Complete meta-review history, including all numbered rounds and
  pre-/post-rebuttal recommendations
- Final meta-review decision
- Number of meta-review rounds

Generate or refresh the files with:

```bash
python -m Published_reviews.build_reviews
```

The command fetches HTML review pages only; it does not download PDFs.

## Cross-modality deduplication

The 18 review CSVs are kept one row per unique `paper_url`, matching the
deduplicated paper indexes. The retained review copy is selected
deterministically from the alphabetically first modality folder, then by
original row order. The complete source-to-retained mapping is recorded in
[`deduplication_map.csv`](deduplication_map.csv), including rows that were
already unique.

The current review set contains 1,161 unique review rows. The audit map records
the 405 duplicate placements removed from the original 1,566 rows. If the
review files are regenerated with `build_reviews`, rerun the same deduplication
policy and preserve the audit map.

## Acceptance plots

Create one PNG per modality, a combined chart, and a CSV containing the
derived acceptance indicators:

```bash
python -m Published_reviews.plot_acceptance
```

Outputs are written to `reports/review_acceptance/`. Reviewer scores 4--6 are
counted as accepting. The plots use the first recommendation in `meta_review`
from the primary AC: `Provisional Accept`/`Accept` become `Accept`, while
`Invite for Rebuttal` remains a separate outcome. `meta_final_decision` and
`meta_review_rounds` are retained in the summary CSV for context but do not
drive the plots. The deduplication audit selects each paper's retained
modality. Use `--dedup-map /path/that/does/not/exist` to include every review
row instead.
