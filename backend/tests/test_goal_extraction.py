"""Replies → what they need, ask, offer or decline, by plain rules (ADR 0020, spec Test E)."""

from __future__ import annotations

import pytest
from app.services.goals.extraction import extract


def _by(text):
    return [(f.predicate, f.quote) for f in extract(text)]


def test_interest_with_a_condition_is_both():
    found = _by(
        "We would consider using this if it supported integration with our internal systems."
    )
    assert (
        "needs",
        "We would consider using this if it supported integration with our internal systems.",
    ) in found


def test_interest_but_need_is_split_into_clauses():
    found = _by("Interested, but we need support for our internal messaging system.")
    assert ("interest", "Interested") in found
    assert ("needs", "we need support for our internal messaging system.") in found


@pytest.mark.parametrize(
    ("text", "predicate"),
    [
        ("What does it cost per seat?", "asked"),
        ("Happy to intro you to our ops lead.", "offered"),
        ("I can send you our requirements doc tomorrow.", "offered"),
        ("Not interested, thanks.", "declined"),
        ("Sounds great, let's talk next week.", "interest"),
    ],
)
def test_each_kind(text, predicate):
    assert predicate in [p for p, _ in _by(text)]


def test_small_talk_finds_nothing():
    assert extract("Thanks for the note. Hope you had a good weekend.") == []


def test_quotes_are_verbatim_and_bounded():
    text = " ".join(f"Do you support feature {i}?" for i in range(20))
    found = extract(text)
    assert len(found) == 8 and all(f.quote.startswith("Do you support feature") for f in found)
