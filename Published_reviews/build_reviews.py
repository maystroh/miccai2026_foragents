#!/usr/bin/env python3
"""Fetch MICCAI review sections and create per-modality review CSVs."""

from __future__ import annotations

import argparse
import csv
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup, Tag


PAPER_ROOT = Path("Published_papers")
REVIEW_ROOT = Path("Published_reviews")
REVIEW_FIELDS = [
    "title", "paper_url",
    "reviewer_1_strengths", "reviewer_1_weaknesses", "reviewer_1_rating",
    "reviewer_2_strengths", "reviewer_2_weaknesses", "reviewer_2_rating",
    "reviewer_3_strengths", "reviewer_3_weaknesses", "reviewer_3_rating",
    "author_feedback", "meta_review", "meta_final_decision", "meta_review_rounds",
    "review_status", "error",
]


def text_of(node: Tag | None) -> str:
    if node is None:
        return ""
    return " ".join(node.get_text(" ", strip=True).split())


def section_items(heading: Tag, stop_tags: set[str]) -> list[Tag]:
    """Return top-level question list items until the next section heading."""
    items: list[Tag] = []
    for element in heading.next_elements:
        if isinstance(element, Tag) and element.name in stop_tags:
            break
        if isinstance(element, Tag) and element.name == "li" and element.find_parent("li") is None:
            items.append(element)
    return items


def review_items(heading: Tag) -> list[Tag]:
    return section_items(heading, {"h3"})


def response_for(items: list[Tag], phrase: str) -> str:
    phrase = phrase.casefold()
    for item in items:
        prompt = text_of(item.find("strong"))
        if phrase in prompt.casefold():
            return text_of(item.find("blockquote"))
    return ""


def parse_page(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    result: dict[str, str] = {}
    prompts = {
        "strengths": "major strengths of the paper",
        "weaknesses": "major weaknesses of the paper",
        "rating": "rate the paper on a scale of 1-6",
    }
    for index in range(1, 4):
        heading = soup.find("h3", id=f"review-{index}")
        items = review_items(heading) if heading else []
        for field, phrase in prompts.items():
            result[f"reviewer_{index}_{field}"] = response_for(items, phrase)

    author_heading = soup.find("h1", id="authorFeedback-id")
    if author_heading:
        result["author_feedback"] = text_of(author_heading.find_next("blockquote"))
    else:
        result["author_feedback"] = ""

    meta_heading = soup.find("h1", id="metareview-id")
    meta = []
    decisions: list[str] = []
    rounds = []
    if meta_heading:
        meta_headings = meta_heading.find_all_next("h2")
        for round_number, meta_heading_2 in enumerate(meta_headings, start=1):
            meta_items = section_items(meta_heading_2, {"h1", "h2"})
            initial_decisions: list[str] = []
            post_rebuttal_decisions: list[str] = []
            justifications: list[str] = []
            for item in meta_items:
                prompt = text_of(item.find("strong")).casefold()
                answer = text_of(item.find("blockquote"))
                if not answer:
                    continue
                if "after you have reviewed the rebuttal" in prompt and "justify" not in prompt:
                    post_rebuttal_decisions.append(answer)
                elif "your recommendation" in prompt and "justify" not in prompt:
                    initial_decisions.append(answer)
                if "please justify your recommendation" in prompt or "please justify your decision" in prompt:
                    justifications.append(answer)
            decisions.extend(initial_decisions)
            decisions.extend(post_rebuttal_decisions)
            parts = [f"Meta-review #{round_number}"]
            if initial_decisions:
                parts.append(f"Initial recommendation: {' | '.join(initial_decisions)}")
            if post_rebuttal_decisions:
                parts.append(f"Post-rebuttal recommendation: {' | '.join(post_rebuttal_decisions)}")
            if justifications:
                parts.append(f"Justification(s): {' | '.join(justifications)}")
            if initial_decisions or post_rebuttal_decisions or justifications:
                rounds.append(" ".join(parts))
        meta.extend(rounds)
    result["meta_review"] = " ".join(meta)
    result["meta_final_decision"] = decisions[-1] if decisions else ""
    result["meta_review_rounds"] = str(len(rounds))
    return result


def fetch_review(url: str, timeout: int = 45) -> dict[str, str]:
    request = Request(url, headers={"User-Agent": "miccai2026-review-inventory/1.0"})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - source URL is from the local paper index
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
    result = parse_page(raw.decode(charset, errors="replace"))
    result["review_status"] = "ok"
    result["error"] = ""
    return result


def collect_papers() -> dict[str, dict[str, str]]:
    papers: dict[str, dict[str, str]] = {}
    for csv_path in sorted(PAPER_ROOT.glob("*/papers_links.csv")):
        with csv_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                papers.setdefault(row["paper_url"], {"title": row["title"], "paper_url": row["paper_url"]})
    return papers


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper-root", type=Path, default=PAPER_ROOT)
    parser.add_argument("--review-root", type=Path, default=REVIEW_ROOT)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args()

    papers_by_url: dict[str, dict[str, str]] = {}
    for csv_path in sorted(args.paper_root.glob("*/papers_links.csv")):
        with csv_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                papers_by_url.setdefault(row["paper_url"], {"title": row["title"], "paper_url": row["paper_url"]})
    print(f"fetching reviews for {len(papers_by_url)} unique papers", file=sys.stderr)

    reviews: dict[str, dict[str, str]] = {}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(fetch_review, url, args.timeout): url for url in papers_by_url}
        for completed, future in enumerate(as_completed(futures), start=1):
            url = futures[future]
            row = dict(papers_by_url[url])
            try:
                row.update(future.result())
            except Exception as error:
                row.update({field: "" for field in REVIEW_FIELDS if field not in row})
                row["review_status"] = "error"
                row["error"] = str(error)
            reviews[url] = row
            if completed % 25 == 0 or completed == len(futures):
                print(f"fetched {completed}/{len(futures)}", file=sys.stderr)

    failures = 0
    for modality_csv in sorted(args.paper_root.glob("*/papers_links.csv")):
        modality = modality_csv.parent.name
        with modality_csv.open(encoding="utf-8", newline="") as handle:
            paper_rows = list(csv.DictReader(handle))
        output_rows = [reviews[row["paper_url"]] for row in paper_rows]
        output_dir = args.review_root / modality
        output_dir.mkdir(parents=True, exist_ok=True)
        with (output_dir / "reviews.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=REVIEW_FIELDS)
            writer.writeheader()
            writer.writerows(output_rows)
        modality_failures = sum(row["review_status"] != "ok" for row in output_rows)
        failures += modality_failures
        print(f"{modality}: {len(output_rows)} papers, {modality_failures} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
