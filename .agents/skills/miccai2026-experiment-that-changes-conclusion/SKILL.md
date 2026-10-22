---
name: miccai2026-experiment-that-changes-conclusion
description: Design a follow-up experiment with outcomes that could strengthen or reverse a paper's conclusion. Use for research planning after evidence review.
---

# What experiment would change the conclusion?

## Input

Start from a specific paper and a specific current conclusion. Read the evaluation details and limitations before proposing a test. Identify the paper with its stable project ID when available. If essential methods or data details are unavailable, state the assumptions that make the proposed test possible.

## Method

1. Write the current conclusion narrowly, naming the population or dataset, modality and protocol, comparator, outcome, and evaluation design.
2. Identify the most decision-relevant uncertainty. Prefer one whose resolution could change the conclusion, not merely add another benchmark number.
3. Propose one primary experiment with a prespecified hypothesis, target population or dataset, comparator, controlled variables, primary outcome, and analysis plan. Include an appropriate held-out, external, temporal, or prospective validation design when the claim requires it.
4. Specify what result would strengthen the conclusion, what result would weaken or reverse it, and what result would leave it unresolved. Give quantitative thresholds only when the paper or domain supplies a justified threshold; otherwise state the threshold as a decision to preregister.
5. Note feasibility, data access, ethics, likely confounders, and the minimum checks needed to trust the result. Do not imply patient data or copyrighted material can be redistributed.

## Output

- **Current conclusion and evidence:** One or two sentences with page/table/figure provenance.
- **Decisive uncertainty:** The specific unresolved question.
- **Proposed experiment:** Design, comparison, primary outcome, controls, and analysis.
- **Outcome map:** Strengthens / weakens or reverses / inconclusive.
- **Why this test matters:** Explain the causal link between the uncertainty and the conclusion.
- **Practical constraints:** Data, ethics, power or sample-size considerations, and remaining limitations.

Offer at most two alternative experiments if the primary one is infeasible. Keep proposed work distinct from experiments the paper already performed.

