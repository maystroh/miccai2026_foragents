"""Audit listed code links using unique papers and original modality memberships."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http.client import HTTPException, InvalidURL
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


REPOSITORY_HOSTS = {
    "github.com", "gitlab.com", "gitlab.inria.fr",
    "zivgitlab.uni-muenster.de", "gitlab.gwdg.de",
}
REPOSITORY_TYPES = {"repository_host_link", "anonymous_repository_link"}


def abstract_repository_links(abstract: str) -> list[str]:
    """Recover explicit hosted-repository URLs without interpreting method claims."""
    candidates = re.findall(r"https?://[^\s{}<>\\]+", abstract)
    return list(dict.fromkeys(
        url for candidate in candidates
        if classify_link(url := candidate.rstrip(".,;:)]\"'")) in REPOSITORY_TYPES
    ))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def classify_link(value: str) -> str:
    if not value.strip():
        return "no_listed_link"
    parsed = urlsplit(value.strip())
    host = parsed.netloc.casefold()
    if parsed.scheme not in {"http", "https"} or not host:
        raise ValueError(f"Invalid code URL: {value}")
    if host in REPOSITORY_HOSTS and len(parsed.path.strip("/").split("/")) >= 2:
        return "repository_host_link"
    if host == "anonymous.4open.science" and parsed.path.startswith("/r/"):
        return "anonymous_repository_link"
    if host.endswith(".github.io"):
        return "project_page"
    if host == "huggingface.co":
        return "model_or_dataset_hub"
    if host == "pypi.org":
        return "package_index"
    if host == "www.codabench.org":
        return "benchmark_platform"
    return "other_link"


def load_inventory(root: Path) -> list[dict[str, str]]:
    papers: dict[str, dict[str, str]] = {}
    for path in sorted(root.glob("*/papers_links.csv")):
        for number, row in enumerate(read_csv(path), 2):
            paper_url = row["paper_url"].strip()
            if not paper_url or paper_url in papers:
                raise ValueError(f"Missing or duplicate paper identity in {path}:{number}")
            papers[paper_url] = {
                **row, "source_file": str(path), "source_row": str(number),
                "retained_modality": path.parent.name,
            }
    if not papers:
        raise ValueError(f"No paper indexes under {root}")
    memberships: dict[str, set[str]] = defaultdict(set)
    for row in read_csv(root / "deduplication_map.csv"):
        url = row["paper_url"].strip()
        if url not in papers:
            raise ValueError(f"Audit paper is missing from indexes: {url}")
        memberships[url].add(row["source_modality"])
    if set(memberships) != set(papers):
        raise ValueError("Audit and paper index identities differ")
    result = []
    for url, row in sorted(papers.items()):
        declared = row["code_url"].strip()
        recovered = abstract_repository_links(row["abstract"]) if not declared else []
        code_url = declared or (recovered[0] if recovered else "")
        if len(recovered) > 1:
            raise ValueError(f"Multiple abstract repositories need disambiguation: {url}")
        result.append({
            "paper_url": url, "title": row["title"],
            "original_modalities": " | ".join(sorted(memberships[url])),
            "retained_modality": row["retained_modality"],
            "original_code_url": declared, "code_url": code_url,
            "link_source": "code_url_field" if declared else ("abstract" if recovered else "none"),
            "link_type": classify_link(code_url),
            "source_file": row["source_file"], "source_row": row["source_row"],
            "public_access_status": "not_checked" if code_url else "no_listed_link",
            "http_status": "", "resolved_url": "", "checked_at_utc": "", "check_error": "",
        })
    return result


def summarize(rows: list[dict[str, str]], modality: str) -> dict[str, object]:
    types = Counter(row["link_type"] for row in rows)
    linked = sum(row["link_type"] != "no_listed_link" for row in rows)
    repositories = sum(row["link_type"] in REPOSITORY_TYPES for row in rows)
    return {
        "modality": modality, "papers": len(rows), "listed_code_links": linked,
        "code_url_field_links": sum(row.get("link_source") == "code_url_field" for row in rows),
        "abstract_only_links": sum(row.get("link_source") == "abstract" for row in rows),
        "listed_code_link_percent": round(100 * linked / len(rows), 2) if rows else 0,
        "repository_host_links": repositories,
        "repository_host_link_percent": round(100 * repositories / len(rows), 2) if rows else 0,
        "other_artifact_links": linked - repositories,
        "no_listed_link": types["no_listed_link"],
        "accessible_repository_pages": sum(
            row["link_type"] in REPOSITORY_TYPES and row["public_access_status"] == "accessible"
            for row in rows
        ),
        "unavailable_public_links": sum(row["public_access_status"] == "not_publicly_accessible" for row in rows),
        "unresolved_link_checks": sum(
            row["public_access_status"] not in {"accessible", "not_publicly_accessible", "no_listed_link"}
            for row in rows
        ),
    }


def modality_summaries(rows: list[dict[str, str]], original: bool = True) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        modalities = row["original_modalities"].split(" | ") if original else [row["retained_modality"]]
        for modality in modalities:
            grouped[modality].append(row)
    return [summarize(grouped[name], name) for name in sorted(grouped)]


def check_link(url: str) -> dict[str, str]:
    result = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "resolved_url": url, "http_status": "", "check_error": "",
    }
    request = Request(url, headers={"User-Agent": "MICCAI-repository-availability-audit/1.0"})
    try:
        with urlopen(request, timeout=15) as response:
            result["http_status"] = str(response.status)
            result["resolved_url"] = response.geturl()
            response.read(1024)
        final = urlsplit(result["resolved_url"])
        if any(part in final.path.casefold() for part in ("/login", "/sign_in", "/signin")):
            result["public_access_status"] = "authentication_required"
        else:
            result["public_access_status"] = "accessible"
    except HTTPError as error:
        result["http_status"] = str(error.code)
        result["resolved_url"] = error.geturl()
        result["public_access_status"] = {
            404: "not_publicly_accessible", 410: "not_publicly_accessible",
            401: "authentication_required", 403: "access_denied_or_rate_limited",
            429: "rate_limited",
        }.get(error.code, "http_error")
        result["check_error"] = str(error)
    except (InvalidURL, ValueError) as error:
        result["public_access_status"] = "invalid_url"
        result["check_error"] = str(error)
    except HTTPException as error:
        result["public_access_status"] = "network_error"
        result["check_error"] = str(error)
    except (URLError, TimeoutError, OSError) as error:
        result["public_access_status"] = "network_error"
        result["check_error"] = str(error)
    return result


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_outputs(rows: list[dict[str, str]], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    overall = summarize(rows, "Overall (unique papers)")
    original = modality_summaries(rows)
    retained = modality_summaries(rows, original=False)
    write_csv(output / "paper_repository_inventory.csv", rows)
    write_csv(output / "availability_by_modality.csv", [overall, *original])
    write_csv(output / "availability_by_retained_folder.csv", [overall, *retained])
    hosts = Counter(urlsplit(row["code_url"]).netloc for row in rows if row["code_url"])
    write_csv(output / "link_hosts.csv", [{"host": host, "papers": count} for host, count in hosts.most_common()])
    lines = [
        "# Repository-link availability in the published-paper index", "",
        f"Snapshot generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}", "",
        f"The local published-paper corpus contains {len(rows):,} unique papers, identified by paper_url.",
        "The overall denominator counts each paper once. Modality denominators reconstruct original",
        "memberships from Published_papers/deduplication_map.csv, so multimodal papers appear in",
        "more than one modality. Modality totals must not be added to obtain the overall total.", "",
        f"The code_url field supplies {overall['code_url_field_links']} links; abstracts supply",
        f"{overall['abstract_only_links']} additional explicit repository URLs for papers with an empty code_url.",
        "Original CSVs are unchanged. The inventory preserves original_code_url and link_source.", "",
        "A listed code link is a declaration, not proof of released source code. Repository-host links",
        "include GitHub, GitLab, and anonymous.4open.science. Other links include project pages,",
        "model/dataset hubs, a package index, and a benchmark platform. No listed link means unknown",
        "code availability, not confirmed absence of code. Project pages can lead to additional repositories.", "",
        "Live checks, when requested, test public HTTP accessibility only. A successful page response",
        "does not establish that a repository contains implementation files or reproduces the paper.",
        "404/410 means the listed URL is not publicly accessible; it does not distinguish a private",
        "repository from a missing one. Network errors, authentication, and rate limits remain unresolved.", "",
        "## Visual summary", "",
        "![Overall repository availability](overall_availability.png)", "",
        "![Repository availability by original modality](availability_by_modality.png)", "",
        "[Overall chart (SVG)](overall_availability.svg) · [Modality chart (SVG)](availability_by_modality.svg)", "",
        "## Other artifact links", "",
        "![What other artifact links provide access to](other_artifact_access.png)", "",
        "The 16 links comprise 12 project websites, one model hub, one dataset hub,",
        "one installable package, and one benchmark portal. Ten project websites display",
        "onward code links; one marks code as coming soon; one has no code-labelled link identified.",
        "These are landing-page observations, not newly verified repository releases.", "",
        "[Curia-2](https://huggingface.co/raidium/curia-2) requires accepting conditions for model-file access.",
        "[MIMIC-MTE](https://huggingface.co/datasets/wanqi16/MIMIC-MTE) has an empty card and no supported data files detected by its viewer.",
        "[clinical-cad](https://pypi.org/project/clinical-cad/) provides package installation instructions.",
        "The SlideGuard Codabench URL is classified by platform; competition contents could not be verified.", "",
        "See [per-paper classifications and evidence](other_artifact_details.csv).",
        "The original availability snapshot and its counts are unchanged.", "",
        "## Original modality memberships", "",
        "| Modality | Papers | Listed code links | Link rate | Repository-host links | Repo-link rate | Accessible repo pages | Other links | No link |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for stat in [overall, *original]:
        lines.append(
            f"| {stat['modality']} | {stat['papers']} | {stat['listed_code_links']} | "
            f"{stat['listed_code_link_percent']:.2f}% | {stat['repository_host_links']} | "
            f"{stat['repository_host_link_percent']:.2f}% | {stat['accessible_repository_pages']} | "
            f"{stat['other_artifact_links']} | {stat['no_listed_link']} |"
        )
    lines.extend(["", "## Link types", ""])
    for kind, count in Counter(row["link_type"] for row in rows).most_common():
        lines.append(f"- {kind}: {count}")
    lines.extend(["", "## Public accessibility checks", ""])
    for status, count in Counter(row["public_access_status"] for row in rows).most_common():
        lines.append(f"- {status}: {count}")
    lines.extend([
        "", "## Cohort interpretation", "",
        "Use published-paper membership as the corpus definition. Do not filter on meta_final_decision:",
        "that field stores the last extracted AC recommendation, which is not necessarily the",
        "conference's final publication decision. The local review data includes Reject recommendations",
        "for papers present on the official accepted-version open-access site.", "",
        "Official example checked on 2026-10-01:",
        "https://papers.miccai.org/miccai-2026/0078-Paper2030.html",
        "The site's introduction identifies its contents as accepted versions; the same page contains",
        "a rejecting AC recommendation. This confirms that review recommendations are an unsuitable filter.", "",
        "## Regeneration", "", "```bash", "make report",
        "# Optional live public HTTP checks (no cloning, PDF downloads, or code execution):",
        "python3 -m src.repository_availability --check-links", "```", "",
    ])
    (output / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper-root", type=Path, default=Path("Published_papers"))
    parser.add_argument("--output", type=Path, default=Path("reports/repository_availability"))
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--check-links", action="store_true")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    rows = load_inventory(args.paper_root)
    if args.validate_only:
        print(f"Validated {len(rows)} unique papers and their original modality memberships.")
        return 0
    # Reuse prior observations only for unchanged URLs. Live checks resume unchecked links.
    previous = args.output / "paper_repository_inventory.csv"
    if previous.exists():
        prior = {row["paper_url"]: row for row in read_csv(previous)}
        for row in rows:
            old = prior.get(row["paper_url"], {})
            if old.get("code_url") == row["code_url"]:
                for key in ("public_access_status", "http_status", "resolved_url", "checked_at_utc", "check_error"):
                    row[key] = old.get(key, row[key])
    write_outputs(rows, args.output)
    if args.check_links:
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            if row["code_url"] and row["public_access_status"] == "not_checked":
                grouped[row["code_url"]].append(row)
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(check_link, url): url for url in grouped}
            for count, future in enumerate(as_completed(futures), 1):
                for row in grouped[futures[future]]:
                    row.update(future.result())
                if count % 25 == 0 or count == len(futures):
                    write_outputs(rows, args.output)
                    print(f"Checked {count}/{len(futures)} links", flush=True)
    print(json.dumps(summarize(rows, "Overall (unique papers)"), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
