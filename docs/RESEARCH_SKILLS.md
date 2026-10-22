# Research reasoning skills

These skills are small, reusable workflows for reading and reasoning about scientific papers. They are designed to help a researcher reach a better question or decision, not to replace expert judgment. Each skill can run on one paper supplied by the user or on a paper indexed by this project.

## Start here

| Question | Skill | Main output |
| --- | --- | --- |
| Understand this paper in one minute. | [`miccai2026-understand-paper-one-minute`](../.agents/skills/miccai2026-understand-paper-one-minute/SKILL.md) | A short, sourced orientation |
| What contribution is actually supported? | [`miccai2026-what-contribution-is-supported`](../.agents/skills/miccai2026-what-contribution-is-supported/SKILL.md) | A claim-to-evidence audit |
| What experiment would change the conclusion? | [`miccai2026-experiment-that-changes-conclusion`](../.agents/skills/miccai2026-experiment-that-changes-conclusion/SKILL.md) | A decisive experiment and outcome map |

Use them as a sequence if helpful: **orient → audit → design a test**. A user can also invoke any skill alone, and each output should stand on its own.

## Shared evidence contract

Every skill should:

1. Identify the paper by a stable ID and state which source material was actually read. Do not present an abstract-only analysis as a full-paper review.
2. Ground factual claims in a page, table, figure, or other precise source location. Label author-reported facts and derived interpretations separately.
3. Preserve dataset, anatomy, imaging modality, acquisition protocol, comparator, metric, and evaluation design when they affect the claim.
4. Say `not reported` or `unclear` when evidence is missing. Avoid invented numbers, protocols, prior-art comparisons, or clinical implications.
5. Keep legally obtained PDFs, patient data, credentials, checkpoints, and large datasets out of the repository. Store metadata, citations, lawful retrieval instructions, and original notes instead.

## Adding a skill

Create `.agents/skills/<short-action-name>/SKILL.md` with YAML frontmatter (`name` and a trigger-oriented `description`). State its input, steps, and output. Make the output answer a real research decision. Include an example paper ID and a small anonymized example output when the workflow is mature. Review an example against the paper before proposing a skill for broad use. Record disagreements or classification uncertainty instead of hiding them.

The [skill ideas](RESEARCH_SKILL_IDEAS.md) file is a public backlog, not a ranking of research topics.
