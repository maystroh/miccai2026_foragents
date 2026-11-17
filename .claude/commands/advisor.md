---
description: Send a research idea or project plan to the miccai-advisor reviewer (Opus, high effort)
argument-hint: <path to idea/plan file, or the idea in words>
---

Use the Agent tool with `subagent_type: "miccai-advisor"` to review this idea or plan: $ARGUMENTS

Pass the file path (or the full idea text) and the run folder it belongs to. When the review comes back,
show the verdict and the fatal issues first, then list each reviewer-predicted weakness with the change it
suggests. Do not edit the plan yourself; ask the user which changes to accept.
