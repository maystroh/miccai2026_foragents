# MICCAI 2026 MRI papers

`Published_papers/MRI/papers_links.csv` is the title-to-paper-page index. The paper page URL is the
stable HTML page on the MICCAI open-access site, for example:

```text
3D Classification of Paramagnetic Rim Lesions in Multiple Sclerosis via Asymmetric QSM–FLAIR Modeling,https://papers.miccai.org/miccai-2026/0002-Paper5533.html
```

Regenerate the CSV from the official category page with:

```bash
python -m Published_papers.parse_mri_category
```

The metadata script can enrich an index with abstracts, PDF URLs, code URLs,
organ labels, and task categories:

```bash
python -m Published_papers.enrich_mri_papers
```

Categories are assigned from title/abstract keywords and include the requested
labels plus
`reconstruction`, `registration`, `image restoration/quality`,
`detection/localization`, `report generation`, `dataset/benchmark`, and
`other`. Keep the abstract and `status` columns for audit and manual review.

Build the same pair of CSV files for all requested modalities with:

```bash
python -m Published_papers.build_modalities
```

This creates folders such as `Published_papers/CT-XRay/` and
`Published_papers/Func_MRI/`. Each contains `papers_links.csv` as the primary
queryable index with title, modality, paper-page URL, PDF URL, code-repository
URL, abstract, task category, normalized `Body`, `Applications`, and `Machine
Learning` topic columns, plus the pipe-separated `authors` field.
No PDFs are downloaded. Shared paper pages are fetched once and reused across
modality folders.

For reproducible offline parsing, pass a saved copy of the page:

```bash
python -m Published_papers.parse_mri_category \
  --source /path/to/categories.html \
  --output Published_papers/MRI/papers_links.csv
```

The parser scopes extraction to `Modalities -> MRI`, deduplicates titles, and
sorts the output by title. The current CSV was seeded from the repository's
existing MRI manifest because this environment cannot resolve the source host;
regenerating it from the category page is the authoritative update path.

## Cross-modality deduplication

The modality CSVs contain one retained row per unique `paper_url`. When a paper
was present in multiple modality folders, the retained copy was selected
deterministically from the alphabetically first modality folder, then by its
original row order. The complete source-to-retained mapping is recorded in
[`deduplication_map.csv`](deduplication_map.csv), including papers that were
already unique.

Each audit row records the original modality/file/row, the retained
modality/file/row, and whether the source row was kept or removed as a
duplicate. Re-running the same policy over the original source CSVs reproduces
the same retained locations.
