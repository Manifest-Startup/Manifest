"""What a reply asks for, needs, promises or signals, found by plain rules, never by a model.

Each finding is a quoted sentence from the reply, saved as an ``inferred`` fact (confidence
0.3) about the person who wrote it. That keeps three things apart that the master spec says
must stay apart: what they literally said (the ``external_claim`` reply fact), what Manifest
thinks it means (these inferred facts), and what the person has confirmed (a
``stated_by_user`` fact, made with ``correctKnowledge``). Nothing here turns a customer's
wish into a product requirement or a commitment on the person's behalf.

The text is untrusted. The rules only match and quote it; nothing in it is executed or
followed.
"""

from __future__ import annotations

import re
from typing import NamedTuple

MAX_FINDINGS = 8
MAX_SENTENCE = 300

_SENTENCES = re.compile(r"(?<=[.!?])\s+|\n+")


class Finding(NamedTuple):
    predicate: str  # needs | asked | offered | interest | declined
    quote: str


_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "declined",
        re.compile(
            r"\b(not interested|no thanks|not a (good )?fit|not for us|pass on this|"
            r"not (right )?now|unsubscribe|stop (messaging|contacting))\b",
            re.I,
        ),
    ),
    (
        "needs",
        re.compile(
            r"\b(we|i|they|our team)\s+(would\s+)?(really\s+)?(need|require|must have)\b|"
            r"\bneeds? (support for|to support|integration)\b|"
            r"\b(would|could) (consider|use|buy|try) (this|it)\b.*\b(if|once|as long as)\b|"
            r"\bonly if\b|\bas long as\b|\bif it (supported|had|could)\b|\bdeal[- ]?breaker\b",
            re.I,
        ),
    ),
    (
        "offered",
        re.compile(
            r"\b(i('ll| will)|we('ll| will)|happy to|glad to|let me|i can|we can)\b"
            r".*\b(send|share|intro(duce)?|call|meet|schedule|try|pilot|test|connect)\b",
            re.I,
        ),
    ),
    (
        "interest",
        re.compile(
            r"\b(interested|sounds (good|great|interesting)|let'?s (talk|chat|meet)|"
            r"would love|keen to|curious)\b",
            re.I,
        ),
    ),
)


def _sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENTENCES.split(text or "")]
    return [p[:MAX_SENTENCE] for p in parts if len(p) > 3]


def extract(text: str) -> list[Finding]:
    """Sentences that ask, need, offer, show interest or decline, in reply order, deduplicated.

    One sentence can match more than one rule ("Interested, but we need X" is both interest
    and a need): each match is kept, because they lead to different next steps."""
    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()
    for sentence in _sentences(text):
        clauses = [c.strip() for c in re.split(r",\s*but\s+|;\s*", sentence) if c.strip()]
        for clause in clauses or [sentence]:
            matched = [name for name, rule in _RULES if rule.search(clause)]
            if clause.endswith("?"):
                matched.append("asked")
            for name in matched:
                key = (name, clause.lower())
                if key not in seen:
                    seen.add(key)
                    findings.append(Finding(name, clause))
        if len(findings) >= MAX_FINDINGS:
            break
    return findings[:MAX_FINDINGS]
