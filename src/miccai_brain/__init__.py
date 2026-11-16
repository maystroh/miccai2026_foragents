"""MICCAI brain: hybrid semantic search and topic graphs over MICCAI 2026 papers.

Inspired by github.com/garrytan/gbrain: one page per paper, BM25 + vector search
merged with reciprocal rank fusion, and a typed graph of papers, concepts and
datasets. Topics are the modality folders under Published_papers/.
"""

import os
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    """Load KEY=VALUE lines from .env into os.environ without overriding existing values."""
    path = Path(path)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        os.environ.setdefault(key, value.strip().strip("'\""))
