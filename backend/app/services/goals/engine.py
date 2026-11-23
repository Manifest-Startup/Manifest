"""Create a goal from a plan, advance it, resume it, and report on it.

``advance`` is the only thing that runs steps. It is safe to call any number of times, from
anywhere (a request, an approval, an Open Media webhook, the background sweep): every state
change is a compare-and-swap, a step that sends something uses an idempotency key, and a
completed step never runs again. All state is in the database, so a goal survives restarts
and picks up where it stopped.
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from app.services.goals import capabilities, knowledge, policy, store
from app.services.goals.capabilities import REGISTRY, Context, Outcome, StepInputError
from app.services.integrations.open_media.client import (
    OpenMediaDisabled,
    OpenMediaError,
    OpenMediaNotLinked,
    OpenMediaUnavailable,
)
from app.utils.logger import logger

MAX_STEPS = 20
MAX_ATTEMPTS = 3
RETRY_BACKOFF = (timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=30))
STALE_RUNNING = timedelta(minutes=5)
DONE = "completed"
OPEN = ("proposed", "ready")
FINISHED = ("completed", "cancelled")
# Steps that can still move on their own (or with an approval).
LIVE = ("proposed", "ready", "running", "waiting_external", "awaiting_authorization")
_KEY = re.compile(r"^[a-z][a-z0-9_]{0,59}$")


class GoalError(ValueError):
    pass


# --- creating -------------------------------------------------------------------------------


def outreach_plan(
    handle: str, message: str, *, purpose: str = "", wait_days: int = 7
) -> list[dict[str, Any]]:
    """The standard plan for "reach out to someone and hear back"."""
    return [
        {"key": "find", "capability": "contact.resolve", "input": {"handle": handle}},
        {
            "key": "draft",
            "capability": "message.prepare",
            "input": {"to": "$steps.find.handle", "body": message, "purpose": purpose},
            "depends_on": ["find"],
        },
        {
            "key": "send",
            "capability": "message.send",
            "input": {"draft": "$steps.draft"},
            "depends_on": ["draft"],
        },
        {
            "key": "reply",
            "capability": "reply.await",
            "input": {"after": "$steps.send", "days": wait_days},
            "depends_on": ["send"],
        },
        {
            "key": "learn",
            "capability": "knowledge.record",
            "input": {"reply": "$steps.reply"},
            "depends_on": ["reply"],
        },
    ]


def _validate_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not steps:
        raise GoalError("A goal needs at least one step.")
    if len(steps) > MAX_STEPS:
        raise GoalError(f"Plans can have up to {MAX_STEPS} steps.")
    seen: set[str] = set()
    clean = []
    for position, step in enumerate(steps):
        key = str(step.get("key") or "").strip()
        if not _KEY.match(key) or key in seen:
            raise GoalError(f"Step keys must be unique snake_case names ('{key}').")
        capability = REGISTRY.get(str(step.get("capability") or ""))
        if capability is None:
            raise GoalError(
                f"Unknown capability '{step.get('capability')}'. Use one of: {', '.join(REGISTRY)}."
            )
        depends = [str(d) for d in step.get("depends_on") or []]
        unknown = [d for d in depends if d not in seen]
        if unknown:
            raise GoalError(f"Step '{key}' depends on '{unknown[0]}', which must come before it.")
        data = step.get("input") if isinstance(step.get("input"), dict) else {}
        missing = [name for name in capability.required if data.get(name) in (None, "")]
        if missing:
            raise GoalError(f"Step '{key}' ({capability.name}) needs {', '.join(missing)}.")
        refs = re.findall(r"\$steps\.([a-z0-9_]+)", repr(data))
        if any(ref not in depends for ref in refs):
            raise GoalError(f"Step '{key}' uses a step it doesn't depend on.")
        seen.add(key)
        clean.append(
            {
                "step_key": key,
                "position": position,
                "title": str(step.get("title") or capability.title)[:200],
                "capability": capability.name,
                "risk_tier": capability.tier,
                "depends_on": depends,
                "input": data,
            }
        )
    return clean


def _same_goal(db: Any, user_id: str, title: str, idea_id: str | None) -> dict[str, Any] | None:
    wanted = " ".join(title.casefold().split())
    open_goals = [
        g
        for g in store.select(db, store.GOALS, user_id=user_id)
        if g["status"] in ("active", "blocked")
    ]
    for goal in open_goals:
        if " ".join(str(goal.get("title") or "").casefold().split()) == wanted and (
            goal.get("idea_id") or None
        ) == (idea_id or None):
            return goal
    return None


def create_goal(
    db: Any,
    user_id: str,
    *,
    title: str,
    steps: list[dict[str, Any]],
    desired_outcome: str = "",
    success_criteria: list[str] | None = None,
    idea_id: str | None = None,
    source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Save a goal and its plan, then run whatever can run now. An active goal with the same
    title (and idea) is returned instead of a duplicate."""
    title = " ".join((title or "").split())[:200]
    if not title:
        raise GoalError("Name the goal.")
    existing = _same_goal(db, user_id, title, idea_id)
    if existing:
        return {**view(db, user_id, existing["id"]), "existing": True}
    rows = _validate_steps(steps)
    goal = store.insert(
        db,
        store.GOALS,
        {
            "user_id": user_id,
            "idea_id": idea_id,
            "title": title,
            "desired_outcome": (desired_outcome or "")[:2000],
            "success_criteria": {"items": [str(c)[:300] for c in success_criteria or []][:10]},
            "status": "active",
            "source": source or {},
            "version": 1,
        },
    )
    for row in rows:
        store.insert(
            db,
            store.TASKS,
            {
                **row,
                "goal_id": goal["id"],
                "user_id": user_id,
                "status": "proposed",
                "result": {},
                "verification": {},
                "attempts": 0,
            },
        )
    store.record_event(
        db,
        user_id,
        goal["id"],
        "goal.created",
        f"Goal: {title} ({len(rows)} steps)",
        {"source": source or {}},
    )
    return advance(db, user_id, goal["id"])


