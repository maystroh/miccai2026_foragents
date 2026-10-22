# Skill ideas for a paper reasoning commons

The three initial skills cover **orientation**, **claim checking**, and **decisive testing**. The next skills should address cognitive work that researchers repeatedly do while reading, comparing, and planning studies. The aim is to expose reasoning and uncertainty so a person can challenge either one.

## Candidate skills

| Research move | User question | Useful output |
| --- | --- | --- |
| Triage | Is this paper relevant to my question? | Relevance reasons, exclusions, and source scope |
| Terminology | What do these terms mean here? | Paper-specific glossary with definitions and citations |
| Study map | What was measured, on whom, and under what conditions? | Dataset, protocol, split, comparator, and outcome map |
| Figure reading | What does this figure actually show? | Axes, units, comparison, and limitations |
| Methods reconstruction | Could I reproduce the method from this text? | Ordered steps, parameters, and missing details |
| Claim audit | Which claims outpace the experiments? | Claim-to-evidence table with boundaries |
| Baseline audit | Is the comparison fair? | Training-data, compute, tuning, and metric parity check |
| Validation audit | Could leakage or selection explain the result? | Split and independence assessment |
| Metric interpretation | Does this number matter? | Metric meaning, uncertainty, and practical threshold |
| Error analysis | Where does the method fail? | Failure modes by subgroup, anatomy, protocol, or site |
| Causal alternatives | What else could explain the finding? | Plausible rival explanations and discriminating tests |
| Robustness | Will this work outside the test setting? | Shift dimensions and evidence gaps |
| Clinical path | What would be needed before clinical use? | Workflow, prospective evidence, safety, and monitoring gaps |
| Replication plan | What is the smallest faithful replication? | Data, code, configuration, and result checklist |
| Cross-paper comparison | Are these results genuinely comparable? | Common axes and reasons comparison is invalid |
| Evidence synthesis | What does a set of papers collectively establish? | Convergent findings, conflicts, and uncertainty |
| Contradiction analysis | Why do two papers disagree? | Dataset, protocol, design, and measurement hypotheses |
| Research gap | Which unanswered question is worth testing? | Gap with importance and tractable next step |
| Experiment design | What result would change my mind? | Prespecified test and outcome map |
| Review rehearsal | What would a rigorous reviewer ask? | Major questions linked to claims and evidence |
| Lab discussion | What should we debate in journal club? | Three questions with opposing interpretations |
| Decision memo | Should we build on this method? | Recommendation, assumptions, evidence, and stop conditions |

## Design principles

- **Questions before summaries.** A skill is strongest when it helps a researcher make a decision or find the next useful question.
- **Source boundaries.** The output should say whether it used a full paper, supplement, abstract, metadata record, or several papers.
- **Specificity over scorecards.** A single numerical paper-quality score conceals which claim is weak and why.
- **Disagreement is useful data.** Let contributors record alternative interpretations and the evidence that would resolve them.
- **Portable outputs.** Reuse stable paper IDs and controlled vocabularies so results from different skills can connect without repeating extraction.
- **Human review at consequential edges.** Novelty, clinical utility, risk of bias, and research priorities benefit from expert review and explicit uncertainty.

## Suggested build order

1. **Study map** and **validation audit**: they provide the structured facts that the three initial skills need.
2. **Cross-paper comparison**: it turns a collection into a research instrument while making non-comparability visible.
3. **Contradiction analysis** and **evidence synthesis**: they reveal where a new experiment is most valuable.
4. **Decision memo**: it connects evidence to a research team's actual next action.

For each new skill, test it on a clear paper, a poorly reported paper, and a paper with a tempting overclaim. Review whether citations support the output and whether a scientist can identify what would change the answer.
