# Run folder templates

## plan.md

```markdown
# <run title>

- Started: <date>
- Question: <the research question in one sentence>
- Area: <topic / task / anatomy, or open>
- What we can do: <data we hold, compute, months available>
- Contribution wanted: <method | benchmark | clinical study | dataset>
- Not worth it if: <the user's own deal-breakers>
- Stopping rule: at most 3 rounds of candidate generation
```

## log.md

```markdown
# Log

## Step <n>: <name> (<date>)
- Question: <what we wanted to know>
- Tool / query: `<tool or CLI call>`
- Result: <what came back, with counts and paper_ids>
- Decision: <kept / dropped / next> because <reason>
```

## evidence-map.md

```markdown
| Claim | Source (paper_id + section, or query) | Relation | Notes |
|---|---|---|---|
```

## ideas/<nn>-<slug>.md

```markdown
# <idea in one sentence>

- Status: candidate | reviewed | shortlisted | dropped
- Outside-MICCAI novelty: not checked (do before committing)

## Evidence of the gap
<counts from tools; limitations and review quotes with paper_ids>

## Closest MICCAI 2026 work
| paper_id | title | what it already does | what it lacks |

## Plan
- Data: <public datasets, splits>
- Baselines: <what the closest papers report or use>
- Method sketch:
- Evaluation: <metrics this field uses here; external test>
- First two weeks:

## How it could fail
- Boring explanation:
- Kill result:
- Untouched test:
```

## decision-brief.md

```markdown
# Decision brief

| Idea | Verdict | Why | Next task |
|---|---|---|---|

Outside-MICCAI novelty: not checked for any idea; first task for each shortlisted idea.
Open questions:
```
