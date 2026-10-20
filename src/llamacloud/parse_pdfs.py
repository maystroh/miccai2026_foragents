"""Convert paper PDFs to Markdown with LlamaCloud (LlamaParse).

Requires LlamaCloud API keys in the repository-root `.env` (or the environment):
LLAMA_CLOUD_API_KEY, optionally LLAMA_CLOUD_API_KEY2, LLAMA_CLOUD_API_KEY3, ...
Keys are rotated automatically when one fails or runs out of credits.

Examples:
    python -m src.llamacloud.parse_pdfs paper.pdf
    python -m src.llamacloud.parse_pdfs deepbreath/ --out output/llamacloud --tier cost_effective

Tiers and measured cost on a 10-page MICCAI paper: fast 1 credit/page (same text
as PyMuPDF), cost_effective 3 credits/page (tables, LaTeX, headings; recommended),
agentic 10 credits/page.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import time
from datetime import datetime, timezone
from pathlib import Path

from src.llamacloud.llamacloud_tokens import has_llamacloud_tokens, run_with_rotating_tokens

TIERS = ["fast", "cost_effective", "agentic", "agentic_plus"]


async def parse_pdf(pdf: Path, tier: str) -> tuple[str, str, float | None]:
    """Return (markdown, token env name, credits used) for one PDF."""

    async def operation(client, token):
        with open(pdf, "rb") as handle:
            file_obj = await client.files.create(file=handle, purpose="parse")
        kwargs = dict(file_id=file_obj.id, tier=tier, version="latest")
        if tier == "fast":
            kwargs["expand"] = ["text"]
        else:
            kwargs["output_options"] = {"markdown": {"tables": {"output_tables_as_markdown": True}}}
            kwargs["expand"] = ["markdown"]
        result = await client.parsing.parse(**kwargs)
        usage = await client.parsing.get(result.job.id, expand=["usage"])
        credits = usage.job.usage.credits if usage.job.usage else None
        return result, credits

    # Never log key material: labels look like "LLAMA_CLOUD_API_KEY2 (llx-ab...wxyz)".
    (result, credits), token = await run_with_rotating_tokens(
        operation, logger=lambda message: print(message.split(" (llx")[0])
    )
    if result.markdown:
        pages = [(page.page_number, page.markdown) for page in result.markdown.pages]
    else:
        pages = [(page.page_number, page.text) for page in result.text.pages]
    markdown = "\n\n".join(f"<!-- page {number} -->\n{body}" for number, body in pages)
    return markdown, token.env_name, credits


async def run(pdfs: list[Path], out_dir: Path, tier: str, overwrite: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = out_dir / "manifest.csv"
    new_manifest = not manifest.exists()
    total = 0.0
    with manifest.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if new_manifest:
            writer.writerow(["pdf", "output", "tier", "credits", "token", "seconds", "parsed_at"])
        for index, pdf in enumerate(pdfs, 1):
            target = out_dir / f"{pdf.stem}.{tier}.md"
            if target.exists() and not overwrite:
                print(f"[{index}/{len(pdfs)}] skip (exists): {target.name}")
                continue
            print(f"[{index}/{len(pdfs)}] {pdf.name}")
            started = time.time()
            try:
                markdown, token_name, credits = await parse_pdf(pdf, tier)
            except Exception as exc:  # keep going through the batch
                print(f"   failed: {exc}")
                continue
            target.write_text(markdown, encoding="utf-8")
            total += credits or 0
            writer.writerow([
                str(pdf), str(target), tier, credits, token_name,
                f"{time.time() - started:.1f}", datetime.now(timezone.utc).isoformat(),
            ])
            handle.flush()
            print(f"   {credits} credits via {token_name} -> {target}")
    print(f"Done. Credits used this run: {total:g}. Manifest: {manifest}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("inputs", nargs="+", help="PDF files or folders (searched recursively)")
    parser.add_argument("--out", default="output/llamacloud", help="output folder (default: output/llamacloud)")
    parser.add_argument("--tier", default="cost_effective", choices=TIERS)
    parser.add_argument("--overwrite", action="store_true", help="re-parse PDFs that already have output")
    args = parser.parse_args()

    if not has_llamacloud_tokens():
        raise SystemExit(
            "No LlamaCloud keys found. Copy src/llamacloud/.env.example to .env at the "
            "repository root and fill in LLAMA_CLOUD_API_KEY (and KEY2, KEY3, ... if you have them)."
        )

    pdfs: list[Path] = []
    for item in map(Path, args.inputs):
        pdfs.extend(sorted(item.rglob("*.pdf")) if item.is_dir() else [item])
    if not pdfs:
        raise SystemExit("No PDFs found.")
    asyncio.run(run(pdfs, Path(args.out), args.tier, args.overwrite))


if __name__ == "__main__":
    main()
