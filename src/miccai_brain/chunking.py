"""Turn a paper's markdown into searchable chunks."""
from __future__ import annotations

import re

COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
TAG_RE = re.compile(r"</?(sup|sub|span|br)[^>]*>")
REFS_RE = re.compile(r"^#{1,4}\s*\**\s*(references|bibliography)\b", re.IGNORECASE | re.MULTILINE)
HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)$", re.MULTILINE)
WATERMARK = "This MICCAI paper is the Open Access version"


def clean_markdown(markdown: str) -> str:
    text = COMMENT_RE.sub("", markdown)
    refs = REFS_RE.search(text)
    if refs:
        text = text[: refs.start()]
    text = TAG_RE.sub("", text)
    lines = [ln for ln in text.splitlines() if WATERMARK not in ln and not ln.startswith("![")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def split_sections(text: str) -> list[tuple[str, str]]:
    sections, last, heading = [], 0, "Front matter"
    for match in HEADING_RE.finditer(text):
        body = text[last : match.start()].strip()
        if body:
            sections.append((heading, body))
        heading = match.group(2).strip("* ")
        last = match.end()
    tail = text[last:].strip()
    if tail:
        sections.append((heading, tail))
    return sections


def window(text: str, max_chars: int, overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    paras, out, cur = text.split("\n\n"), [], ""
    for para in paras:
        while len(para) > max_chars:
            head, para = para[:max_chars], para[max_chars - overlap :]
            if cur:
                out.append(cur)
                cur = ""
            out.append(head)
        if len(cur) + len(para) + 2 > max_chars and cur:
            out.append(cur)
            cur = cur[-overlap:] + "\n\n" + para if overlap else para
        else:
            cur = f"{cur}\n\n{para}" if cur else para
    if cur:
        out.append(cur)
    return out


def chunk_paper(markdown: str, max_chars: int = 1800, overlap: int = 200) -> list[tuple[str, str]]:
    """Return (section, text) chunks; small sections are merged forward."""
    chunks: list[tuple[str, str]] = []
    pending_heading, pending = "", ""
    for heading, body in split_sections(clean_markdown(markdown)):
        piece = f"{heading}\n{body}"
        if len(pending) + len(piece) < max_chars // 2:
            pending_heading = pending_heading or heading
            pending = f"{pending}\n\n{piece}" if pending else piece
            continue
        if pending:
            piece = f"{pending}\n\n{piece}"
            heading = pending_heading
            pending_heading, pending = "", ""
        chunks.extend((heading, part) for part in window(piece, max_chars, overlap))
    if pending:
        chunks.append((pending_heading, pending))
    return chunks
