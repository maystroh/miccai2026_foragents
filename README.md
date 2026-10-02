# miccai2026_foragents

This project maps MICCAI 2026 medical-imaging papers, reviews, and shared
research artifacts across modalities and clinical applications.

See [AGENTS.md](AGENTS.md) for repository conventions and
[docs/PROJECT_MEMORY.md](docs/PROJECT_MEMORY.md) for the current analysis state.

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

## Repository availability

**828 of 1,161 published papers (71.32%)** have publicly accessible repository
pages, based on checks from October 1, 2026. Repository code has not been analyzed.

[![Repository availability across the published corpus](reports/repository_availability/overall_availability.png)](reports/repository_availability/overall_availability.png)

See the [full repository availability analysis](reports/repository_availability/README.md)
for all charts, modality comparisons, artifact classifications, and paper-level data.
