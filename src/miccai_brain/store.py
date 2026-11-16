"""SQLite store: papers, chunks (FTS5 + float32 vectors), concepts, datasets, edges."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np

DEFAULT_DB = Path("reports/miccai_brain/brain.sqlite")

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS papers (
  paper_id TEXT PRIMARY KEY, title TEXT, paper_url TEXT, pdf_url TEXT, code_url TEXT,
  authors TEXT, abstract TEXT, body TEXT, applications TEXT, ml_tags TEXT, keywords TEXT,
  modalities TEXT, decision TEXT, folder TEXT, vector BLOB
);
CREATE TABLE IF NOT EXISTS paper_modalities (paper_id TEXT, modality TEXT, PRIMARY KEY (paper_id, modality));
CREATE TABLE IF NOT EXISTS chunks (
  id INTEGER PRIMARY KEY, paper_id TEXT, kind TEXT, section TEXT, text TEXT, hash TEXT, vector BLOB
);
CREATE INDEX IF NOT EXISTS chunks_paper ON chunks(paper_id);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(title, section, text, tokenize='porter unicode61');
CREATE TABLE IF NOT EXISTS embed_cache (hash TEXT PRIMARY KEY, vector BLOB);
CREATE TABLE IF NOT EXISTS paper_concepts (paper_id TEXT, concept TEXT, kind TEXT, PRIMARY KEY (paper_id, concept));
CREATE TABLE IF NOT EXISTS paper_datasets (paper_id TEXT, dataset TEXT, mentions INTEGER, PRIMARY KEY (paper_id, dataset));
CREATE TABLE IF NOT EXISTS paper_edges (src TEXT, dst TEXT, weight REAL, PRIMARY KEY (src, dst));
"""


def connect(db_path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def to_blob(vector: np.ndarray) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def from_blob(blob: bytes | None) -> np.ndarray | None:
    return None if blob is None else np.frombuffer(blob, dtype=np.float32)


def set_meta(conn, key: str, value) -> None:
    conn.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, json.dumps(value)))


def get_meta(conn, key: str, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def paper_row(conn, paper_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM papers WHERE paper_id = ?", (paper_id,)).fetchone()
    if not row:
        return None
    out = dict(row)
    out.pop("vector", None)
    for key in ("authors", "applications", "ml_tags", "keywords", "modalities"):
        out[key] = json.loads(out[key] or "[]")
    return out
