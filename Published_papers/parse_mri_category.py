#!/usr/bin/env python3
"""Extract MICCAI 2026 MRI-category paper titles and links.

The category page contains many subject-area sections.  This parser only
collects paper links below the ``Modalities -> MRI`` heading, so it does not
accidentally include papers from other categories.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen


DEFAULT_URL = "https://papers.miccai.org/miccai-2026/categories/"
DEFAULT_CATEGORY = "Modalities -> MRI"
PAPER_LINK = re.compile(r"/miccai-2026/\d+-Paper\d+\.html(?:$|[?#])")


def normalize_text(value: str) -> str:
    return " ".join(value.split()).strip()


class CategoryParser(HTMLParser):
    """Collect paper anchors encountered inside one heading section."""

    def __init__(self, category: str) -> None:
        super().__init__(convert_charrefs=True)
        self.category = normalize_text(category).casefold()
        self.active_section_depth: int | None = None
        self.current_heading_depth: int | None = None
        self.heading_text: list[str] = []
        self.in_heading = False
        self.anchor_href: str | None = None
        self.anchor_text: list[str] = []
        self.rows: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.in_heading = True
            self.heading_text = []
            self.current_heading_depth = int(tag[1:])
        elif tag == "a":
            self.anchor_href = dict(attrs).get("href")
            self.anchor_text = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and self.in_heading:
            heading = normalize_text("".join(self.heading_text)).casefold()
            if heading == self.category:
                self.active_section_depth = int(tag[1:])
            elif (
                self.active_section_depth is not None
                and int(tag[1:]) <= self.active_section_depth
            ):
                self.active_section_depth = None
            self.current_heading_depth = None
            self.in_heading = False
        elif tag == "a" and self.anchor_href is not None:
            title = normalize_text("".join(self.anchor_text))
            if self.active_section_depth is not None and PAPER_LINK.search(self.anchor_href):
                self.rows.append((title, self.anchor_href))
            self.anchor_href = None
            self.anchor_text = []

    def handle_data(self, data: str) -> None:
        if self.in_heading:
            self.heading_text.append(data)
        if self.anchor_href is not None:
            self.anchor_text.append(data)


def read_source(source: str) -> tuple[str, str]:
    path = Path(source)
    if path.exists():
        return path.as_uri(), path.read_text(encoding="utf-8")

    request = Request(source, headers={"User-Agent": "miccai2026-mri-paper-index/1.0"})
    with urlopen(request, timeout=30) as response:  # noqa: S310 - explicit user source
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
    return source, raw.decode(charset, errors="replace")


def extract_rows(source: str, category: str) -> list[dict[str, str]]:
    source_url, html = read_source(source)
    parser = CategoryParser(category)
    parser.feed(html)

    deduplicated: dict[str, str] = {}
    for title, href in parser.rows:
        if title:
            deduplicated[title] = urljoin(source_url, href)

    return [
        {"title": title, "paper_url": url}
        for title, url in sorted(deduplicated.items(), key=lambda row: row[0].casefold())
    ]


def write_csv(rows: list[dict[str, str]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["title", "paper_url"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("--source", default=DEFAULT_URL, help="Category URL or saved HTML file")
    argument_parser.add_argument("--category", default=DEFAULT_CATEGORY)
    argument_parser.add_argument("--output", type=Path, default=Path("Published_papers/MRI/papers_links.csv"))
    args = argument_parser.parse_args()

    try:
        rows = extract_rows(args.source, args.category)
    except Exception as error:  # provide a useful CLI failure without a traceback
        print(f"error: could not parse {args.source}: {error}", file=sys.stderr)
        return 1
    if not rows:
        print(f"error: no paper links found below heading {args.category!r}", file=sys.stderr)
        return 1

    write_csv(rows, args.output)
    print(f"wrote {len(rows)} papers to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