# --- running --------------------------------------------------------------------------------


def _goal(db: Any, user_id: str, goal_id: str) -> dict[str, Any]:
    goal = store.one(db, store.GOALS, id=goal_id, user_id=user_id)
    if goal is None:
        raise GoalError("No such goal.")
    return goal


def _tasks(db: Any, goal_id: str) -> list[dict[str, Any]]:
    rows = store.select(db, store.TASKS, goal_id=goal_id)
    rows.sort(key=lambda r: int(r.get("position") or 0))
    return rows


def _due(task: dict[str, Any]) -> bool:
    when = store.parse_time(task.get("next_check_at"))
    return when is None or when <= store.now()


def _classify(exc: Exception) -> tuple[str, str]:
    """('blocked'|'retry'|'failed', message safe to show)."""
    if isinstance(exc, StepInputError):
        return "failed", str(exc)
    if isinstance(exc, OpenMediaNotLinked | OpenMediaDisabled):
        return "blocked", str(exc)
    if isinstance(exc, OpenMediaUnavailable) or (
        isinstance(exc, OpenMediaError)
        and (exc.status is None or exc.status >= 500 or exc.status == 429)
    ):
        return "retry", str(exc)
    if isinstance(exc, OpenMediaError):
        return "failed", str(exc)
    return "retry", "Something went wrong running this step."


def _finish(
    db: Any, user_id: str, goal: dict[str, Any], task: dict[str, Any], outcome: Outcome
) -> None:
    changes: dict[str, Any] = {
        "result": outcome.result,
        "verification": outcome.verification,
        "last_error": outcome.error,
    }
    if outcome.status == "completed":
        changes.update(status=DONE, next_check_at=None)
        event, summary = "task.completed", f"Done: {task['title']}"
    elif outcome.status == "waiting":
        after = outcome.check_after or timedelta(minutes=15)
        changes.update(status="waiting_external", next_check_at=(store.now() + after).isoformat())
        event, summary = None, ""
    elif outcome.status == "blocked":
        changes.update(status="blocked", next_check_at=None)
        event, summary = "task.blocked", f"Needs you: {outcome.error}"
    else:
        changes.update(status="failed", next_check_at=None)
        event, summary = "task.failed", f"Failed: {task['title']}: {outcome.error}"
    store.cas_update(db, store.TASKS, task["id"], {"status": "running"}, changes)
    if event:
        store.record_event(
            db,
            user_id,
            goal["id"],
            event,
            summary,
            {"task_id": task["id"], "verification": outcome.verification},
            dedupe_key=f"{event}:{task['id']}:{task.get('attempts', 0)}",
        )


