"""Pluggable embedders, selected by the MICCAI_BRAIN_EMBEDDER setting.

Spec format: "<provider>:<model>", for example
  sentence-transformers:BAAI/bge-small-en-v1.5
  ollama:nomic-embed-text
  openai:text-embedding-3-small
  ssh:Qwen/Qwen3-Embedding-0.6B   (GPU server running server_embed.py over SSH)
  hash:256          (deterministic, dependency-free; tests only)
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import urllib.request

import numpy as np

DEFAULT_SPEC = "sentence-transformers:Qwen/Qwen3-Embedding-0.6B"
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
        kwargs = {}
        if query and "query" in (getattr(self.model, "prompts", None) or {}):
            kwargs["prompt_name"] = "query"  # same prompt server_embed.py uses
        elif query and self.query_prefix:
            texts = [self.query_prefix + t for t in texts]
        return _normalize(self.model.encode(texts, batch_size=32, show_progress_bar=len(texts) > 64, **kwargs))


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


class SshEmbedder(Embedder):
    """Talks to a long-running server_embed.py over SSH: one JSON request per line.

    -> {"texts": [...], "query": bool}   <- {"vectors": "<base64 float16>", "shape": [n, dim]}
    The server applies the model's own query prompt, so no prefix is added here.

    MICCAI_BRAIN_SSH is the command that opens the connection. A {remote} placeholder marks where
    the remote command goes (otherwise it is appended in single quotes), for example
      wsl.exe -e bash -lc "ssh -o BatchMode=yes -p 2361 user@host '{remote}'"
    MICCAI_BRAIN_SSH_REMOTE is the remote command; {model} in it is replaced by the spec's model.
    """

    DEFAULT_REMOTE = "DEEP_MODEL={model} ~/projects/embed-eval/venv/bin/python ~/projects/embed-eval/server_embed.py"

    def __init__(self, model: str):
        self.model = model
        self.spec = f"ssh:{model}"
        ssh = os.environ.get("MICCAI_BRAIN_SSH")
        if not ssh:
            raise RuntimeError("Set MICCAI_BRAIN_SSH to the ssh command for the GPU server")
        remote = os.environ.get("MICCAI_BRAIN_SSH_REMOTE", self.DEFAULT_REMOTE)
        remote = remote.replace("{model}", model)
        command = ssh.replace("{remote}", remote) if "{remote}" in ssh else f"{ssh} '{remote}'"
        self.batch = int(os.environ.get("MICCAI_BRAIN_EMBED_BATCH", "64"))
        self.proc = subprocess.Popen(command, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     text=True, encoding="utf-8", bufsize=1)
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError(f"embedding server exited before it was ready (command: {command})")
            msg = json.loads(line) if line.strip().startswith("{") else {}
            if msg.get("error"):
                raise RuntimeError(f"embedding server: {msg['error']}")
            if msg.get("ready"):
                break
        self.dim = self.embed(["dimension probe"]).shape[1]

    def embed(self, texts, query=False):
        out = []
        for start in range(0, len(texts), self.batch):
            self.proc.stdin.write(json.dumps({"texts": texts[start : start + self.batch], "query": bool(query)}) + "\n")
            self.proc.stdin.flush()
            answer = json.loads(self.proc.stdout.readline() or '{"error": "server closed"}')
            if "error" in answer:
                raise RuntimeError(f"embedding server: {answer['error']}")
            vec = np.frombuffer(base64.b64decode(answer["vectors"]), dtype=np.float16).reshape(answer["shape"])
            out.append(vec.astype(np.float32))
        return _normalize(np.vstack(out))

    def close(self):
        if self.proc.poll() is None:
            self.proc.stdin.close()
            self.proc.wait(timeout=30)


def get_embedder(spec: str | None = None) -> Embedder:
    spec = spec or os.environ.get("MICCAI_BRAIN_EMBEDDER", DEFAULT_SPEC)
    provider, _, model = spec.partition(":")
    if provider == "hash":
        return HashEmbedder(model)
    if provider == "sentence-transformers":
        return SentenceTransformerEmbedder(model)
    if provider == "ssh":
        return SshEmbedder(model)
    if provider in ("ollama", "openai"):
        return HttpEmbedder(provider, model)
    raise ValueError(f"Unknown embedder provider: {provider!r}")
