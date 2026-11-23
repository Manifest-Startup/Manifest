"""Goals that run (ADR 0020): a person's goal, its dependency-aware plan, approvals, and results.

- ``store``: rows and the event log (``goals``, ``goal_tasks``, ``approval_requests``,
  ``knowledge_facts``, ``goal_events``).
- ``capabilities``: what a step can do, with its risk tier, inputs, verification and handler.
- ``policy``: risk tiers and approvals, enforced here, at the execution boundary, not by a
  model's judgement.
- ``knowledge``: facts learned along the way, with provenance, confidence and corrections.
- ``engine``: create a goal from a plan, advance it, resume it on approvals and replies, and
  report progress.
"""
