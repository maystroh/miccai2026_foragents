#!/usr/bin/env python3
"""Fetch MICCAI paper pages and build a sortable MRI-paper inventory."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


DEFAULT_INPUT = Path("Published_papers/MRI/papers_links.csv")
DEFAULT_OUTPUT = Path("Published_papers/MRI/papers_enriched.csv")
URL_RE = re.compile(r"https?://[^\s<>\"']+")


class PaperPageParser(HTMLParser):
    """Extract text and links from the stable sections of a MICCAI page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.section: str | None = None
        self.heading_id: str | None = None
        self.text: dict[str, list[str]] = {"abstract": [], "links": [], "code": []}
        self.links: dict[str, list[str]] = {"links": [], "code": []}
        self.topics: dict[str, list[str]] = {"Body": [], "Applications": [], "Machine Learning": []}
        self.in_anchor = False
        self.anchor_href: str | None = None
        self.in_topic_anchor = False
        self.topic_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag.lower() in {"h1", "h2", "h3"}:
            self.heading_id = attributes.get("id")
            self.section = {
                "abstract-id": "abstract",
                "link-id": "links",
                "code-id": "code",
            }.get(self.heading_id)
        elif tag.lower() == "a":
            self.in_anchor = True
            self.anchor_href = attributes.get("href")
            self.in_topic_anchor = "post-category" in (attributes.get("class") or "").split()
            self.topic_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a":
            if self.in_topic_anchor:
                topic = " ".join("".join(self.topic_text).split())
                group, separator, value = topic.partition(" -> ")
                if separator and group in self.topics and value and value not in self.topics[group]:
                    self.topics[group].append(value)
            self.in_anchor = False
            self.anchor_href = None
            self.in_topic_anchor = False
            self.topic_text = []

    def handle_data(self, data: str) -> None:
        if self.section in self.text:
            self.text[self.section].append(data)
        if self.in_anchor and self.section in self.links and self.anchor_href:
            self.links[self.section].append(self.anchor_href)
        if self.in_topic_anchor:
            self.topic_text.append(data)

    def result(self) -> dict[str, str]:
        abstract = " ".join(" ".join(self.text["abstract"]).split())
        abstract = re.sub(r"^Abstract\s*", "", abstract, flags=re.IGNORECASE)
        all_links = self.links["links"]
        pdf_url = next((url for url in all_links if ".pdf" in url.lower()), "")
        code_url = next(
            (
                url
                for url in self.links["code"]
                if not any(host in url.lower() for host in ("miccai.org", "springer.com"))
            ),
        "")
        return {
            "abstract": abstract,
            "pdf_url": pdf_url,
            "code_url": code_url,
            "Body": "; ".join(self.topics["Body"]),
            "Applications": "; ".join(self.topics["Applications"]),
            "Machine Learning": "; ".join(self.topics["Machine Learning"]),
        }


def fetch_page(url: str, timeout: int) -> dict[str, str]:
    request = Request(url, headers={"User-Agent": "miccai2026-mri-paper-inventory/1.0"})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - URL comes from the input CSV
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
    html = raw.decode(charset, errors="replace")
    parser = PaperPageParser()
    parser.feed(html)
    result = parser.result()
    authors = []
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.select("div.post-tags a.post-category"):
        author = " ".join(link.get_text(" ", strip=True).split())
        if author and author not in authors:
            authors.append(author)
    result["authors"] = " | ".join(authors)
    if not result["abstract"]:
        raise ValueError("abstract section not found")
    return result


