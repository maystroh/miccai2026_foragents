# Repository Guidelines

## Project Structure & Module Organization

This project analyzes MICCAI 2026 medical-imaging papers across modalities and organs. Keep public documentation neutral across research topics. Consult `docs/LOCAL_RESEARCH_INTERESTS.md`, when present, for local research priorities; never commit that file or publish its contents. Use this layout as the current empty scaffold grows:

- `papers/` for paper metadata, reading notes, and references to legally obtained PDFs.
- `data/` for structured extraction tables and controlled vocabularies.
- `src/` for ingestion, validation, analysis, and visualization code.
- `tests/` for automated tests mirroring `src/`.
- `reports/` for generated summaries, figures, and comparison tables.

Track each paper by a stable identifier. Capture task, anatomy, dataset, imaging modality and acquisition protocol, method, metrics, validation design, and code/data availability.

## Build, Test, and Development Commands

No build system exists yet. When adding tooling, provide one documented entry point, preferably a `Makefile`, with these targets:

- `make setup` — install dependencies and prepare local configuration.
- `make ingest` — validate and normalize paper metadata.
- `make test` — run the automated test suite.
- `make report` — regenerate tables, figures, and summaries.

Commands must be non-interactive and fail with a nonzero status for CI.

## Coding Style & Naming Conventions

Use four spaces for Python and two for YAML/JSON. Apply the configured formatter and linter. Use `snake_case` for Python files and functions, `PascalCase` for classes, and stable paper slugs such as `smith-2026-medical-segmentation`. Prefer controlled terms for tasks, modalities, and anatomy, and document vocabulary additions.

## Testing Guidelines

Test parsers, schema validation, deduplication, metric normalization, and report generation. Mirror source paths and name tests by behavior, for example `tests/test_metadata.py::test_rejects_missing_paper_id`. Use small, anonymized fixtures and avoid network-dependent tests. Spot-check generated tables against source papers.

## Commit & Pull Request Guidelines

Use imperative subjects such as `Add repository availability analysis`. Keep code, metadata, and reports separable. Pull requests should describe changed sources or analyses, list verification commands, and flag uncertain classifications or missing fields. Link paper identifiers and include sample outputs for visualization changes.

## Research Integrity & Data Handling

Record claims with page, table, or figure provenance. Distinguish reported results from derived comparisons; qualify metrics by dataset and evaluation design. Never commit copyrighted PDFs, patient data, credentials, large datasets, checkpoints, or caches. Document lawful retrieval and reproducible generation instead.
