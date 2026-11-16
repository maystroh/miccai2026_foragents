"""Concepts and datasets for each paper, without an LLM.

Concepts come from the paper's own keyword line and the MICCAI Body /
Applications / Machine Learning tags. Datasets are matched against the
hand-curated vocabulary in reports/miccai_brain/inputs/datasets.csv.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from .corpus import Paper

INPUTS = Path("reports/miccai_brain/inputs")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def normalize_concept(term: str, aliases: dict[str, str]) -> str:
    term = re.sub(r"\s+", " ", term.strip().lower().strip(".:;,"))
    return aliases.get(term, term)


def load_aliases(root: Path) -> dict[str, str]:
    path = root / INPUTS / "concept_aliases.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        return {r["alias"].strip().lower(): r["concept"].strip().lower() for r in csv.DictReader(handle)}


def load_dataset_patterns(root: Path) -> list[tuple[str, re.Pattern]]:
    path = root / INPUTS / "datasets.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [(r["dataset"], re.compile(r["pattern"])) for r in csv.DictReader(handle)]


def paper_concepts(paper: Paper, aliases: dict[str, str]) -> list[tuple[str, str]]:
    """Return (concept, kind) pairs. kind: keyword | body | application | ml."""
    seen: dict[str, str] = {}
    for term, kind in (
        [(k, "keyword") for k in paper.keywords]
        + [(paper.body, "body")]
        + [(a, "application") for a in paper.applications]
        + [(m, "ml") for m in paper.ml_tags]
    ):
        concept = normalize_concept(term, aliases) if term else ""
        if concept and len(concept) > 1 and concept not in seen:
            seen[concept] = kind
    return list(seen.items())


def paper_datasets(paper: Paper, patterns: list[tuple[str, re.Pattern]]) -> list[tuple[str, int]]:
    """Return (dataset, mention_count); requires a mention in the body text."""
    text = paper.abstract + "\n" + paper.markdown.split("## References")[0]
    hits = []
    for name, pattern in patterns:
        count = len(pattern.findall(text))
        if count:
            hits.append((name, count))
    return hits
