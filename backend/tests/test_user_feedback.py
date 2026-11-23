"""report_feedback: one GitHub issue per problem, more people counted, nothing private posted."""

import json
import re

import httpx
import pytest
from app.services.operations import user_feedback as uf


class FakeGitHub:
    """Just enough of the GitHub REST API: issues, search, labels, comments."""

    def __init__(self, issues=None):
        self.issues = {i["number"]: i for i in (issues or [])}
        self.comments: dict[int, list[str]] = {}
        self.labels: set[str] = set()
        self.next = max(self.issues, default=0) + 1

    def _issue(self, number, title, body="", labels=()):
        return {
            "number": number,
            "title": title,
            "body": body,
            "state": "open",
            "html_url": f"https://github.com/o/r/issues/{number}",
            "labels": [{"name": n} for n in labels],
        }

    def handler(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        if path == "/search/issues":
            q = request.url.params["q"]
            words = [w for w in q.split() if ":" not in w and w != "OR"]
            any_word = " OR " in q
            hits = [
                i
                for i in self.issues.values()
                if i["state"] == "open"
                and (any if any_word else all)(w in i["title"].lower() for w in words)
            ]
            return httpx.Response(200, json={"items": hits})
        if path.endswith("/labels") and method == "GET":
            return httpx.Response(200, json=[{"name": n} for n in self.labels])
        if path.endswith("/labels") and method == "POST":
            self.labels.add(json.loads(request.content)["name"])
            return httpx.Response(201, json={})
        if path.endswith("/issues") and method == "GET":
            wanted = request.url.params.get("labels")
            return httpx.Response(
                200,
                json=[
                    i
                    for i in self.issues.values()
                    if i["state"] == "open"
                    and (not wanted or wanted in [x["name"] for x in i["labels"]])
                ],
            )
        if path.endswith("/issues") and method == "POST":
            data = json.loads(request.content)
            issue = self._issue(self.next, data["title"], data["body"], data["labels"])
            self.issues[self.next] = issue
            self.next += 1
            return httpx.Response(201, json=issue)
        match = re.search(r"/issues/(\d+)(/comments)?$", path)
        if match:
            number = int(match.group(1))
            if number not in self.issues:
                return httpx.Response(404, json={})
            if match.group(2):
                self.comments.setdefault(number, []).append(json.loads(request.content)["body"])
                return httpx.Response(201, json={})
            if method == "PATCH":
                self.issues[number].update(json.loads(request.content))
            return httpx.Response(200, json=self.issues[number])
        return httpx.Response(404, json={"path": path})


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("MANIFEST_GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("MANIFEST_FEEDBACK_REPO", "o/r")
    monkeypatch.setattr(uf.rate_limit_service, "allow", lambda *a, **k: True)


async def _report(gh, **kwargs):
    async with httpx.AsyncClient(transport=httpx.MockTransport(gh.handler)) as client:
        args = {"user_id": "u1", "kind": "bug", "title": "Pitch deck export fails on Safari"}
        args.update(kwargs)
        return await uf.UserFeedbackService().report(client=client, **args)


@pytest.mark.asyncio
async def test_new_feedback_creates_one_labelled_issue_with_redaction():
    gh = FakeGitHub()
    result = await _report(
        gh, details="Mail me at jo@example.com or +1 415 555 0100", source="voice"
    )
    assert result.status == "created" and result.reporters == 1
    issue = gh.issues[result.issue_number]
    assert {"bug", "user-feedback", "source:voice"} <= {x["name"] for x in issue["labels"]}
    assert "jo@example.com" not in issue["body"] and "555" not in issue["body"]
    assert "Reported by 1 person" in issue["body"]
    assert "u1" not in issue["body"]


@pytest.mark.asyncio
async def test_same_problem_from_another_person_is_added_not_duplicated():
    gh = FakeGitHub()
    first = await _report(gh)
    second = await _report(
        gh, user_id="u2", title="Pitch deck export fails in Safari", details="Same for me"
    )
    assert second.status == "added" and second.issue_number == first.issue_number
    assert second.reporters == 2 and len(gh.issues) == 1
    assert "Reported by 2 people" in gh.issues[first.issue_number]["body"]
    assert "Another person reported this" in gh.comments[first.issue_number][0]
    assert "> Same for me" in gh.comments[first.issue_number][0]


@pytest.mark.asyncio
async def test_same_person_twice_counts_once():
    gh = FakeGitHub()
    first = await _report(gh)
    again = await _report(gh)
    assert again.status == "already_reported" and again.reporters == 1
    assert first.issue_number == again.issue_number and not gh.comments


@pytest.mark.asyncio
async def test_partial_match_asks_the_agent_then_duplicate_of_joins_it():
    gh = FakeGitHub()
    gh.issues[7] = gh._issue(7, "Voice agent is slow to answer")
    maybe = await _report(gh, user_id="u2", kind="improvement", title="Voice replies take long")
    assert maybe.status == "possible_duplicates" and maybe.candidates[0]["number"] == 7
    assert len(gh.issues) == 1  # nothing filed yet

    joined = await _report(gh, user_id="u2", kind="improvement", title="x voice", duplicate_of=7)
    # An issue filed by hand counts its author, plus this person.
    assert joined.status == "added" and joined.reporters == 2

    new = await _report(
        gh, user_id="u3", kind="improvement", title="Voice replies take long", force_new=True
    )
    assert new.status == "created" and len(gh.issues) == 2


@pytest.mark.asyncio
async def test_unrelated_feedback_is_new_and_errors_are_friendly(monkeypatch):
    gh = FakeGitHub()
    gh.issues[3] = gh._issue(3, "Dark mode for the pitch deck")
    result = await _report(gh, kind="enhancement", title="Export cap table to CSV")
    assert result.status == "created"

    with pytest.raises(uf.FeedbackError, match="no issue #99"):
        await _report(gh, duplicate_of=99)
    with pytest.raises(uf.FeedbackError, match="Kind must be"):
        await _report(gh, kind="rant")
    monkeypatch.delenv("MANIFEST_GITHUB_TOKEN")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(uf.FeedbackError, match="isn't set up"):
        await _report(gh)


def test_similarity_and_marker_round_trip():
    assert uf.similarity("Pitch deck export fails", "pitch deck exports failing") >= uf.STRONG_MATCH
    assert uf.similarity("Pitch deck export fails", "Add dark mode") < 0.3
    body = uf.write_marker("Hello", ["a"])
    body = uf.write_marker(body, ["a", "b"])
    assert uf.read_marker(body)["reporters"] == ["a", "b"]
    assert body.count("Reported by") == 1 and "Reported by 2 people" in body


@pytest.mark.asyncio
async def test_graphql_mutation_requires_sign_in_and_maps_result(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.graphql.resolvers import survey as resolver
    from app.graphql.schema import Mutation
    from app.graphql.types.survey import ReportFeedbackInput

    async def fake_report(**kwargs):
        assert kwargs["user_id"] == "user-9" and kwargs["source"] == "voice"
        return uf.FeedbackResult(status="created", issue_number=5, reporters=1, message="ok")

    monkeypatch.setattr(resolver, "get_current_user_id", lambda request: "user-9")
    monkeypatch.setattr(resolver.user_feedback_service, "report", fake_report)
    info = SimpleNamespace(context={"request": MagicMock(), "db": MagicMock()})
    out = await Mutation().report_feedback(
        info, ReportFeedbackInput(kind="bug", title="Broken thing", source="voice")
    )
    assert out.status == "created" and out.issue_number == 5
