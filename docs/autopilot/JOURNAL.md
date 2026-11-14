# Autopilot Journal

Append-only run log. One line per autopilot run, newest at the bottom. Written
by `run_autopilot_agent.py`; summarized weekly by `autopilot-retro.yml` into
the Learnings section of `PLAYBOOK.md`.

Format: `` `<utc-ts>` #<issue> — **<action>** · model `<model>` · $<cost> · <pr-url> · <reason> ``

Actions: `pr_opened`, `declined`, `guard_rejected`, `checks_failed`.

---
