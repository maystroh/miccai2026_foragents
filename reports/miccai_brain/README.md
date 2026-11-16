# MICCAI brain

Hybrid semantic search and topic graphs over all MICCAI 2026 papers, inspired by
[gbrain](https://github.com/garrytan/gbrain). Code: `src/miccai_brain/`.

- **Search**: SQLite FTS5 (BM25) plus vector search over paper chunks, merged per paper
  with reciprocal rank fusion. Peer reviews are indexed too and are searched on request.
- **Graph**: papers, concepts and datasets. Concepts come from the authors' keyword line,
  the MICCAI Body/Applications/ML tags and (optionally) an LLM extraction of tasks, methods,
  anatomy and metrics. Datasets come from `inputs/datasets.csv` plus the LLM extraction.
  Papers are linked to their 8 nearest neighbours by embedding similarity.
- **Topics** are the modality folders under `Published_papers/`. A paper belongs to every
  modality that lists it in `deduplication_map.csv`.

## Run

Run from the miccai2026 folder (it needs `Published_papers/<modality>/<paper>/` folders).

Settings can live in the `.env` of the miccai2026 folder (the CLI reads it).

```bash
# GPU server over SSH running server_embed.py (JSON lines on stdin/stdout); {remote} marks
# where the remote command goes
MICCAI_BRAIN_EMBEDDER=ssh:Qwen/Qwen3-Embedding-0.6B
MICCAI_BRAIN_SSH=wsl.exe -e bash -lc "ssh -o BatchMode=yes -p <port> <user>@<host> '{remote}'"
# optional: embed search queries locally with the same model instead of over SSH
MICCAI_BRAIN_QUERY_EMBEDDER=sentence-transformers:Qwen/Qwen3-Embedding-0.6B
OPENROUTER_API_KEY=...
```

Other embedders:

```bash
# OpenAI-compatible /v1/embeddings server (vLLM, TEI, ...)
export MICCAI_BRAIN_EMBEDDER="openai:Qwen/Qwen3-Embedding-4B"
export MICCAI_BRAIN_EMBED_URL="http://<server>:<port>/v1"
export MICCAI_BRAIN_EMBED_KEY_VAR=""            # name of the env var holding the key, if any

# optional: LLM extraction via OpenRouter, cached in reports/miccai_brain/llm/
export MICCAI_BRAIN_LLM_KEY_VAR="OPENROUTER_API_KEY"
python -m src.miccai_brain extract --model anthropic/claude-haiku-5.5 --limit 20   # pilot
python -m src.miccai_brain extract --model anthropic/claude-haiku-5.5              # all papers

python -m src.miccai_brain build              # writes brain.sqlite and brain.html here
python -m src.miccai_brain search "missing modality brain tumor segmentation" -m MRI
python -m src.miccai_brain search "limited novelty" --reviews
python -m src.miccai_brain related 0002-Paper5533
python -m src.miccai_brain topic EHR
python -m src.miccai_brain concept BraTS -m MRI
```

Ollama also works (`MICCAI_BRAIN_EMBEDDER=ollama:<model>`), as does a local
sentence-transformers model (`sentence-transformers:BAAI/bge-small-en-v1.5`). Re-running
`build` reuses cached embeddings for unchanged text. Qwen3-Embedding models get their query
instruction automatically; override it with `MICCAI_BRAIN_QUERY_PREFIX`.

## Claude / MCP

```bash
claude mcp add miccai-brain -- python -m src.miccai_brain serve
```

Tools: `search_papers`, `get_paper`, `related_papers`, `list_topics`, `topic_overview`,
`papers_with`.

## Dashboard

`brain.html` is self-contained (data inlined; the graph library loads from jsDelivr). Pick a
topic, filter by text, click a paper for its abstract, concepts, datasets and nearest
neighbours, or click a concept/dataset for its papers.

## Inputs

- `inputs/datasets.csv`: dataset vocabulary (name, regex). Add rows to catch more datasets.
- `inputs/concept_aliases.csv`: merges synonyms (e.g. `cnns` -> `cnn`).