def _run(db: Any, user_id: str, goal: dict[str, Any], task: dict[str, Any], steps: dict) -> bool:
    """Run one step if it may run. Returns True if the step's state changed."""
    capability = REGISTRY[task["capability"]]
    ctx = Context(db=db, user_id=user_id, goal=goal, task=task, steps=steps)
    try:
        data = capabilities.resolve_input(task.get("input") or {}, steps)
        if policy.needs_approval(capability.tier):
            scope = capability.scope(ctx, data) if capability.scope else {"task": task["id"]}
            if not policy.is_authorized(db, user_id, task["id"], scope):
                described = capability.describe(ctx, data) if capability.describe else {}
                policy.request(
                    db,
                    user_id=user_id,
                    goal_id=goal["id"],
                    task=task,
                    scope=scope,
                    summary=described.get("summary", capability.title),
                    reason=described.get("reason", goal["title"]),
                    consequences=described.get("consequences", ""),
                )
                if task["status"] != "awaiting_authorization":
                    store.cas_update(
                        db,
                        store.TASKS,
                        task["id"],
                        {"status": task["status"]},
                        {"status": "awaiting_authorization"},
                    )
                    return True
                return False
    except StepInputError as exc:
        claimed = store.cas_update(
            db, store.TASKS, task["id"], {"status": task["status"]}, {"status": "running"}
        )
        if claimed:
            _finish(db, user_id, goal, claimed, Outcome("failed", error=str(exc)))
        return bool(claimed)

    rechecking = task["status"] == "waiting_external"
    attempts = int(task.get("attempts") or 0) + (0 if rechecking else 1)
    claimed = store.cas_update(
        db,
        store.TASKS,
        task["id"],
        {"status": task["status"]},
        {"status": "running", "attempts": max(attempts, 1)},
    )
    if claimed is None:
        return False  # another worker took it
    try:
        outcome = capability.run(ctx, data)
    except Exception as exc:  # noqa: BLE001 — classify, record, never hide
        kind, message = _classify(exc)
        logger.warning(
            "[goals] step failed",
            extra={
                "goal.id": goal["id"],
                "task.id": task["id"],
                "exception.type": type(exc).__name__,
            },
        )
        attempts = int(claimed.get("attempts") or 1)
        if kind == "retry" and attempts < MAX_ATTEMPTS:
            store.cas_update(
                db,
                store.TASKS,
                task["id"],
                {"status": "running"},
                {
                    "status": "ready",
                    "last_error": message,
                    "next_check_at": (store.now() + RETRY_BACKOFF[attempts - 1]).isoformat(),
                },
            )
            return True
        outcome = Outcome("blocked" if kind == "blocked" else "failed", error=message)
    _finish(db, user_id, goal, claimed, outcome)
    return not (rechecking and outcome.status == "waiting")  # still waiting is not progress


def _cancel_dependents(db: Any, user_id: str, goal_id: str, task_key: str) -> None:
    tasks = _tasks(db, goal_id)
    doomed = {task_key}
    for task in tasks:  # ordered, so transitive dependents are found in one pass
        if set(task.get("depends_on") or []) & doomed and task["status"] not in FINISHED:
            doomed.add(task["step_key"])
            store.cas_update(
                db, store.TASKS, task["id"], {"status": task["status"]}, {"status": "cancelled"}
            )


def _settle(db: Any, user_id: str, goal: dict[str, Any], tasks: list[dict[str, Any]]) -> None:
    if goal["status"] != "active" or not tasks:
        return
    done = [t for t in tasks if t["status"] == DONE]
    verified = all((t.get("verification") or {}).get("verified") for t in done)
    if (
        len(done) == len(tasks)
        and verified
        and store.cas_update(
            db, store.GOALS, goal["id"], {"status": "active"}, {"status": "achieved"}
        )
    ):
        store.record_event(
            db,
            user_id,
            goal["id"],
            "outcome.verified",
            f"Achieved: {goal['title']} (every step verified)",
            dedupe_key=f"outcome.verified:{goal['id']}",
        )
        return
    if any(t["status"] in LIVE for t in tasks):
        return
    # Nothing left that can run. A blocked or failed step waits for the person (retry_step
    # reopens the goal); if every unfinished step was cancelled (a declined approval), the
    # goal is closed rather than left looking active.
    stuck = [t for t in tasks if t["status"] in ("blocked", "failed")]
    status = "blocked" if stuck else "cancelled"
    if store.cas_update(db, store.GOALS, goal["id"], {"status": "active"}, {"status": status}):
        summary = (
            f"Blocked: {stuck[0]['title']} needs you"
            if stuck
            else f"Closed: {goal['title']} (nothing left to do after the decline)"
        )
        store.record_event(
            db,
            user_id,
            goal["id"],
            "goal.blocked" if stuck else "goal.closed",
            summary,
            dedupe_key=f"goal.settled:{goal['id']}:{status}",
        )


