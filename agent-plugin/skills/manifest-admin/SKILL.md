---
name: manifest-admin
description: "Manifest platform administration for admins only: platform AI cost, agent runs, production smoke tests, voice-agent tests and user roles. Use only when the signed-in person is a Manifest admin and asks about platform health or roles."
---

# Administration (admins only)

Everyone else gets a permission error from these tools; say so plainly instead of retrying.

- `admin_cost_overview`: platform AI cost over a window.
- `admin_agent_runs`: recent agent runs across users (filter by kind and status).
- `admin_production_test_stats`: production smoke-test pass rates.
- `admin_voice_test_runs`, `admin_voice_test_stats`, `admin_run_voice_test_case`: voice-agent quality.
- `admin_set_user_role` changes a user's role (needs `confirm: true`; name the user and the new role).

Never paste other users' personal data into the conversation beyond what the question needs.