def classify(title: str, abstract: str) -> str:
    text = f"{title} {abstract}".casefold()
    if re.search(r"\b(agent|agentic|multi-agent)\b", text):
        return "Agent"
    if re.search(r"\b(vlm|vision.language|vision–language|multimodal large language|medical mllm|medical vqa)\b", text):
        return "VLM"
    has_segmentation = bool(re.search(r"\b(segment|segmentation|parcellation|delineation)\b", text))
    has_classification = bool(re.search(r"\b(classif|diagnos|prediction|prognos|grading)\w*\b", text))
    if has_segmentation and has_classification:
        return "classification&segmentation"
    if has_segmentation:
        return "segmentation"
    if re.search(r"\b(synthes|generation|translation|diffusion|generat|digital phantom)\w*\b", text):
        return "image synthesis"
    if has_classification:
        return "classification"
    for label, pattern in (
        ("reconstruction", r"reconstruct|reconstruction|unrolling|inverse problem"),
        ("registration", r"registration|registrat|deformable alignment"),
        ("image restoration/quality", r"artifact|quality assessment|restoration|harmonization|motion correction"),
        ("detection/localization", r"\bdetection\b|localization|landmark"),
        ("report generation", r"report generation|radiology reporting"),
        ("dataset/benchmark", r"dataset|benchmark"),
    ):
        if re.search(pattern, text):
            return label
    return "other"


def organ(title: str, abstract: str) -> str:
    text = f"{title} {abstract}".casefold()
    rules = (
        ("breast", r"\bbreast\b|dce.mri|her2|pcr prediction"),
        ("brain", r"\bbrain\b|cerebr|cortical|cortex|alzheimer|epilep|glioma|stroke|multiple sclerosis|hippocamp|cerebrovascular|f\.mri|fmri"),
        ("cardiac/heart", r"cardiac|\bheart\b|myocard|cine.mri|cardiovascular|coronary"),
        ("prostate", r"prostat"),
        ("spine", r"\bspine\b|spinal|vertebr|intervertebral"),
        ("liver", r"\bliver\b|hepatocellular"),
        ("kidney/renal", r"kidney|renal|adpkd|polycystic"),
        ("pancreas", r"pancrea"),
        ("knee", r"\bknee\b|femoral|meniscus"),
        ("pelvis/gynecologic", r"pelvic|uter|gynecolog|ovarian|prostate"),
        ("head and neck", r"head.and.neck|nasopharyn|tmj|vocal tract|cervical"),
        ("vasculature", r"vessel|vascular|aneurysm|arter|mra|\btof.mra\b"),
        ("lung/thorax", r"lung|pulmon|thorac"),
        ("fetal/neonatal", r"fetal|foetal|neonat|newborn"),
        ("whole-body/multi-organ", r"whole.body|multi.organ|multi-organ"),
    )
    for label, pattern in rules:
        if re.search(pattern, text):
            return label
    return "unspecified"


def enrich(row: dict[str, str], timeout: int) -> dict[str, str]:
    result = dict(row)
    try:
        result.update(fetch_page(row["paper_url"], timeout))
        result["category"] = classify(row["title"], result["abstract"])
        result["organ"] = organ(row["title"], result["abstract"])
        result["status"] = "ok"
        result["error"] = ""
    except Exception as error:  # keep one failed page from losing the full inventory
        result.update({"abstract": "", "pdf_url": "", "code_url": "", "category": "", "organ": "", "Body": "", "Applications": "", "Machine Learning": "", "authors": ""})
        result["status"] = "error"
        result["error"] = str(error)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    with args.input.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    enriched: list[dict[str, str] | None] = [None] * len(rows)
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(enrich, row, args.timeout): index for index, row in enumerate(rows)}
        for completed, future in enumerate(as_completed(futures), start=1):
            index = futures[future]
            enriched[index] = future.result()
            print(f"[{completed}/{len(rows)}] {rows[index]['title']}", file=sys.stderr)

    fields = ["title", "paper_url", "pdf_url", "code_url", "organ", "category", "Body", "Applications", "Machine Learning", "authors", "abstract", "status", "error"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(enriched)  # type: ignore[arg-type]
    failures = sum(row["status"] != "ok" for row in enriched if row)
    print(f"wrote {len(rows)} rows to {args.output}; failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
