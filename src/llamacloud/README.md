# LlamaCloud PDF parsing

Converts paper PDFs to Markdown with [LlamaParse](https://cloud.llamaindex.ai),
keeping tables, equations (LaTeX) and section headings. Use it when PyMuPDF's
plain text layer is not enough, for example to extract result tables.

## Before you run it: fill in the keys

The parser needs at least one LlamaCloud API key, and it refuses to start without one.

1. Copy `src/llamacloud/.env.example` to `.env` at the repository root.
2. Fill in `LLAMA_CLOUD_API_KEY`. You can also add `LLAMA_CLOUD_API_KEY2`, `LLAMA_CLOUD_API_KEY3` and so on.
   When a key fails or runs out of credits, the parser switches to the next one.
3. `pip install -r requirements.txt` (installs `llama-cloud`).

Environment variables take precedence over `.env`. `.env` is gitignored, so never commit keys.
Key health (cooldowns and failures, but no key values) is stored in `.cache/llamacloud_token_state.json`.

## Usage

```bash
python -m src.llamacloud.parse_pdfs path/to/paper.pdf
python -m src.llamacloud.parse_pdfs deepbreath/ --out output/llamacloud --tier cost_effective
```

Each PDF becomes `<out>/<pdf stem>.<tier>.md`, with `<!-- page N -->` markers.
Existing outputs are skipped unless you pass `--overwrite`. `manifest.csv` in the output folder records
the credits, key name and time for every parsed file.

## Tiers

Measured on a 10-page MICCAI paper on 2026-10-20:

| Tier | Credits/page | Result |
|---|---|---|
| `fast` | 1 | Same text as PyMuPDF: no tables, broken hyphenation. Rarely worth it. |
| `cost_effective` (default) | 3 | Correct Markdown tables, LaTeX equations, headings. Recommended. |
| `agentic` | 10 | Slightly cleaner headings and superscripts. |
| `agentic_plus` | more | Highest quality. Not tested. |

A MICCAI paper is about 10 pages, so `cost_effective` costs about 30 credits per paper.
