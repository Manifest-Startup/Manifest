"""Each idea's knowledge graph: source passages, concepts, cited documents (ADR 0006).

Pure functions, no AI and no stored state, so the graph is always current: it is rebuilt from
the idea note, the founder's qualification answers and the generated documents every time it
is read. The same output feeds the app (``ideaKnowledgeGraph``) and the local vault
(``vault.build_files``), so both show identical ``[[wiki-links]]``:

- **Passages**: the idea note split into sentences (``^p1``…) and the founder's own interview
  answers (``^a1``…). They become Obsidian block ids in the idea note.
- **Concepts**: recurring phrases from the note, the answers and the documents, plus the
  required skills. Each concept links to every one of the person's ideas that mentions it,
  which is what makes the network dense across ideas.
- **Citations**: every substantial line of a generated document gets
  ``[[<idea note>#^p3|↩]]`` pointing at the passage it draws on (falling back to the note
  itself), and the first mention of each concept per section links to its concept note.
"""

from __future__ import annotations

import html
import json
import math
import re
from collections import Counter
from typing import Any

ROOT = "Manifest"
CITE_LABEL = "↩"
MAX_CONCEPTS = 24
MIN_CITE_WORDS = 5

_TOKEN = re.compile(r"[a-z][a-z0-9'’-]*[a-z0-9]|[a-z]")
_TAGS = re.compile(r"<[^>]+>")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'“(])")
_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
# Spans we never rewrite: existing wiki links, Markdown links/images, inline code, URLs.
_PROTECTED = re.compile(r"(\[\[[^\]]*\]\]|!?\[[^\]]*\]\([^)]*\)|`[^`]*`|https?://\S+)")
_UNSAFE = re.compile(r'[\\/:*?"<>|#^\[\]\n\r\t]+')

_STOP = frozenset(
    """
    a about above across after again against all almost also although always am among an and
    another any anyone anything are around as at away back be because become been before being
    below between both but by can cannot could did do does doing done down during each either
    else enough even ever every few first for from further get gets getting give given go goes
    going good got great had has have having he her here hers him his how however i if in into
    is it its itself just keep know last least less let like likely made make makes making many
    may me might more most much must my need needs new next no nor not now of off often on once
    one only or other others our ours out over own per perhaps rather really same see seem
    should since so some something still such than that the their theirs them then there these
    they thing things this those though through thus to too toward towards under until up upon
    us use used uses using very via want wants was way ways we well were what whatever when
    where whether which while who whom whose why will with within without would yet you your
    yours able across already etc i.e e.g vs per year years month months day days time times
    lot lots kind sort part parts set sets based include includes including provide provides
    help helps allow allows people person idea ideas startup company product products user users
    customer customers business solution solutions problem problems market markets value
    slide section document draft key main core simple easy better best high low large small
    minute minutes hour hours week weeks public private free cheap real live late early whole
    cover covers reach reaches arrive arrives take takes turn turns lack lacks learn already
    able door level levels based full total real-time actual current today tomorrow approach
    """.split()
)


# -- text helpers -----------------------------------------------------------------------


def plain(text: Any) -> str:
    """Note text without HTML tags or entities (the editor may store either)."""
    return html.unescape(_TAGS.sub(" ", str(text or "")))


def _stem(word: str) -> str:
    word = word.replace("’", "'").removesuffix("'s")
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def _tokens(text: str) -> list[str]:
    return [_stem(t) for t in _TOKEN.findall(text.lower())]


def content_words(text: str) -> set[str]:
    return {t for t in _tokens(text) if t not in _STOP and len(t) > 2 and not t.isdigit()}


def note_name(text: str, fallback: str = "Untitled") -> str:
    name = _UNSAFE.sub(" ", str(text or "")).strip().strip(".")
    return re.sub(r"\s+", " ", name)[:120] or fallback


def concept_path(label: str) -> str:
    return f"{ROOT}/Concepts/{note_name(label.title())}"


# -- passages ---------------------------------------------------------------------------


def source_passages(description: Any, answers: list[str]) -> list[dict[str, str]]:
    """The idea note as sentence passages (``p1``…) plus interview answers (``a1``…)."""
    passages: list[dict[str, str]] = []
    for line in plain(description).splitlines():
        line = line.strip().lstrip("-*•> ").strip()
        for sentence in _SENTENCE.split(line):
            if len(content_words(sentence)) >= 2:
                passages.append(
                    {"id": f"p{len(passages) + 1}", "kind": "note", "text": sentence.strip()}
                )
    count = 0
    for answer in answers:
        text = re.sub(r"\s+", " ", plain(answer)).strip()
        if len(content_words(text)) >= 2:
            count += 1
            passages.append({"id": f"a{count}", "kind": "answer", "text": text})
    return passages


