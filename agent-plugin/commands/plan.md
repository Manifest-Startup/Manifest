---
description: Generate the investable plan for an idea - Business Model Canvas, pitch deck and PRD
argument-hint: "[idea title]"
---

Build the plan for my Manifest idea $ARGUMENTS (if none is named, list my `ideas` and ask which).

1. Check `ai_key_status` and `my_cost_preflight`; stop and explain if I have no key or I'm near my cap.
2. `enqueue_background_tasks` for the Business Model Canvas, pitch deck and PRD, then poll `generation_job` until it's done, telling me it's running.
3. Summarise each document in a few bullets and say what's weakest. Don't publish anything.
