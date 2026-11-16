"""Read papers, modality membership and reviews from the local folder layout."""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

PAPER_ID_RE = re.compile(r"(\d{4}-Paper\d+)")
SKIP_DIRS = {"__pycache__"}


@dataclass
class Review:
    role: str  # reviewer_1..3, author_feedback, meta_review
    text: str
    rating: str = ""


@dataclass
class Paper:
    paper_id: str  # e.g. 0002-Paper5533
    title: str
    paper_url: str
    pdf_url: str = ""
    code_url: str = ""
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    body: str = ""  # Body tag (anatomy)
    applications: list[str] = field(default_factory=list)
    ml_tags: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    modalities: list[str] = field(default_factory=list)
    markdown: str = ""
    folder: str = ""
    decision: str = ""
    reviews: list[Review] = field(default_factory=list)


def paper_id_from_url(url: str) -> str:
    match = PAPER_ID_RE.search(url or "")
    return match.group(1) if match else ""


def split_tags(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[;|]", value or "") if part.strip()]


KEYWORDS_RE = re.compile(r"^(?:#+\s*)?[*_]{0,2}\s*Key ?words?\s*[:.]?\s*[*_]{0,2}\s*[:.]?\s*(.+)", re.IGNORECASE)


def extract_keywords(markdown: str) -> list[str]:
    for line in markdown.splitlines()[:150]:
        match = KEYWORDS_RE.match(line.strip())
        if match:
            raw = re.sub(r"<[^>]+>|\*", "", match.group(1))
            parts = re.split(r"\s*[·•;,]\s*|\s+-\s+", raw)
            return [p.strip(" .") for p in parts if 1 < len(p.strip(" .")) < 80]
    return []


def modality_map(root: Path) -> dict[str, list[str]]:
    """paper_id -> every modality folder that lists it (kept and duplicates)."""
    mapping: dict[str, list[str]] = {}
    dedup = root / "Published_papers" / "deduplication_map.csv"
    if dedup.exists():
        with dedup.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                pid = paper_id_from_url(row["paper_url"])
                mods = mapping.setdefault(pid, [])
                for mod in (row.get("kept_modality", ""), row.get("source_modality", "")):
                    if mod and mod not in mods:
                        mods.append(mod)
    return mapping


def load_reviews(root: Path) -> dict[str, tuple[str, list[Review]]]:
    out: dict[str, tuple[str, list[Review]]] = {}
    base = root / "Published_reviews"
    if not base.exists():
        return out
    csv.field_size_limit(10**8)
    for path in sorted(base.glob("*/reviews.csv")):
        with path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                pid = paper_id_from_url(row.get("paper_url", ""))
                if not pid or pid in out:
                    continue
                reviews = []
                for i in range(1, 6):
                    key = f"reviewer_{i}"
                    strengths = row.get(f"{key}_strengths", "") or ""
                    weaknesses = row.get(f"{key}_weaknesses", "") or ""
                    if strengths or weaknesses:
                        text = f"Strengths: {strengths}\n\nWeaknesses: {weaknesses}".strip()
                        reviews.append(Review(key, text, row.get(f"{key}_rating", "") or ""))
                for key in ("author_feedback", "meta_review"):
                    if (row.get(key) or "").strip():
                        reviews.append(Review(key, row[key].strip()))
                out[pid] = (row.get("meta_final_decision", "") or "", reviews)
    return out


def iter_paper_dirs(root: Path):
    base = root / "Published_papers"
    for modality_dir in sorted(p for p in base.iterdir() if p.is_dir() and p.name not in SKIP_DIRS):
        for paper_dir in sorted(modality_dir.iterdir()):
            if paper_dir.is_dir() and PAPER_ID_RE.fullmatch(paper_dir.name):
                yield modality_dir.name, paper_dir


def load_papers(root: Path, modalities: list[str] | None = None) -> list[Paper]:
    root = Path(root)
    mod_map = modality_map(root)
    reviews = load_reviews(root)
    papers: dict[str, Paper] = {}
    for modality, paper_dir in iter_paper_dirs(root):
        meta_path = paper_dir / "metadata.json"
        if not meta_path.exists():
            continue
        pid = paper_dir.name
        if pid in papers:
            if modality not in papers[pid].modalities:
                papers[pid].modalities.append(modality)
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8")).get("paper", {})
        md_path = paper_dir / "paper.md"
        markdown = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
        mods = list(mod_map.get(pid, []))
        if modality not in mods:
            mods.insert(0, modality)
        decision, paper_reviews = reviews.get(pid, ("", []))
        papers[pid] = Paper(
            paper_id=pid,
            title=meta.get("title", "").strip(),
            paper_url=meta.get("paper_url", ""),
            pdf_url=meta.get("pdf_url", ""),
            code_url=meta.get("code_url", ""),
            authors=split_tags(meta.get("authors", "")),
            abstract=meta.get("abstract", "").strip(),
            body=meta.get("Body", "").strip(),
            applications=split_tags(meta.get("Applications", "")),
            ml_tags=split_tags(meta.get("Machine Learning", "")),
            keywords=extract_keywords(markdown),
            modalities=mods,
            markdown=markdown,
            folder=str(paper_dir.relative_to(root)),
            decision=decision,
            reviews=paper_reviews,
        )
    result = list(papers.values())
    if modalities:
        wanted = set(modalities)
        result = [p for p in result if wanted & set(p.modalities)]
    return result
