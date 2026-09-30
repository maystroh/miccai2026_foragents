#!/usr/bin/env python3
"""Plot reviewer acceptance counts against the primary AC's first decision.

Reviewer scores 4--6 are treated as accepting scores (Weak Accept, Accept,
and Strong Accept). Meta-review recommendations beginning with
The first recommendation in ``meta_review`` is used: ``Provisional Accept``
and ``Accept`` are primary-AC acceptance, while ``Invite for Rebuttal`` is a
rebuttal outcome. Later AC decisions in ``meta_final_decision`` are retained
in the summary but do not drive the plots. When the paper deduplication audit
exists, its retained modality is used for modality plots.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


REVIEWER_FIELDS = ["reviewer_1_rating", "reviewer_2_rating", "reviewer_3_rating"]
SCORE_RE = re.compile(r"^\s*\(([1-6])\)")
PRIMARY_META_RECOMMENDATION_RE = re.compile(
    r"Recommendation:\s*(Invite for Rebuttal|Provisional Accept|Early Accept|Early Reject|Reject|Accept)\b",
    re.IGNORECASE,
)


def reviewer_score(value: str) -> int | None:
    """Extract a numeric reviewer score from a rating field."""

    match = SCORE_RE.search(value or "")
    return int(match.group(1)) if match else None


def accepted_reviewer_count(row: dict[str, str]) -> int:
    """Return how many of the three reviewers gave an accepting score."""

    return sum((reviewer_score(row.get(field, "")) or 0) >= 4 for field in REVIEWER_FIELDS)


def primary_meta_decision(value: str) -> str:
    """Extract the primary AC's first decision from the meta-review text."""

    match = PRIMARY_META_RECOMMENDATION_RE.search(value or "")
    if not match:
        return "Other"
    recommendation = match.group(1).casefold()
    if recommendation in {"accept", "provisional accept", "early accept"}:
        return "Accept"
    if recommendation == "invite for rebuttal":
        return "Invite for Rebuttal"
    return "Other"


def primary_meta_accepts(value: str) -> bool:
    """Return whether the primary AC's first decision is an acceptance."""

    return primary_meta_decision(value) == "Accept"


def load_kept_modalities(dedup_map: Path | None) -> dict[str, str]:
    """Load retained paper modalities from the deduplication audit."""

    if dedup_map is None or not dedup_map.exists():
        return {}
    kept: dict[str, str] = {}
    with dedup_map.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("action", "").strip() == "kept":
                kept[row.get("paper_url", "").strip()] = row.get("kept_modality", "").strip()
    return kept


def load_review_rows(review_root: Path, dedup_map: Path | None = None) -> list[dict[str, str]]:
    """Load review rows, optionally selecting audit-retained modalities."""

    kept_modalities = load_kept_modalities(dedup_map)
    rows: list[dict[str, str]] = []
    for path in sorted(review_root.glob("*/reviews.csv")):
        modality = path.parent.name
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                paper_url = row.get("paper_url", "").strip()
                kept_modality = kept_modalities.get(paper_url)
                if kept_modality and modality != kept_modality:
                    continue
                row["modality"] = modality
                rows.append(row)
    return rows


def deduplicate_papers(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    """Keep one review row per paper URL, preserving deterministic order."""

    unique: dict[str, dict[str, str]] = {}
    for row in rows:
        paper_url = row.get("paper_url", "").strip()
        if paper_url and paper_url not in unique:
            unique[paper_url] = row
    return list(unique.values())


def acceptance_counts(rows: Iterable[dict[str, str]]) -> Counter[tuple[int, str]]:
    """Count papers by accepted-reviewer count and primary AC decision."""

    counts: Counter[tuple[int, str]] = Counter()
    for row in rows:
        counts[
            (accepted_reviewer_count(row), primary_meta_decision(row.get("meta_review", "")))
        ] += 1
    return counts


def write_summary(path: Path, rows: Iterable[dict[str, str]]) -> None:
    """Write one row per paper with the derived acceptance indicators."""

    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "modality",
        "title",
        "paper_url",
        "reviewer_accept_count",
        "primary_meta_decision",
        "meta_final_decision",
        "meta_review_rounds",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "modality": row.get("modality", ""),
                    "title": row.get("title", ""),
                    "paper_url": row.get("paper_url", ""),
                    "reviewer_accept_count": accepted_reviewer_count(row),
                    "primary_meta_decision": primary_meta_decision(row.get("meta_review", "")),
                    "meta_final_decision": row.get("meta_final_decision", ""),
                    "meta_review_rounds": row.get("meta_review_rounds", ""),
                }
            )


def plot_counts(path: Path, label: str, rows: list[dict[str, str]]) -> None:
    """Render a stacked bar chart for one modality or the combined set."""

    counts = acceptance_counts(rows)
    x = list(range(4))
    primary_accepts = [counts[(reviewer_count, "Accept")] for reviewer_count in x]
    primary_rebuttals = [counts[(reviewer_count, "Invite for Rebuttal")] for reviewer_count in x]
    primary_other = [counts[(reviewer_count, "Other")] for reviewer_count in x]

    figure, axis = plt.subplots(figsize=(8.5, 5.2))
    axis.bar(x, primary_accepts, label="Primary AC: Accept", color="#2a9d8f")
    axis.bar(
        x,
        primary_rebuttals,
        bottom=primary_accepts,
        label="Primary AC: Invite for Rebuttal",
        color="#e9c46a",
    )
    if any(primary_other):
        axis.bar(
            x,
            primary_other,
            bottom=[a + r for a, r in zip(primary_accepts, primary_rebuttals)],
            label="Primary AC: Other",
            color="#e76f51",
        )
    axis.set_xticks(x, [str(value) for value in x])
    axis.set_xlabel("Number of reviewers with an accepting score (4–6)")
    axis.set_ylabel("Number of papers")
    axis.set_title(f"Reviewer acceptance vs primary AC decision — {label}")
    axis.set_ylim(bottom=0)
    axis.grid(axis="y", alpha=0.25)
    axis.legend(frameon=False)
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "modality"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-root", type=Path, default=Path("Published_reviews"))
    parser.add_argument(
        "--dedup-map",
        type=Path,
        default=Path("Published_papers/deduplication_map.csv"),
        help="Audit map selecting each paper's retained modality; omit to include all rows",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("reports/review_acceptance"))
    args = parser.parse_args()

    rows = load_review_rows(args.review_root, args.dedup_map)
    if not rows:
        parser.error(f"no review CSV files found under {args.review_root}")

    by_modality: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_modality.setdefault(row["modality"], []).append(row)

    for modality, modality_rows in sorted(by_modality.items()):
        plot_counts(args.output_dir / f"{safe_filename(modality)}.png", modality, modality_rows)

    combined_rows = deduplicate_papers(sorted(rows, key=lambda row: (row.get("paper_url", ""), row["modality"])))
    plot_counts(args.output_dir / "all_papers.png", "all unique papers", combined_rows)
    write_summary(args.output_dir / "acceptance_summary.csv", combined_rows)

    print(f"wrote {len(by_modality)} modality charts and 1 combined chart to {args.output_dir}")
    print(f"combined papers: {len(combined_rows)} unique URLs ({len(rows)} retained modality rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
