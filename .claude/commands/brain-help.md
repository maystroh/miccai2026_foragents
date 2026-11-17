---
description: Show every MICCAI brain tool, what it answers, and an example for each
---

Call the `brain_guide` tool of the miccai-brain MCP server. If it is not connected, run
`python -m src.miccai_brain guide` from the repo root instead.

Show the result to the user as it comes, grouped (Find, Map, Gaps, Problems, Help), as compact tables:
tool, what it answers, example question. Then list the kinds, the typical sequences and the extras.
Do not add commentary. End by asking which question they want to start with.
