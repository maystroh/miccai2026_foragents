#!/usr/bin/env python3
"""Build per-modality paper indexes and enriched inventories from MICCAI 2026."""

from __future__ import annotations

import argparse
import csv
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin

try:
    from .enrich_mri_papers import enrich
    from .parse_mri_category import CategoryParser, DEFAULT_URL, read_source
except ImportError:  # support `python MRI_papers/build_modalities.py`
    from enrich_mri_papers import enrich
    from parse_mri_category import CategoryParser, DEFAULT_URL, read_source


MODALITIES = {
    "MRI": "Modalities -> MRI",
    "CT-XRay": "Modalities -> CT / X-ray",
    "Diffusion-MRI": "Modalities -> Diffusion MRI",
    "Histology": "Modalities -> Digital Pathology/Histopathology",
    "Physio-signals": "Modalities -> EEG / MEG / ECG / Physiological Signals",
    "EHR": "Modalities -> Electronic Health Records",
    "Endoscopy": "Modalities -> Endoscopy",
    "Func_MRI": "Modalities -> Functional MRI",
    "Microscopy": "Modalities -> Microscopy",
    "Sensors": "Modalities -> Mobile / Wearable / Point-of-Care Imaging & Sensors",
    "Multimodals": "Modalities -> Multimodal Sensor Fusion",
    "PET_SPECT": "Modalities -> Nuclear Imaging / PET / SPECT",
    "Others": "Modalities -> Other",
    "Photo_video": "Modalities -> Photograph / Video",
    "Robotics": "Modalities -> Robotics / Intraoperative Imaging",
    "Spectroscopy": "Modalities -> Spectroscopy",
    "Computational_imagings": "Modalities -> Synthetic / Computational Imaging",
    "ultrasounds": "Modalities -> Ultrasound",
}


def extract_modality_rows(html: str, source_url: str, heading: str) -> list[dict[str, str]]:
    parser = CategoryParser(heading)
    parser.feed(html)
    rows: dict[str, dict[str, str]] = {}
    for title, href in parser.rows:
        if title:
            rows[title] = {"title": title, "paper_url": urljoin(source_url, href)}
    return sorted(rows.values(), key=lambda row: row["title"].casefold())


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["title", "paper_url"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=Path("Published_papers"))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--source", default=DEFAULT_URL, help="Category URL or saved HTML file")
    args = parser.parse_args()

    source_url, html = read_source(args.source)
    # A saved category page has a file:// source URL, but its relative links
    # still refer to the official MICCAI site.
    if Path(args.source).exists():
        source_url = DEFAULT_URL
    raw_by_modality = {
        name: extract_modality_rows(html, source_url, heading)
        for name, heading in MODALITIES.items()
    }
    all_rows = {row["paper_url"]: row for rows in raw_by_modality.values() for row in rows}
    print(
        f"found {len(all_rows)} unique paper pages across "
        f"{len(raw_by_modality)} modalities",
        file=sys.stderr,
    )

    enriched_by_url: dict[str, dict[str, str]] = {}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {
            pool.submit(enrich, row, args.timeout): url
            for url, row in all_rows.items()
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            url = futures[future]
            enriched_by_url[url] = future.result()
            if completed % 25 == 0 or completed == len(futures):
                print(f"enriched {completed}/{len(futures)}", file=sys.stderr)

    for name, rows in raw_by_modality.items():
        directory = args.output_root / name
        enriched_rows = [enriched_by_url[row["paper_url"]] for row in rows]
        fields = [
            "title", "paper_url", "pdf_url", "code_url", "category", "Body",
            "Applications", "Machine Learning", "authors", "abstract", "status", "error",
        ]
        index_rows = [
            {
                "title": row["title"],
                "paper_url": row["paper_url"],
                "pdf_url": row["pdf_url"],
                "code_url": row["code_url"],
                "category": row["category"],
                "Body": row["Body"],
                "Applications": row["Applications"],
                "Machine Learning": row["Machine Learning"],
                "authors": row["authors"],
                "abstract": row["abstract"],
                "status": row["status"],
                "error": row["error"],
            }
            for row in enriched_rows
        ]
        with (directory / "papers_links.csv").open("w", encoding="utf-8", newline="") as handle:
            link_fields = fields
            writer = csv.DictWriter(handle, fieldnames=link_fields)
            writer.writeheader()
            writer.writerows(index_rows)
        failures = sum(row["status"] != "ok" for row in enriched_rows)
        print(f"{name}: {len(rows)} papers, {failures} failures")
    return 1 if any(row["status"] != "ok" for row in enriched_by_url.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