def advance(db: Any, user_id: str, goal_id: str, *, force_check: bool = False) -> dict[str, Any]:
    """Run every step that can run now, in dependency order, then return the goal's view."""
    goal = _goal(db, user_id, goal_id)
    if goal["status"] == "active":
        checked: set[str] = set()  # each wait is checked at most once per call
        for _ in range(MAX_STEPS * 2):
            tasks = _tasks(db, goal_id)
            steps = {t["step_key"]: t for t in tasks}
            progressed = False
            for task in tasks:
                deps_done = all(
                    steps.get(d, {}).get("status") == DONE for d in task["depends_on"] or []
                )
                waiting = task["status"] == "waiting_external"
                runnable = (
                    (task["status"] in OPEN and _due(task))
                    or task["status"] == "awaiting_authorization"
                    or (waiting and task["id"] not in checked and (force_check or _due(task)))
                )
                if waiting and runnable:
                    checked.add(task["id"])
                if deps_done and runnable and _run(db, user_id, goal, task, steps):
                    progressed = True
                    break
            if not progressed:
                break
        _settle(db, user_id, goal, _tasks(db, goal_id))
    return view(db, user_id, goal_id)


def decide_approval(
    db: Any, user_id: str, approval_id: str, *, approve: bool, scope_sha256: str, via: str
) -> dict[str, Any]:
    decided = policy.decide(
        db, user_id, approval_id, approve=approve, scope_sha256_seen=scope_sha256, via=via
    )
    task = store.one(db, store.TASKS, id=decided["task_id"], user_id=user_id)
    if task and not approve and task["status"] == "awaiting_authorization":
        store.cas_update(
            db,
            store.TASKS,
            task["id"],
            {"status": "awaiting_authorization"},
            {"status": "cancelled"},
        )
        _cancel_dependents(db, user_id, decided["goal_id"], task["step_key"])
    return advance(db, user_id, decided["goal_id"])


def cancel_goal(db: Any, user_id: str, goal_id: str) -> dict[str, Any]:
    goal = _goal(db, user_id, goal_id)
    if goal["status"] in ("active", "blocked"):
        store.cas_update(
            db, store.GOALS, goal_id, {"status": goal["status"]}, {"status": "cancelled"}
        )
        for task in _tasks(db, goal_id):
            if task["status"] not in FINISHED and task["status"] != "running":
                store.cas_update(
                    db, store.TASKS, task["id"], {"status": task["status"]}, {"status": "cancelled"}
                )
        for approval in store.select(db, store.APPROVALS, goal_id=goal_id, status="pending"):
            store.cas_update(
                db, store.APPROVALS, approval["id"], {"status": "pending"}, {"status": "superseded"}
            )
        store.record_event(db, user_id, goal_id, "goal.cancelled", f"Cancelled: {goal['title']}")
    return view(db, user_id, goal_id)


def retry_step(db: Any, user_id: str, goal_id: str, step_key: str) -> dict[str, Any]:
    """The person fixed what blocked a step (linked Open Media, waited longer): try it again."""
    goal = _goal(db, user_id, goal_id)
    if goal["status"] == "blocked":
        store.cas_update(db, store.GOALS, goal_id, {"status": "blocked"}, {"status": "active"})
    task = next((t for t in _tasks(db, goal_id) if t["step_key"] == step_key), None)
    if task is None or task["status"] not in ("blocked", "failed"):
        raise GoalError("Only a blocked or failed step can be retried.")
    store.cas_update(
        db,
        store.TASKS,
        task["id"],
        {"status": task["status"]},
        {"status": "ready", "attempts": 0, "last_error": None, "next_check_at": None},
    )
    return advance(db, user_id, goal_id)


