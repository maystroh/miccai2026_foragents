"""Concepts and datasets for each paper, without an LLM.

Concepts come from the paper's own keyword line and the MICCAI Body /
Applications / Machine Learning tags. Datasets are matched against the
hand-curated vocabulary in reports/miccai_brain/inputs/datasets.csv.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from .corpus import Paper, split_tags

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


TAG_KINDS = {"body", "application", "ml"}


def load_stoplist(root: Path) -> set[str]:
    """Generic building blocks (u-net, transformer, ...) that would link almost every paper."""
    path = root / INPUTS / "concept_stoplist.csv"
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as handle:
        return {r["concept"].strip().lower() for r in csv.DictReader(handle) if r.get("concept")}


def fold_key(concept: str) -> str:
    """Spelling-insensitive key: "Multi-modal LLMs" and "multimodal llm" fold together."""
    words = re.sub(r"[-\u2010-\u2015_/\s]+", " ", concept.lower()).split()
    words = [w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")) else w for w in words]
    return "".join(words)


def merge_variants(per_paper: dict[str, list[tuple[str, str]]]) -> dict[str, str]:
    """Map each spelling variant to the form most papers use (ties: shortest, then alphabetical)."""
    counts: dict[str, int] = {}
    for pairs in per_paper.values():
        for concept in {c for c, _ in pairs}:
            counts[concept] = counts.get(concept, 0) + 1
    groups: dict[str, list[str]] = {}
    for concept in counts:
        groups.setdefault(fold_key(concept), []).append(concept)
    mapping = {}
    for forms in groups.values():
        if len(forms) > 1:
            best = min(forms, key=lambda f: (-counts[f], len(f), f))
            mapping.update({f: best for f in forms if f != best})
    return mapping


def load_dataset_patterns(root: Path) -> list[tuple[str, re.Pattern]]:
    path = root / INPUTS / "datasets.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [(r["dataset"], re.compile(r["pattern"])) for r in csv.DictReader(handle)]


def paper_concepts(paper: Paper, aliases: dict[str, str]) -> list[tuple[str, str]]:
    """Return (concept, kind) pairs. kind: keyword | body | application | ml."""
    seen: dict[str, str] = {}
    # Tags first, so a keyword that repeats a tag ("brain") keeps the tag's kind.
    for term, kind in (
        [(b, "body") for b in split_tags(paper.body)]
        + [(a, "application") for a in paper.applications]
        + [(m, "ml") for m in paper.ml_tags]
        + [(k, "keyword") for k in paper.keywords]
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