def interview_answers(sessions: list[dict[str, Any]]) -> list[str]:
    """The founder's own words from qualification interviews, oldest first."""
    answers: list[str] = []
    for session in sorted(sessions, key=lambda s: str(s.get("created_at") or "")):
        if session.get("initial_idea_text"):
            answers.append(str(session["initial_idea_text"]))
        turns = session.get("transcript") or []
        if isinstance(turns, str):
            try:
                turns = json.loads(turns)
            except ValueError:
                turns = []
        answers += [
            str(t.get("content") or "")
            for t in turns
            if isinstance(t, dict) and t.get("role") != "assistant"
        ]
    seen: set[str] = set()
    return [a for a in answers if a.strip() and not (a.strip() in seen or seen.add(a.strip()))]


# -- concepts ---------------------------------------------------------------------------


def _candidate_phrases(text: str) -> Counter[tuple[str, ...]]:
    """1–3 word runs with no stopword at either end, counted."""
    counts: Counter[tuple[str, ...]] = Counter()
    for chunk in re.split(r"[.,;:!?()\[\]{}\n|/\"“”]+", text.lower()):
        words = [_stem(w) for w in _TOKEN.findall(chunk)]
        for n in (1, 2, 3):
            for i in range(len(words) - n + 1):
                gram = tuple(words[i : i + n])
                if any(w in _STOP or w.isdigit() for w in gram):
                    continue
                if n == 1 and len(gram[0]) < 4:
                    continue
                if any("'" in w for w in gram):
                    continue
                counts[gram] += 1
    return counts


def extract_concepts(
    core_text: str, extra_text: str = "", skills: list[str] | None = None, limit: int = MAX_CONCEPTS
) -> list[str]:
    """Concept labels for one idea, strongest first.

    ``core_text`` is the founder's own words (note + answers); anything it repeats, or any
    multi-word phrase it shares with the documents (``extra_text``), is a concept.
    """
    core = _candidate_phrases(core_text)
    extra = _candidate_phrases(extra_text)
    scored: dict[tuple[str, ...], float] = {}
    for gram, n in core.items():
        total = n + extra.get(gram, 0)
        if len(gram) == 1 and total < 3:
            continue
        if len(gram) == 2 and total < 2:
            continue
        if len(gram) == 3 and total < 3:
            continue
        scored[gram] = total * (1 + 0.6 * (len(gram) - 1)) + (1.5 if n > 1 else 0)
    # A shorter phrase that only ever appears inside a kept longer one adds nothing.
    for gram in sorted(scored, key=len, reverse=True):
        for shorter in list(scored):
            if (
                len(shorter) < len(gram)
                and _contains(gram, shorter)
                and core[shorter] + extra.get(shorter, 0) <= core[gram] + extra.get(gram, 0)
            ):
                scored.pop(shorter, None)
    ranked = [" ".join(g) for g, _ in sorted(scored.items(), key=lambda kv: (-kv[1], kv[0]))]
    labels = [s.strip() for s in skills or [] if s.strip()]
    keys = {key(label) for label in labels}
    for phrase in ranked:
        if key(phrase) not in keys:
            labels.append(phrase)
            keys.add(key(phrase))
        if len(labels) >= limit:
            break
    return labels[: max(limit, len(skills or []))]


def _contains(longer: tuple[str, ...], shorter: tuple[str, ...]) -> bool:
    n = len(shorter)
    return any(longer[i : i + n] == shorter for i in range(len(longer) - n + 1))


def key(label: str) -> str:
    return " ".join(_tokens(label))


def mentions(text: str, label: str) -> bool:
    words = _tokens(label)
    if not words:
        return False
    tokens = _tokens(text)
    n = len(words)
    return any(tokens[i : i + n] == words for i in range(len(tokens) - n + 1))


# -- citations --------------------------------------------------------------------------


def best_passage(line: str, passages: list[dict[str, str]]) -> dict[str, str] | None:
    words = content_words(line)
    if not words:
        return None
    best, best_score = None, 0.0
    for passage in passages:
        pwords = content_words(passage["text"])
        shared = len(words & pwords)
        if shared < 2:
            continue
        score = shared / math.sqrt(len(pwords) + 1)
        if score > best_score:
            best, best_score = passage, score
    return best


def _concept_pattern(labels: list[str]) -> re.Pattern[str] | None:
    """Matches any concept as a whole phrase, plural/possessive tolerant, longest first."""
    parts = []
    for label in sorted(labels, key=len, reverse=True):
        words = label.split()
        if not words:
            continue
        body = r"\s+".join(re.escape(w) for w in words[:-1])
        last = re.escape(words[-1].removesuffix("y")) + (
            r"(?:y|ies)" if words[-1].endswith("y") else r"(?:s|es)?"
        )
        last += r"(?:['’]s)?"
        parts.append((body + r"\s+" if body else "") + last)
    if not parts:
        return None
    return re.compile(r"(?<![\w\[/#|])(" + "|".join(parts) + r")(?![\w\]])", re.IGNORECASE)