def on_open_media_message(db: Any, conversation_id: str) -> int:
    """An Open Media message arrived: wake goals waiting on that conversation. Returns how many."""
    woken = 0
    for task in store.select(db, store.TASKS, status="waiting_external", capability="reply.await"):
        if (task.get("result") or {}).get("conversation_id") != conversation_id:
            continue
        try:
            advance(db, task["user_id"], task["goal_id"], force_check=True)
            woken += 1
        except Exception as exc:  # noqa: BLE001 — one goal must not stop the others
            logger.warning(
                "[goals] wake failed",
                extra={"goal.id": task["goal_id"], "exception.type": type(exc).__name__},
            )
    return woken


def sweep(db: Any, *, limit: int = 50) -> int:
    """Background pass: resume due waits and retries, and recover steps a crash left running."""
    stale_before = store.now() - STALE_RUNNING
    for task in store.select(db, store.TASKS, status="running"):
        updated = store.parse_time(task.get("updated_at"))
        if updated and updated < stale_before:
            # Safe to rerun: sends carry an idempotency key, reads have no side effects.
            store.cas_update(
                db, store.TASKS, task["id"], {"status": "running"}, {"status": "ready"}
            )
    goals: dict[str, str] = {}
    for status in ("waiting_external", "ready"):
        for task in store.select(db, store.TASKS, status=status):
            if _due(task) and len(goals) < limit:
                goals.setdefault(task["goal_id"], task["user_id"])
    for goal_id, user_id in goals.items():
        try:
            advance(db, user_id, goal_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[goals] sweep failed",
                extra={"goal.id": goal_id, "exception.type": type(exc).__name__},
            )
    return len(goals)


# --- reading --------------------------------------------------------------------------------


def _report(
    goal: dict[str, Any], tasks: list[dict[str, Any]], approvals: list[dict[str, Any]]
) -> dict[str, list[str]]:
    """Completed / in progress / waiting / needs you / next, only what's true right now."""
    pending = {a["task_id"]: a for a in approvals if a["status"] == "pending"}
    report: dict[str, list[str]] = {
        "completed": [],
        "in_progress": [],
        "waiting": [],
        "needs_you": [],
        "next": [],
    }
    for task in tasks:
        status = task["status"]
        if status == DONE:
            report["completed"].append(task["title"])
        elif status == "running":
            report["in_progress"].append(task["title"])
        elif status == "waiting_external":
            who = (task.get("result") or {}).get("waiting_for")
            report["waiting"].append(f"{task['title']}" + (f" from @{who}" if who else ""))
        elif status == "awaiting_authorization" and task["id"] in pending:
            report["needs_you"].append(f"Approve or decline: {pending[task['id']]['summary']}")
        elif status in ("blocked", "failed"):
            report["needs_you"].append(f"{task['title']}: {task.get('last_error') or status}")
    nxt = next((t for t in tasks if t["status"] in OPEN), None)
    if nxt and goal["status"] == "active":
        report["next"].append(nxt["title"])
    return report


def view(db: Any, user_id: str, goal_id: str) -> dict[str, Any]:
    goal = _goal(db, user_id, goal_id)
    tasks = _tasks(db, goal_id)
    approvals = store.select(db, store.APPROVALS, goal_id=goal_id, user_id=user_id)
    approvals.sort(key=lambda a: a.get("created_at") or "")
    events = store.select(db, store.EVENTS, order="created_at", goal_id=goal_id, user_id=user_id)
    for task in tasks:
        task["result"] = capabilities.fenced_reply(task.get("result") or {})
    return {
        "goal": goal,
        "tasks": tasks,
        "approvals": approvals,
        "events": events,
        "facts": knowledge.for_goal(db, user_id, goal_id),
        "report": _report(goal, tasks, approvals),
    }


def list_goals(db: Any, user_id: str, *, include_closed: bool = False) -> list[dict[str, Any]]:
    goals = store.select(db, store.GOALS, user_id=user_id)
    goals.sort(key=lambda g: g.get("updated_at") or "", reverse=True)
    return [g for g in goals if include_closed or g["status"] in ("active", "blocked")]


def pending_approvals(db: Any, user_id: str) -> list[dict[str, Any]]:
    rows = store.select(db, store.APPROVALS, user_id=user_id, status="pending")
    return [a for a in rows if not policy._expired(a)]
