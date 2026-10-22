---
name: miccai2026-what-contribution-is-supported
description: Audit a paper's contribution claims against its reported experiments. Use to judge what the results support and where claims overreach.
---

# What contribution is actually supported?

## Input

Read the full paper when available, including supplementary material and reported limitations. If only an abstract or summary is available, label the audit provisional. Use the stable project paper ID when available.

## Method

1. Extract each distinct author claim: new method, better performance, mechanism, efficiency, robustness, generalization, or clinical utility. Quote only a short phrase when needed to disambiguate a claim.
2. For each claim, find its direct evidence: dataset and acquisition setting, comparison, ablation, metric, sample size, uncertainty, and evaluation design. Cite page, table, or figure.
3. Ask what alternative explanation remains: data leakage, unfair comparison, extra training data, selection bias, tuning on the test set, confounding, small sample, distribution shift, or an unmeasured outcome. Only raise alternatives that fit the study.
4. Classify the evidential status as `supported in tested setting`, `partly supported`, `not tested`, or `contradicted by reported results`. Explain the boundary, not just the label.
5. Treat novelty separately from empirical support. A paper's novelty claim is author-reported unless a literature comparison has actually been performed.

## Output

Start with a one-sentence **Supported contribution** limited to the studied setting. Then provide a compact table:

| Author claim | Evidence and provenance | Status | Boundary or missing test |
| --- | --- | --- | --- |

End with **What remains unknown** (up to three high-impact uncertainties) and **Confidence in this audit** (high/medium/low, based on source completeness and reporting quality). Do not equate statistical significance with practical or clinical value. Do not pool metrics across datasets or protocols without justification.

