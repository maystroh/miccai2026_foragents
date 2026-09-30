# Project Memory

## Scope

This project analyzes MICCAI 2026 medical-imaging papers, with classification
and segmentation of MRI volumes as the main focus and breast MRI as a priority
for deeper analysis. General findings should remain separate from breast-
specific synthesis.

## Current repository state

- `Published_papers/` contains the deduplicated paper index by modality.
- `Published_reviews/` contains review/acceptance records by modality.
- `Published_reviews/deduplication_map.csv` records review-row provenance after
  cross-modality deduplication.
- `deepbreath/` contains breast-imaging papers grouped into oral, poster, and
  unclassified tracks.
- `medagent/` contains medical-agent-related paper PDFs.
- `reports/review_acceptance/` contains acceptance summaries and generated
  modality plots.
- `Published_papers/deduplication_map.csv` is the audit trail for the latest
  cross-modality deduplication.

## Deduplication memory

The 18 paper modality CSVs originally contained 1,566 rows representing 1,161
unique `paper_url` values. They now contain one retained row per unique paper:
1,161 rows total, with 405 duplicate placements removed.

The retained copy is selected deterministically by alphabetical modality-folder
order, then original row order. The audit map records every original location,
the retained location, the title, URL, and action (`kept` or
`removed_duplicate`). Do not infer a paper's modality solely from its retained
folder; use the original locations in the audit map when reconstructing the
pre-deduplication classification.

The same policy is applied independently to `Published_reviews/`: its 1,566
original rows now contain 1,161 unique review rows, with 405 duplicate review
placements recorded in `Published_reviews/deduplication_map.csv`.

## Working rules

- Use stable `paper_url` values as the paper identity key.
- Preserve title, URL, authors, body, application, and machine-learning fields
  when moving or regenerating records.
- Keep provenance for claims using page, table, or figure references.
- Do not commit copyrighted PDFs, patient data, credentials, checkpoints,
  caches, or large datasets.
- When adding new papers, run a URL-based duplicate check across all modality
  indexes and update the audit map if a deduplication pass is performed.

## Folder resolver

For a compact machine-readable resolver, see
[`folder_resolver.csv`](folder_resolver.csv). It maps each important folder or
subfolder to its purpose and key files.

| Need | Start here |
|---|---|
| Unique paper index | `Published_papers/*/papers_links.csv` |
| Deduplication provenance | `Published_papers/deduplication_map.csv` |
| Review deduplication provenance | `Published_reviews/deduplication_map.csv` |
| Paper-index documentation and regeneration | `Published_papers/README.md` |
| Review/acceptance records | `Published_reviews/*/reviews.csv` |
| Breast MRI and breast-imaging papers | `deepbreath/orals/`, `deepbreath/posters/`, `deepbreath/unclassified/` |
| Medical-agent paper corpus | `medagent/` |
| Acceptance summaries and plots | `reports/review_acceptance/` |
| Repository conventions | `AGENTS.md` |
