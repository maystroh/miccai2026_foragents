"""Optional LLM extraction of tasks, methods, anatomy, datasets and metrics via OpenRouter.

Results are cached per paper in reports/miccai_brain/llm/<paper_id>.json, keyed by model and
prompt version, so `build` picks them up without calling the API again.

Settings: MICCAI_BRAIN_LLM_MODEL (OpenRouter id), MICCAI_BRAIN_LLM_KEY_VAR (name of the env
variable holding the key; default OPENROUTER_API_KEY), MICCAI_BRAIN_LLM_URL (default OpenRouter).
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .chunking import clean_markdown
from .corpus import Paper

PROMPT_VERSION = "v1"
CACHE_DIR = Path("reports/miccai_brain/llm")
LLM_KINDS = ("task", "method", "anatomy", "metric")

SYSTEM = (
    "You extract structured facts from MICCAI medical-imaging papers. Answer with one JSON object and "
    "nothing else. Use short canonical noun phrases in lowercase (e.g. 'brain tumor segmentation', "
    "'diffusion model', 'mamba', 'dice score'). Prefer widely used names over the paper's invented model "
    "names. Only list datasets that the paper actually uses, with their public name if they have one."
)
SCHEMA_HINT = {
    "tasks": ["clinical/technical tasks addressed, 1-4"],
    "methods": ["key method families or building blocks, 2-6"],
    "anatomy": ["organs or body regions, 0-3"],
    "metrics": ["evaluation metrics, 0-5"],
    "datasets": [{"name": "dataset name", "public": True, "role": "train|eval|both"}],
    "contributions": ["one-sentence main contributions, 1-3"],
    "limitations": ["limitations stated by the authors, 0-3"],
}


def paper_prompt(paper: Paper, max_chars: int = 24000) -> str:
    body = clean_markdown(paper.markdown)[:max_chars]
    return (
        f"Title: {paper.title}\nModalities: {', '.join(paper.modalities)}\nAuthor keywords: {', '.join(paper.keywords)}\n"
        f"Abstract: {paper.abstract}\n\nPaper text (truncated):\n{body}\n\n"
        f"Return JSON with exactly these keys: {json.dumps(SCHEMA_HINT)}"
    )


def cache_path(root: Path, paper_id: str) -> Path:
    return Path(root) / CACHE_DIR / f"{paper_id}.json"


def load_cached(root: Path, paper_id: str) -> dict | None:
    path = cache_path(root, paper_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _parse_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start : end + 1])


def call_llm(prompt: str, model: str, retries: int = 4) -> tuple[dict, dict]:
    url = os.environ.get("MICCAI_BRAIN_LLM_URL", "https://openrouter.ai/api/v1").rstrip("/") + "/chat/completions"
    key = os.environ.get(os.environ.get("MICCAI_BRAIN_LLM_KEY_VAR", "OPENROUTER_API_KEY"), "")
    if not key:
        raise RuntimeError("No API key: set MICCAI_BRAIN_LLM_KEY_VAR to the env variable that holds it")
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 1500,
        "response_format": {"type": "json_object"},
        "usage": {"include": True},  # OpenRouter returns the real cost in usage.cost
    }
    for attempt in range(retries):
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {key}")
        req.add_header("X-Title", "miccai-brain")
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read())
            return _parse_json(data["choices"][0]["message"]["content"]), data.get("usage", {})
        except (urllib.error.URLError, json.JSONDecodeError, KeyError, ValueError) as exc:
            if attempt == retries - 1:
                raise RuntimeError(f"LLM call failed: {exc}") from exc
            time.sleep(2 ** attempt * 2)
    raise RuntimeError("unreachable")


def extract_all(root: Path, papers: list[Paper], model: str, workers: int = 4, force: bool = False,
                limit: int | None = None, max_cost: float | None = None, log=print) -> dict:
    """Extract and cache; stops submitting new papers once the spent cost reaches max_cost (USD)."""
    todo = []
    for paper in papers:
        cached = load_cached(root, paper.paper_id)
        if force or not cached or cached.get("model") != model or cached.get("prompt_version") != PROMPT_VERSION:
            todo.append(paper)
    if limit:
        todo = todo[:limit]
    log(f"LLM extraction with {model}: {len(todo)} papers to do, {len(papers) - len(todo)} cached"
        + (f", budget ${max_cost:.2f}" if max_cost else ""))
    usage = {"papers": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0, "failed": 0, "stopped_by_budget": False}

    def work(paper: Paper):
        try:
            result, used = call_llm(paper_prompt(paper), model)
        except RuntimeError as exc:
            return paper, None, str(exc)
        record = {"paper_id": paper.paper_id, "model": model, "prompt_version": PROMPT_VERSION,
                  "extracted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "usage": used, "result": result}
        path = cache_path(root, paper.paper_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
        return paper, used, None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for start in range(0, len(todo), workers * 5):
            if max_cost is not None and usage["cost"] >= max_cost:
                usage["stopped_by_budget"] = True
                log(f"  budget of ${max_cost:.2f} reached; stopping. Re-run to continue from the cache.")
                break
            for paper, used, error in pool.map(work, todo[start : start + workers * 5]):
                if error:
                    usage["failed"] += 1
                    log(f"  ! {paper.paper_id}: {error}")
                    continue
                usage["papers"] += 1
                for key in ("prompt_tokens", "completion_tokens"):
                    usage[key] += int(used.get(key, 0) or 0)
                usage["cost"] += float(used.get("cost", 0) or 0)
            log(f"  {usage['papers']}/{len(todo)}  tokens in {usage['prompt_tokens']:,} out {usage['completion_tokens']:,}"
                f"  cost ${usage['cost']:.4f}")
    if usage["papers"]:
        usage["cost_per_paper"] = round(usage["cost"] / usage["papers"], 5)
    usage["cost"] = round(usage["cost"], 4)
    return usage


def spent(root: Path, model: str | None = None) -> dict:
    """Total recorded cost of the cached extractions."""
    total, n = 0.0, 0
    for path in (Path(root) / CACHE_DIR).glob("*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        if model and record.get("model") != model:
            continue
        total += float((record.get("usage") or {}).get("cost", 0) or 0)
        n += 1
    return {"papers": n, "cost": round(total, 4)}


def llm_concepts(record: dict | None) -> tuple[list[tuple[str, str]], list[str]]:
    """(concept, kind) pairs and dataset names from a cached extraction."""
    if not record:
        return [], []
    result = record.get("result", {})
    concepts = []
    for key, kind in (("tasks", "task"), ("methods", "method"), ("anatomy", "anatomy"), ("metrics", "metric")):
        for term in result.get(key, []) or []:
            if isinstance(term, str) and term.strip():
                concepts.append((term, kind))
    datasets = []
    for item in result.get("datasets", []) or []:
        name = item.get("name") if isinstance(item, dict) else item
        if isinstance(name, str) and name.strip() and (not isinstance(item, dict) or item.get("public", True)):
            datasets.append(name.strip())
    return concepts, datasets
