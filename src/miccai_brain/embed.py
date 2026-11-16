"""Pluggable embedders, selected by the MICCAI_BRAIN_EMBEDDER setting.

Spec format: "<provider>:<model>", for example
  sentence-transformers:BAAI/bge-small-en-v1.5
  ollama:nomic-embed-text
  openai:text-embedding-3-small
  hash:256          (deterministic, dependency-free; tests only)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request

import numpy as np

DEFAULT_SPEC = "sentence-transformers:BAAI/bge-small-en-v1.5"
QWEN3_QUERY_PREFIX = (
    "Instruct: Given a search query about medical image computing, retrieve relevant MICCAI paper passages\nQuery: "
)


def query_prefix_for(model: str) -> str:
    """Qwen3-Embedding expects an instruction on queries (not on documents)."""
    if "MICCAI_BRAIN_QUERY_PREFIX" in os.environ:
        return os.environ["MICCAI_BRAIN_QUERY_PREFIX"].replace("\\n", "\n")
    return QWEN3_QUERY_PREFIX if "qwen3-embedding" in model.lower() else ""


class Embedder:
    spec: str
    dim: int

    def embed(self, texts: list[str], query: bool = False) -> np.ndarray:
        raise NotImplementedError


def _normalize(vectors: np.ndarray) -> np.ndarray:
    vectors = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.maximum(norms, 1e-12)


class HashEmbedder(Embedder):
    def __init__(self, dim: str = "256"):
        self.dim = int(dim or 256)
        self.spec = f"hash:{self.dim}"

    def embed(self, texts, query=False):
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            for token in re.findall(r"[a-z0-9]+", text.lower()):
                h = int(hashlib.md5(token.encode()).hexdigest(), 16)
                out[i, h % self.dim] += 1.0 if (h >> 64) & 1 else -1.0
        return _normalize(out)


class SentenceTransformerEmbedder(Embedder):
    def __init__(self, model: str):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model)
        self.spec = f"sentence-transformers:{model}"
        self.dim = self.model.get_sentence_embedding_dimension()
        self.query_prefix = query_prefix_for(model)

    def embed(self, texts, query=False):
        if query and self.query_prefix:
            texts = [self.query_prefix + t for t in texts]
        return _normalize(self.model.encode(texts, batch_size=32, show_progress_bar=len(texts) > 64))


class HttpEmbedder(Embedder):
    """Ollama (/api/embed) or any OpenAI-compatible /v1/embeddings endpoint (vLLM, TEI, llama.cpp).

    Server settings: MICCAI_BRAIN_EMBED_URL (base URL, e.g. http://gpu-box:8000/v1) and
    MICCAI_BRAIN_EMBED_KEY_VAR (name of the env variable holding the key, if any).
    """

    def __init__(self, provider: str, model: str):
        self.provider, self.model = provider, model
        self.spec = f"{provider}:{model}"
        self.query_prefix = query_prefix_for(model)
        self.batch = int(os.environ.get("MICCAI_BRAIN_EMBED_BATCH", "32"))
        base = os.environ.get("MICCAI_BRAIN_EMBED_URL")
        if provider == "ollama":
            base = base or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
            self.url = base.rstrip("/") + "/api/embed"
        else:
            base = base or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
            self.url = base.rstrip("/") + "/embeddings"
        self.key = os.environ.get(os.environ.get("MICCAI_BRAIN_EMBED_KEY_VAR", "OPENAI_API_KEY"), "")
        self.dim = len(self.embed(["dimension probe"])[0])

    def _post(self, payload):
        req = urllib.request.Request(self.url, data=json.dumps(payload).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        if self.key:
            req.add_header("Authorization", f"Bearer {self.key}")
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read())

    def embed(self, texts, query=False):
        if query and self.query_prefix:
            texts = [self.query_prefix + t for t in texts]
        vectors = []
        for start in range(0, len(texts), self.batch):
            batch = texts[start : start + self.batch]
            data = self._post({"model": self.model, "input": batch})
            if self.provider == "ollama":
                vectors.extend(data["embeddings"])
            else:
                vectors.extend(item["embedding"] for item in sorted(data["data"], key=lambda d: d["index"]))
        return _normalize(np.array(vectors))


def get_embedder(spec: str | None = None) -> Embedder:
    spec = spec or os.environ.get("MICCAI_BRAIN_EMBEDDER", DEFAULT_SPEC)
    provider, _, model = spec.partition(":")
    if provider == "hash":
        return HashEmbedder(model)
    if provider == "sentence-transformers":
        return SentenceTransformerEmbedder(model)
    if provider in ("ollama", "openai"):
        return HttpEmbedder(provider, model)
    raise ValueError(f"Unknown embedder provider: {provider!r}")
