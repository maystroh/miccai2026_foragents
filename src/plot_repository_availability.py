"""Plot the saved repository availability audit without making network requests."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", tempfile.mkdtemp(prefix="miccai-matplotlib-"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

from src.repository_availability import REPOSITORY_TYPES, read_csv


STATUSES = (
    ("accessible", "Accessible repository page", "#167D9A"),
    ("unavailable", "HTTP 404 / 410 — not found / gone", "#C96153"),
    ("unresolved", "Malformed or unresolved repository link", "#8767A5"),
    ("other", "Other artifact link", "#D8A642"),
    ("missing", "No link found", "#CFD7DD"),
)
LABELS = {
    "Computational_imagings": "Computational imaging", "Diffusion-MRI": "Diffusion MRI",
    "Func_MRI": "Functional MRI", "Multimodals": "Multimodal",
    "PET_SPECT": "PET / SPECT", "Photo_video": "Photo / video",
    "Physio-signals": "Physiological signals", "ultrasounds": "Ultrasound",
}


def status_group(row: dict[str, str]) -> str:
    if row["link_type"] == "no_listed_link":
        return "missing"
    if row["link_type"] not in REPOSITORY_TYPES:
        return "other"
    if row["public_access_status"] == "accessible":
        return "accessible"
    if row["public_access_status"] == "not_publicly_accessible":
        return "unavailable"
    return "unresolved"


def grouped_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    counts = {key: 0 for key, _, _ in STATUSES}
    for row in rows:
        counts[status_group(row)] += 1
    return counts


def clean_axes(ax) -> None:
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(axis="both", length=0, colors="#4B5B66", pad=8)
    ax.set_axisbelow(True)
    ax.grid(axis="x", color="#E5EAEE", linewidth=0.7)


def save(fig, output: Path, name: str) -> None:
    for extension in ("png", "svg"):
        save_image(fig, output / f"{name}.{extension}")
    plt.close(fig)


def save_image(fig, target: Path) -> None:
    # Replace completed images atomically, including when a viewer has the old image open.
    with tempfile.NamedTemporaryFile(prefix=f".{target.stem}-", suffix=target.suffix, dir=target.parent, delete=False) as handle:
        temporary = Path(handle.name)
    fig.savefig(temporary, dpi=180, facecolor="white")
    temporary.replace(target)


def plot_overall(rows: list[dict[str, str]], output: Path, checked_date: str) -> None:
    counts = grouped_counts(rows)
    total = len(rows)
    fig, ax = plt.subplots(figsize=(12, 5.8))
    fig.subplots_adjust(left=0.36, right=0.87, top=0.72, bottom=0.24)
    fig.text(0.045, 0.94, "Repository availability across the published corpus", fontsize=19, weight="bold", color="#233644")
    accessible = counts["accessible"]
    fig.text(0.045, 0.845, f"{accessible:,} / {total:,} papers  ·  {accessible / total:.1%} have an accessible repository page", fontsize=15, color="#167D9A", weight="bold")
    for index, (key, label, color) in enumerate(STATUSES):
        count = counts[key]
        ax.barh(index, count, height=0.58, color=color)
        ax.text(count + total * 0.012, index, f"{count:,}  ({count / total:.1%})", va="center", fontsize=11, color="#233644")
    ax.set_yticks(range(len(STATUSES)), [label for _, label, _ in STATUSES])
    ax.invert_yaxis()
    ax.set_xlim(0, total * 0.79)
    ax.set_xlabel("Unique papers", fontsize=11, labelpad=9)
    clean_axes(ax)
    fig.text(0.045, 0.065, f"Public-link checks: {checked_date}. Source: saved paper repository inventory. No link found means availability is unknown.", fontsize=9, color="#596C79")
    fig.text(0.045, 0.025, "HTTP 404 can also mean private or moved. Accessibility checks do not inspect repository contents.", fontsize=9, color="#596C79")
    save(fig, output, "overall_availability")


def plot_modalities(rows: list[dict[str, str]], output: Path, checked_date: str) -> None:
    groups: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        for modality in row["original_modalities"].split(" | "):
            groups.setdefault(modality, []).append(row)
    counts = {name: grouped_counts(items) for name, items in groups.items()}
    names = sorted(groups, key=lambda name: (-counts[name]["accessible"] / len(groups[name]), name))
    positions = list(range(len(names)))
    fig, (coverage, volume) = plt.subplots(1, 2, figsize=(16, 11), gridspec_kw={"width_ratios": [1.7, 1]}, sharey=True)
    fig.subplots_adjust(left=0.19, right=0.91, top=0.81, bottom=0.26, wspace=0.2)
    fig.text(0.045, 0.95, "Repository availability by original modality", fontsize=23, weight="bold", color="#233644")
    fig.text(0.045, 0.9, "Compare coverage on the left and the number of accessible repository pages on the right.", fontsize=12, color="#596C79")
    fig.text(0.045, 0.865, "MRI: 227 / 302 papers (75.2%)  ·  Overall: 828 / 1,161 unique papers (71.3%)", fontsize=13, color="#167D9A", weight="bold")
    offsets = [0.0] * len(names)
    for key, label, color in STATUSES:
        values = [100 * counts[name][key] / len(groups[name]) for name in names]
        coverage.barh(positions, values, left=offsets, height=0.68, color=color, label=label)
        offsets = [left + value for left, value in zip(offsets, values)]
    for index, name in enumerate(names):
        rate = 100 * counts[name]["accessible"] / len(groups[name])
        coverage.text(rate / 2, index, f"{rate:.1f}%", color="white", ha="center", va="center", fontsize=10, weight="bold")
        value = counts[name]["accessible"]
        volume.barh(index, value, height=0.68, color="#167D9A")
        volume.text(value + 4, index, f"{value} / {len(groups[name])}", va="center", color="#233644", fontsize=10, weight="bold" if name == "MRI" else "normal")
    coverage.set_yticks(positions, [LABELS.get(name, name) for name in names])
    coverage.invert_yaxis()
    for tick, name in zip(coverage.get_yticklabels(), names):
        if name == "MRI":
            tick.set_color("#167D9A")
            tick.set_weight("bold")
    coverage.set_xlim(0, 100)
    coverage.xaxis.set_major_formatter(PercentFormatter())
    coverage.set_xlabel("Share of papers in each modality", labelpad=12)
    coverage.set_title("Coverage · sorted by accessible share", loc="left", fontsize=12, pad=16)
    volume.set_xlim(0, max(counts[name]["accessible"] for name in names) * 1.35)
    volume.set_xlabel("Papers with accessible repository pages", labelpad=12)
    volume.set_title("Accessible / total papers", loc="left", fontsize=12, pad=16)
    volume.tick_params(axis="y", labelleft=False)
    for ax in (coverage, volume):
        clean_axes(ax)
    handles, labels = coverage.get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower left", bbox_to_anchor=(0.18, 0.09), ncol=2, frameon=False, fontsize=10)
    fig.text(0.045, 0.065, "Modality memberships overlap; do not sum these rows. Small groups (e.g., Spectroscopy, n=4) have less stable percentages.", fontsize=10, color="#596C79")
    fig.text(0.045, 0.025, f"Public-link checks: {checked_date}. Other links include project pages and model/data hubs. Repository code was not analyzed.", fontsize=10, color="#596C79")
    save(fig, output, "availability_by_modality")


def plot_other_artifacts(rows: list[dict[str, str]], output: Path) -> None:
    """Show portal types and the onward-code links exposed by project websites."""
    annotations = read_csv(Path("data/other_artifact_classification.csv"))
    candidates = {row["code_url"]: row for row in rows if status_group(row) == "other"}
    if {item["artifact_url"] for item in annotations} != set(candidates):
        raise ValueError("Artifact annotations do not match the other-link inventory")
    categories = ["Project website", "Model hub", "Dataset hub", "Installable package", "Benchmark portal"]
    category_colors = ["#167D9A", "#8767A5", "#59977B", "#D8A642", "#C96153"]
    fig, (types, websites) = plt.subplots(1, 2, figsize=(16, 7), gridspec_kw={"width_ratios": [1.3, 1]})
    fig.subplots_adjust(left=0.15, right=0.93, top=0.73, bottom=0.3, wspace=0.55)
    fig.text(0.04, 0.94, "What do the 16 other artifact links point to?", fontsize=22, weight="bold", color="#233644")
    fig.text(0.04, 0.865, "Project pages are often gateways to code, data, models and demonstrations.", fontsize=13, color="#596C79")
    for index, (category, color) in enumerate(zip(categories, category_colors)):
        count = sum(item["access_type"] == category for item in annotations)
        types.barh(index, count, color=color, height=0.6)
        types.text(count + 0.15, index, f"{count} / 16", va="center", fontsize=11, color="#233644")
    types.set_yticks(range(len(categories)), categories)
    types.invert_yaxis()
    types.set_xlim(0, 14)
    types.set_xticks([0, 4, 8, 12])
    types.set_title("Destination type · one per paper", loc="left", fontsize=12, pad=18)
    types.set_xlabel("Papers", labelpad=12)
    project_rows = [item for item in annotations if item["access_type"] == "Project website"]
    details = [("linked", "Code link shown", "#167D9A"), ("coming_soon", "Code marked coming soon", "#D8A642"), ("not_identified", "No code link identified", "#CFD7DD")]
    for index, (status, label, color) in enumerate(details):
        count = sum(item["project_code_link_status"] == status for item in project_rows)
        websites.barh(index, count, height=0.5, color=color)
        websites.text(count + 0.12, index, f"{count} / {len(project_rows)}", va="center", fontsize=11, color="#233644")
    websites.set_yticks(range(len(details)), [item[1] for item in details])
    websites.invert_yaxis()
    websites.set_xlim(0, 12)
    websites.set_xticks([0, 4, 8, 12])
    websites.set_title("Within the 12 project websites", loc="left", fontsize=12, pad=18)
    websites.set_xlabel("Project websites", labelpad=12)
    for ax in (types, websites):
        clean_axes(ax)
    fig.text(0.04, 0.18, "Model hub: Curia-2 has gated file access. Dataset hub: MIMIC-MTE does not currently show supported data files.", fontsize=11, color="#596C79")
    fig.text(0.04, 0.115, "Package: clinical-cad offers an installable tool. Benchmark portal: SlideGuard's competition contents remain unverified.", fontsize=11, color="#596C79")
    fig.text(0.04, 0.05, "Reviewed October 2, 2026. Onward links were identified on landing pages; repository code and downloads were not analyzed.", fontsize=10, color="#596C79")
    save_image(fig, output / "other_artifact_access.png")
    plt.close(fig)
    joined = [{**candidates[item["artifact_url"]], **item} for item in annotations]
    from src.repository_availability import write_csv
    write_csv(output / "other_artifact_details.csv", joined)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("reports/repository_availability"))
    args = parser.parse_args()
    rows = read_csv(args.output / "paper_repository_inventory.csv")
    checked_dates = sorted({row["checked_at_utc"][:10] for row in rows if row["checked_at_utc"]})
    checked_date = "not checked" if not checked_dates else " to ".join(dict.fromkeys([checked_dates[0], checked_dates[-1]]))
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "svg.fonttype": "none"})
    plot_overall(rows, args.output, checked_date)
    plot_modalities(rows, args.output, checked_date)
    plot_other_artifacts(rows, args.output)
    print(f"Saved overall, modality, and other-artifact charts to {args.output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