def _link_concepts(
    segment: str, pattern: re.Pattern[str], by_key: dict[str, str], used: set[str]
) -> str:
    def swap(match: re.Match[str]) -> str:
        found = match.group(0)
        label = by_key.get(key(found))
        if not label or label in used:
            return found
        used.add(label)
        return f"[[{concept_path(label)}|{found}]]"

    return pattern.sub(swap, segment)


def cite_document(
    text: str,
    idea_target: str,
    passages: list[dict[str, str]],
    concepts: list[str],
) -> str:
    """The document with source citations and concept links added. Idempotent-safe: lines that
    already link to the idea note are left as they are."""
    if not text or not text.strip():
        return text
    pattern = _concept_pattern(concepts)
    by_key = {key(c): c for c in concepts}
    used: set[str] = set()
    fence = ""
    out: list[str] = []
    cited_any = False
    for line in text.split("\n"):
        marker = _FENCE.match(line)
        if marker:
            fence = "" if fence and marker.group(1)[0] == fence[0] else (fence or marker.group(1))
            out.append(line)
            continue
        stripped = line.strip()
        if fence or not stripped:
            out.append(line)
            continue
        if re.match(r"^#{1,6}\s", stripped):
            used = set()  # a new section links its concepts again
            out.append(line)
            continue
        if (
            stripped.startswith("|")
            or stripped.startswith("<")
            or re.fullmatch(r"[-*_=\s]+", stripped)
        ):
            out.append(line)
            continue
        if pattern:
            pieces = _PROTECTED.split(line)
            line = "".join(
                piece if i % 2 else _link_concepts(piece, pattern, by_key, used)
                for i, piece in enumerate(pieces)
            )
        if f"[[{idea_target}#" not in line and len(content_words(stripped)) >= MIN_CITE_WORDS:
            source = best_passage(stripped, passages)
            if source:
                line = f"{line.rstrip()} [[{idea_target}#^{source['id']}|{CITE_LABEL}]]"
                cited_any = True
        out.append(line)
    if not cited_any and f"[[{idea_target}" not in text:
        out.append("")
        out.append(f"Source: [[{idea_target}|original idea note]]")
    return "\n".join(out)


# -- the graph ----------------------------------------------------------------------------


def idea_text(idea: dict[str, Any]) -> str:
    return f"{idea.get('title') or ''}\n{plain(idea.get('description'))}"


def build_graph(
    idea: dict[str, Any],
    documents: dict[str, str],
    answers: list[str],
    other_ideas: list[dict[str, Any]],
    *,
    idea_target: str,
    idea_targets: dict[str, str],
    skills: list[str] | None = None,
) -> dict[str, Any]:
    """The knowledge graph for one idea.

    ``documents`` maps document type → Markdown. ``other_ideas`` are the person's other ideas
    (``idea_id``, ``title``, ``description``, optional ``required_skills``); ``idea_targets``
    maps idea id → wiki-link target. Returns passages, concepts (with every idea that mentions
    each one), related ideas ranked by shared concepts, and the cited documents.
    """
    passages = source_passages(idea.get("description"), answers)
    core = "\n".join([idea_text(idea), *answers])
    concepts = extract_concepts(core, "\n".join(documents.values()), skills)
    others = [o for o in other_ideas if str(o.get("idea_id")) != str(idea.get("idea_id"))]
    other_text = {str(o["idea_id"]): idea_text(o) for o in others}
    concept_nodes = []
    shared: dict[str, list[str]] = {}
    for label in concepts:
        linked = [iid for iid, text in other_text.items() if mentions(text, label)]
        for iid in linked:
            shared.setdefault(iid, []).append(label)
        concept_nodes.append(
            {
                "label": label,
                "path": concept_path(label),
                "passages": [p["id"] for p in passages if mentions(p["text"], label)],
                "documents": [d for d, t in documents.items() if t and mentions(t, label)],
                "ideas": linked,
            }
        )
    titles = {str(o["idea_id"]): o.get("title") or "Untitled idea" for o in others}
    related = [
        {"idea_id": iid, "title": titles[iid], "path": idea_targets.get(iid), "concepts": labels}
        for iid, labels in sorted(shared.items(), key=lambda kv: (-len(kv[1]), titles[kv[0]]))
    ]
    cited = {
        doc: cite_document(text, idea_target, passages, concepts)
        for doc, text in documents.items()
        if text and text.strip()
    }
    return {
        "idea_target": idea_target,
        "passages": passages,
        "concepts": concept_nodes,
        "related": related,
        "documents": cited,
    }
