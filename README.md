# miccai2026_foragents

This project analyzes MICCAI 2026 medical-imaging papers, with classification
and segmentation of MRI volumes as the main focus and breast MRI prioritized
for deeper analysis.

See [AGENTS.md](AGENTS.md) for repository conventions and
[docs/PROJECT_MEMORY.md](docs/PROJECT_MEMORY.md) for the current analysis state.

## Repository availability

Of **1,161 unique published papers**, **828 (71.32%)** have publicly accessible
repository pages. For MRI, the corresponding count is **227/302 (75.17%)**.
These are public page checks from October 1, 2026; repository code has not been analyzed.

[![Overall repository availability](reports/repository_availability/overall_availability.png)](reports/repository_availability/overall_availability.png)

![Repository availability by modality](reports/repository_availability/availability_by_modality.png)

![Types of access provided by other artifact links](reports/repository_availability/other_artifact_access.png)

The 16 other links include **12 project websites** and one each for a model hub,
dataset hub, installable package, and benchmark portal. Ten project websites
display onward code links. These landing-page observations do not establish
that the destination repositories contain released implementation code.
See the [artifact details and access conditions](reports/repository_availability/other_artifact_details.csv).

“HTTP 404 / 410 — not found / gone” means that the supplied address was
not publicly accessible during the check. It can indicate a private, moved,
deleted, or incorrectly linked repository; it does not establish absence of code.
All 39 links in this category returned **HTTP 404** in the saved snapshot.

Modality memberships overlap. The charts use the original memberships from the
deduplication audit; the overall count includes each paper once. A missing link
means unknown availability, and an accessible page does not establish that
implementation code has been released.

### Deeper repository availability analysis

Browse [all images and analysis files](reports/repository_availability/) or open
an individual chart:

- [Overall availability (PNG)](reports/repository_availability/overall_availability.png) · [SVG](reports/repository_availability/overall_availability.svg)
- [Availability by modality (PNG)](reports/repository_availability/availability_by_modality.png) · [SVG](reports/repository_availability/availability_by_modality.svg)
- [Other artifact access (PNG)](reports/repository_availability/other_artifact_access.png)

Repository-link availability is summarized in
[`reports/repository_availability/README.md`](reports/repository_availability/README.md),
with a paper-level inventory and original-modality breakdown. This audit covers
listed links and public HTTP accessibility; it does not inspect repository code.
Run `make setup`, `make ingest`, `make test`, and `make report` to prepare,
validate, test, and regenerate the offline analysis. Optional live checks use
`python3 -m src.repository_availability --check-links`.

## Reviewer acceptance summary

The chart below summarizes the number of reviewers assigning an accepting score
(4–6) for each unique paper, together with the corresponding primary AC
decision. It highlights how AC reviewers used rebuttal invitations when the
initial reviewer consensus was weak.

![Reviewer acceptance versus primary AC decision](reports/review_acceptance/all_papers.png)

| Accepting reviewers | Papers | Invite for rebuttal | Rebuttal rate |
|---:|---:|---:|---:|
| 1 | 219 | 217 | **99.09%** |
| 2 | 648 | 522 | **80.56%** |
| 3 | 290 | 39 | **13.45%** |

The steep decline suggests that AC judgment matters most when reviewer support
is divided; these are descriptive associations, not proof that reviewer counts
alone caused the decision.

Four papers received no accepting score from any reviewer, yet the primary AC
decision was **Invite for Rebuttal** for all four:

- [Anatomy- and Site-Guided 3D Patch Diffusion for Robust MRI Harmonization](https://papers.miccai.org/miccai-2026/0052-Paper3157.html)
- [BRAIN: Bi-directional Motion Reasoning with Dynamic Memory Pruning for Surgical Video Segmentation](https://papers.miccai.org/miccai-2026/0116-Paper5179.html)
- [RAPO: Risk-Aware Anatomical Prior Optimization via Reinforcement Learning for CAC Detection in Rheumatoid Arthritis](https://papers.miccai.org/miccai-2026/0855-Paper1391.html)
- [Surgical Video Temporal Grounding](https://papers.miccai.org/miccai-2026/1013-Paper4572.html)

The underlying per-paper summary is available in
[`reports/review_acceptance/acceptance_summary.csv`](reports/review_acceptance/acceptance_summary.csv).
