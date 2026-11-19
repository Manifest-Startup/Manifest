"""Each idea's knowledge graph: a small semantic model of the idea (ADR 0006, ADR 0009).

Pure functions, no AI and no stored state, so the graph is always current and every part
of it can be explained: it is rebuilt from the idea note, the founder's interview answers
and the generated documents each time it is read. The app (``ideaKnowledgeGraph``) and the
local vault (``vault.build_files``) show the same ``[[wiki-links]]``.

How the model is derived:

1. **Passages.** The note is split into sentences (``p1``…) and the founder's interview
   answers into ``a1``…. These are the only places concepts can come from: generated
   documents can mention a concept, never create one.
2. **Candidate phrases.** 1–3 word runs from the founder's words, with no stopword or
   generic business word ("app", "platform", "market") at either end. Words are lightly
   stemmed ("schedules", "scheduling" → "schedul") and hyphens split ("night-shift").
3. **Concepts.** A phrase becomes a concept when the founder repeats it, puts it in the
   title, or (for multi-word names) states it specifically. A fragment that mostly occurs
   inside a longer kept phrase ("plan" inside "meal plan") folds into it; spelling variants
   become aliases; a kept phrase inside another kept phrase becomes its narrower child.
4. **Roles.** Each concept gets the role it plays in the idea (who it's for, problem,
   solution, how it works, business, context), scored from what it is (people and buyers,
   technologies) and from cue words in the sentences that mention it ("struggle", "pay").
5. **Relations.** Two concepts in the same founder sentence are related; the label comes
   from their roles ("struggles with", "addresses", "uses", "pays for") and every relation
   cites its sentences.
6. **Other ideas.** An idea is related only through shared concepts that are distinctive
   (rare across the person's ideas, not generic), and the reason is spelled out.
7. **Citations.** Each substantial document line cites the passage it best matches,
   weighting rare words and shared concepts, and preferring passages whose role matches the
   section (a "Problem" slide cites the problem sentence).
"""

from __future__ import annotations

import html
import json
import math
import re
from collections import Counter, defaultdict
from typing import Any

ROOT = "Manifest"
CITE_LABEL = "↩"
MAX_CONCEPTS = 14
MIN_CITE_WORDS = 5

_WORD = re.compile(r"[a-z][a-z0-9'’]*[a-z0-9]|[a-z]")
_TAGS = re.compile(r"<[^>]+>")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'“(])")
_CHUNK = re.compile(r"[.,;:!?()\[\]{}\n|/\"“”]+|\s[-–—]\s")
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
    yours able already etc vs year years month months day days time times lot lots kind sort
    part parts include includes including i'm i've i'd we're it's don't can't won't isn't
    nobody everyone someone anybody instead around already actually basically maybe
    i.e e.g eg ie im ive id dont cant wont isnt pre re non co sub multi semi
    """.split()
)
# Words that say nothing about this idea in particular. They may sit inside a concept
# ("scheduling software") but never start, end or make up one on their own.
_GENERIC = frozenset(
    """
    idea ideas startup startups company companies product products solution solutions problem
    problems market markets business businesses value platform platforms app apps application
    tool tools service services system systems feature features user users customer customers
    people person team teams thing stuff way approach help helps allow allows provide provides
    offer offers build builds create creates simple easy better best high low large small big
    huge major key main core real live whole full total current today tomorrow new old
    slide section document draft public private free cheap early late fast slow quick
    significant important growing large-scale challenge challenges opportunity opportunities
    experience experiences process processes option options
    good great nice able certain various different specific general
    """.split()
)
_PEOPLE = frozenset(
    """
    nurse doctor physician clinician patient caregiver student teacher parent child kid
    family worker employee staff founder administrator admin manager driver owner resident
    tenant landlord farmer chef cook artist creator musician developer engineer designer
    freelancer contractor volunteer athlete coach senior retiree veteran traveler commuter
    shopper buyer seller merchant vendor investor lawyer accountant broker agent therapist
    pharmacist dentist officer firefighter technician mechanic electrician plumber teen
    adult woman man women men colleague member fan reader writer gamer homeowner renter
    hospital clinic school university college city government agency insurer bank retailer
    restaurant hotel landlord employer brand nonprofit charity church library council
    """.split()
)
# Organisations that usually pay for what their people use.
_BUYERS = frozenset(
    """
    hospital clinic school university college city government agency insurer bank retailer
    employer brand nonprofit council company enterprise district state ministry
    """.split()
)
_TECH = frozenset(
    """
    ai ml api sdk sensor sensors iot gps camera cameras blockchain model llm algorithm
    software hardware integration sync database cloud chip robot drone satellite bluetooth
    nfc rfid wearable app-store machine-learning computer vision lidar battery solar
    analytics dashboard automation chatbot embedding scanner
    """.split()
)

ROLES = ("who", "problem", "solution", "technology", "business", "context", "skill")
ROLE_LABELS = {
    "who": "Who it's for",
    "problem": "Problem",
    "solution": "Solution",
    "technology": "How it works",
    "business": "Business",
    "context": "Context",
    "skill": "Skills needed",
}
# Cue words in a sentence that say what that sentence is about (stems).
_CUES = {
    "problem": """skip struggl can't cannot hard difficult expensive costl cost waste lack
        miss fail poor broken closed pain frustrat stress risk unsaf danger burnout slow
        manual tedious overwhelm confus lose lost delay ignor nobody never only worry
        suffer shortag gap barrier limit unabl afford""",
    "solution": """build app platform tool plan deliver let lets help automat match connect
        track remind recommend schedul order book offer design creat put enabl simplif
        replac guid personaliz predict alert monitor sync""",
    "technology": """sensor api integrat sync ai model data algorithm software hardware
        machin learn gps camera cloud device chip""",
    "business": """pay paid price pric subscription fee revenu benefit budget spend sell
        buy margin licens contract commission per month annual cost save saving insur
        reimburs fund grant""",
    "who": """for who nurse student worker employe parent patient custom user member
        staff colleagu i'm i've""",
}
_CUES = {role: frozenset(words.split()) for role, words in _CUES.items()}
_HEADING_ROLES = {
    "problem": ("problem", "pain", "challenge", "why now", "opportunity"),
    "solution": ("solution", "product", "how it works", "overview", "feature", "demo"),
    "who": ("customer", "user", "segment", "persona", "who", "audience", "market"),
    "business": ("business model", "revenue", "pricing", "go-to-market", "financial", "ask"),
    "technology": ("technology", "architecture", "requirement", "technical", "claims"),
}
RELATION_LABELS = {
    ("who", "problem"): "struggles with",
    ("solution", "problem"): "addresses",
    ("solution", "who"): "serves",
    ("solution", "technology"): "uses",
    ("technology", "problem"): "addresses",
    ("who", "business"): "benefits from",
    ("business", "solution"): "pays for",
    ("problem", "problem"): "comes with",
    ("problem", "business"): "costs",
    ("solution", "solution"): "works with",
}


# -- text helpers -----------------------------------------------------------------------


def plain(text: Any) -> str:
    """Note text without HTML tags or entities (the editor may store either)."""
    return html.unescape(_TAGS.sub(" ", str(text or "")))


def _stem(word: str) -> str:
    """A light, predictable stemmer: plurals, possessives, -ing/-ed, a trailing e."""
    word = word.replace("’", "'").removesuffix("'s").removesuffix("'")
    if len(word) > 4 and word.endswith("ies"):
        word = word[:-3] + "y"
    elif len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        word = word[:-1]
    if len(word) > 5 and word.endswith("ing"):
        word = word[:-3]
    elif len(word) > 4 and word.endswith("ed") and not word.endswith("eed"):
        word = word[:-2]
    if len(word) > 4 and word.endswith("e") and not word.endswith(("ee", "ie")):
        word = word[:-1]
    return word


def _words(text: str) -> list[str]:
    """Lower-case surface words; hyphenated compounds split ("night-shift" → night, shift)."""
    return _WORD.findall(text.lower().replace("-", " ").replace("–", " "))


def _tokens(text: str) -> list[str]:
    return [_stem(w) for w in _words(text)]


def content_words(text: str) -> set[str]:
    return {t for t in _tokens(text) if t not in _STOP and len(t) > 2 and not t.isdigit()}


def note_name(text: str, fallback: str = "Untitled") -> str:
    name = _UNSAFE.sub(" ", str(text or "")).strip().strip(".")
    return re.sub(r"\s+", " ", name)[:120] or fallback


def concept_path(label: str) -> str:
    return f"{ROOT}/Concepts/{note_name(label.title() if label.islower() else label)}"


def key(label: str) -> str:
    return " ".join(_tokens(label))


def mentions(text: str, label: str) -> bool:
    words = _tokens(label)
    if not words:
        return False
    tokens = _tokens(text)
    n = len(words)
    return any(tokens[i : i + n] == words for i in range(len(tokens) - n + 1))


def _mentions_any(text: str, keys: list[str]) -> bool:
    tokens = " " + " ".join(_tokens(text)) + " "
    return any(f" {k} " in tokens for k in keys if k)


def _stop(stem: str) -> bool:
    return stem in _STOP_STEMS or stem.isdigit() or len(stem) < 2


def _generic(stem: str) -> bool:
    return stem in _GENERIC_STEMS


_STOP_STEMS = frozenset(_stem(w) for w in _STOP) | _STOP
_GENERIC_STEMS = frozenset(_stem(w) for w in _GENERIC)
_PEOPLE_STEMS = frozenset(_stem(w) for w in _PEOPLE)
_TECH_STEMS = frozenset(_stem(w) for w in _TECH)
_BUYER_STEMS = frozenset(_stem(w) for w in _BUYERS)
_CUE_STEMS = {role: frozenset(_stem(w) for w in words) | words for role, words in _CUES.items()}


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


# Verbs and prepositions that make a phrase a fragment of a clause rather than a name.
_EDGE_WORDS = frozenset(
    """
    eat skip build want pay sync time live work struggle buy sell run save spend welcome
    update record write handle take help deliver use get make keep put cover reach face
    lead go come bring send show tell ask
    near nearby onto inside outside overnight automatically already late early instead
    """.split()
)
_EDGE_STEMS = frozenset(_stem(w) for w in _EDGE_WORDS) | _EDGE_WORDS


def _phrases(text: str) -> list[tuple[tuple[str, ...], str, tuple[int, int, int]]]:
    """Every 1–3 word candidate in ``text``: (stems, surface words, (chunk, start, end))."""
    found = []
    for c, chunk in enumerate(_CHUNK.split(text)):
        surface = _words(chunk)
        stems = [_stem(w) for w in surface]
        for n in (1, 2, 3):
            for i in range(len(stems) - n + 1):
                gram = tuple(stems[i : i + n])
                if any(_stop(w) for w in gram) or any("'" in w for w in gram):
                    continue
                if _generic(gram[0]) or _generic(gram[-1]):
                    continue
                if n > 1 and (gram[0] in _EDGE_STEMS or gram[-1] in _EDGE_STEMS):
                    continue
                # A plural word before the head means a verb or a list, not a name:
                # "plans healthy meals", "nurses skip meals" ("meal plan", not "meals plan").
                if n > 1 and any(
                    surface[k].endswith("s") and _stem(surface[k]) != surface[k]
                    for k in range(i, i + n - 1)
                ):
                    continue
                if n == 1 and (len(gram[0]) < 4 or gram[0] in _EDGE_STEMS):
                    continue
                found.append((gram, " ".join(surface[i : i + n]), (c, i, i + n)))
    return found


def _contains(longer: tuple[str, ...], shorter: tuple[str, ...]) -> bool:
    n = len(shorter)
    return any(longer[i : i + n] == shorter for i in range(len(longer) - n + 1))


def _singular(label: str) -> str:
    words = label.split()
    last = words[-1]
    if len(last) > 4 and last.endswith("ies"):
        last = last[:-3] + "y"
    elif len(last) > 3 and last.endswith("s") and not last.endswith(("ss", "us", "is")):
        last = last[:-1]
    return " ".join([*words[:-1], last])


def _surface_label(forms: Counter[str]) -> str:
    """The way the founder most often wrote it, singular where we can tell."""
    return _singular(forms.most_common(1)[0][0])


Gram = tuple[str, ...]
Span = tuple[str, int, int, int]  # passage id, chunk, start, end


class _Phrases:
    """Where each candidate phrase occurs, and its C-value.

    C-value is a standard term-extraction score: frequent phrases win, longer ones get a
    bonus, and a phrase loses the uses it only has inside longer phrases.
    """

    def __init__(self, title: str, passages: list[dict[str, str]]) -> None:
        self.spans: dict[Gram, set[Span]] = defaultdict(set)
        self.forms: dict[Gram, Counter[str]] = defaultdict(Counter)
        for passage in [{"id": "title", "text": title}, *passages]:
            for gram, surface, (c, i, j) in _phrases(passage["text"]):
                self.spans[gram].add((passage["id"], c, i, j))
                self.forms[gram][surface] += 1
        self.in_title = {g for g, s in self.spans.items() if any(x[0] == "title" for x in s)}
        self.freq = {g: len(s) + (g in self.in_title) for g, s in self.spans.items()}
        grams = list(self.spans)
        self.longer: dict[Gram, list[Gram]] = {
            g: [h for h in grams if len(h) > len(g) and _contains(h, g)] for g in grams
        }

    def cvalue(self, g: Gram) -> float:
        # Softened for short notes: half of the average nested use is discounted.
        nested = [self.freq[h] for h in self.longer[g]]
        own = self.freq[g] - 0.5 * (sum(nested) / len(nested) if nested else 0)
        # A phrase said once is weaker evidence than a word the founder keeps coming back to.
        once = 0.5 if self.freq[g] == 1 and g not in self.in_title else 1.0
        return once * (1 + 0.5 * (len(g) - 1)) * max(own, 0.0)

    def eligible(self, g: Gram) -> bool:
        if len(g) == 1:
            return self.freq[g] >= 2
        if sum(_generic(w) for w in g) * 2 >= len(g):
            return False
        return self.freq[g] >= 2 or g in self.in_title or len(g) <= 3

    def ranked(self) -> list[Gram]:
        found = (g for g in self.spans if self.eligible(g))
        return sorted(found, key=lambda g: (-self.cvalue(g), -len(g), g))

    def label(self, g: Gram) -> str:
        return _surface_label(self.forms[g])


def _straddles(spans: set[Span], kept_spans: set[Span]) -> bool:
    """Every use of a phrase cuts across a kept phrase without containing or sitting in it."""
    for pid, c, i, j in spans:
        if not any(
            qid == pid and d == c and a < j and i < b and not (a <= i <= j <= b or i <= a <= b <= j)
            for qid, d, a, b in kept_spans
        ):
            return False
    return True


def _select(stats: _Phrases, limit: int) -> tuple[list[Gram], dict[Gram, set[Gram]]]:
    """The concept phrases, each with the variants and fragments folded into it."""
    kept: list[Gram] = []
    aliases: dict[Gram, set[Gram]] = defaultdict(set)
    kept_spans: set[Span] = set()
    freq = stats.freq
    for g in stats.ranked():
        if stats.cvalue(g) <= 0 and g not in stats.in_title:
            continue
        home = next((k for k in kept if key(" ".join(k)) == key(" ".join(g))), None) or next(
            (k for k in kept if len(k) > len(g) and _contains(k, g) and freq[k] >= 0.6 * freq[g]),
            None,
        )
        if home:
            aliases[home].add(g)  # a spelling variant, or "plan" inside "meal plan"
            continue
        if _straddles(stats.spans[g], kept_spans):
            continue
        # A kept fragment that mostly occurs inside this phrase becomes its alias.
        for k in [k for k in kept if len(k) < len(g) and _contains(g, k)]:
            if freq[g] >= 0.6 * freq[k]:
                kept.remove(k)
                aliases[g] |= {k, *aliases.pop(k, set())}
        kept.append(g)
        kept_spans |= stats.spans[g]
        if len(kept) >= limit:
            break
    return kept, aliases


def _concept(stats: _Phrases, g: Gram, aliases: set[Gram]) -> dict[str, Any]:
    members = [g, *aliases]
    label = stats.label(g)
    return {
        "gram": g,
        "label": label,
        "aliases": sorted(
            {_singular(stats.forms[a].most_common(1)[0][0]) for a in aliases} - {label}
        ),
        "passages": sorted(
            {pid for m in members for pid, *_ in stats.spans[m] if pid != "title"},
            key=_passage_order,
        ),
        "count": len({s for m in members for s in stats.spans[m] if s[0] != "title"}),
        "in_title": g in stats.in_title,
        "weight": stats.cvalue(g) + (1.0 if g in stats.in_title else 0.0),
        "source": "founder",
        "parent": None,
    }


def _skill_concept(skill: str) -> dict[str, Any]:
    return {
        "gram": tuple(_tokens(skill)),
        "label": skill.strip(),
        "aliases": [],
        "passages": [],
        "count": 0,
        "in_title": False,
        "weight": 0.5,
        "source": "skills",
        "parent": None,
    }


def _derive_concepts(
    title: str, passages: list[dict[str, str]], skills: list[str], limit: int
) -> list[dict[str, Any]]:
    """Concepts from the founder's own words, with aliases, parents and evidence."""
    stats = _Phrases(title, passages)
    kept, aliases = _select(stats, limit + 6)
    # A one-off variant with one more word in front ("rotating shift schedule") is the same
    # concept as the phrase it qualifies ("shift schedule"): fold it in.
    for g in sorted(kept, key=len, reverse=True):
        if stats.freq[g] > 1 or g in stats.in_title:
            continue
        base = g[1:]
        if base in kept:
            kept.remove(g)
            aliases[base] |= {g, *aliases.pop(g, set())}
    concepts = sorted(
        (_concept(stats, g, aliases[g]) for g in kept), key=lambda c: (-c["weight"], c["label"])
    )[:limit]
    # Narrower concepts sit under the closest broader one they contain ("night shift" under
    # "shift", "shift scheduling software" under "shift schedule").
    for concept in concepts:
        parents = [
            o
            for o in concepts
            if len(o["gram"]) < len(concept["gram"]) and _contains(concept["gram"], o["gram"])
        ]
        if parents:
            concept["parent"] = max(parents, key=lambda o: (len(o["gram"]), o["weight"]))["label"]
    seen = {key(c["label"]) for c in concepts}
    for skill in skills:
        if skill.strip() and key(skill) not in seen:
            seen.add(key(skill))
            concepts.append(_skill_concept(skill))
    return concepts


def _passage_order(pid: str) -> tuple[int, int]:
    return (0 if pid.startswith("p") else 1, int(pid[1:]) if pid[1:].isdigit() else 0)


def extract_concepts(
    core_text: str, extra_text: str = "", skills: list[str] | None = None, limit: int = MAX_CONCEPTS
) -> list[str]:
    """Concept labels for one idea, skills first then strongest first.

    Only ``core_text`` (the founder's words) creates concepts; ``extra_text`` (generated
    documents) is accepted for compatibility and ignored, so boilerplate can't become one.
    """
    del extra_text
    passages = [
        {"id": f"p{i + 1}", "kind": "note", "text": s}
        for i, s in enumerate(s for s in _SENTENCE.split(plain(core_text)) if s.strip())
    ]
    found = _derive_concepts("", passages, [], limit)
    labels = [s.strip() for s in skills or [] if s.strip()]
    keys = {key(label) for label in labels}
    for concept in found:
        if key(concept["label"]) not in keys:
            labels.append(concept["label"])
            keys.add(key(concept["label"]))
    return labels[: max(limit, len(skills or []))]


# -- roles and relations ----------------------------------------------------------------


def _cues_in(text: str) -> dict[str, list[str]]:
    """Cue words in ``text`` by role, as the founder wrote them ("closed", not "clos")."""
    found: dict[str, set[str]] = defaultdict(set)
    for word in _words(text):
        word = word.replace("’", "'")
        for role, stems in _CUE_STEMS.items():
            if word in stems or _stem(word) in stems:
                found[role].add(word)
    return {role: sorted(words) for role, words in found.items()}


def _assign_role(concept: dict[str, Any], by_id: dict[str, str]) -> None:
    if concept["source"] == "skills":
        concept.update(role="skill", cues=[])
        return
    gram = concept["gram"]
    head = gram[-1]
    scores: Counter[str] = Counter()
    cues: Counter[str] = Counter()
    if head in _PEOPLE_STEMS:
        scores["who"] += 4
    if head in _TECH_STEMS or any(w in _TECH_STEMS for w in gram):
        scores["technology"] += 3
    if any(w in _CUE_STEMS["problem"] for w in gram):
        scores["problem"] += 4
    if any(w in _CUE_STEMS["business"] for w in gram):
        scores["business"] += 3
    for pid in concept["passages"]:
        found = _cues_in(by_id.get(pid, ""))
        for role, words in found.items():
            if role == "who":
                continue  # a sentence mentioning people says little about this concept
            scores[role] += 1 + 0.25 * (len(words) - 1)
            cues.update(w for w in words if _stem(w) not in gram)
    total = sum(scores.values())
    top_role, top = scores.most_common(1)[0] if scores else ("context", 0.0)
    if top < 1 or (top_role in ("solution", "problem") and top / total < 0.45):
        role = "context"  # it appears everywhere; it is the setting, not one part of the idea
    else:
        role = top_role
        if role == "solution" and scores["who"] >= 4:
            role = "who"
    concept["role"] = role
    role_stems = _CUE_STEMS.get(role, set())
    concept["cues"] = [
        w for w, _ in cues.most_common(6) if w in role_stems or _stem(w) in role_stems
    ][:3]


def _why(concept: dict[str, Any]) -> str:
    if concept["source"] == "skills":
        return "Listed in the skills this idea needs."
    ids = concept["passages"]
    parts = []
    times = concept["count"] + (1 if concept["in_title"] else 0)
    where = ", ".join(ids[:4]) + ("…" if len(ids) > 4 else "")
    if concept["in_title"]:
        parts.append("It's in the idea's title")
    if ids:
        parts.append(
            f"you wrote it {times}× ({where})" if parts else f"You wrote it {times}× ({where})"
        )
    if concept["aliases"]:
        parts.append("also as " + ", ".join(f"“{a}”" for a in concept["aliases"][:3]))
    sentence = "; ".join(parts) + "."
    role = concept["role"]
    if role == "who":
        sentence += " It names people or organisations the idea is for."
    elif role == "technology" and not concept["cues"]:
        sentence += " It's a technology the idea relies on."
    elif concept["cues"]:
        what = {
            "problem": "a problem",
            "solution": "what you're building",
            "technology": "how it works",
            "business": "who pays and how",
        }.get(role, "the idea")
        cues = ", ".join(f"“{c}”" for c in concept["cues"])
        sentence += f" The sentences around it are about {what} ({cues})."
    return sentence[0].upper() + sentence[1:]


def _relations(concepts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Concepts that share a founder sentence, labelled by the roles they play."""
    pairs: dict[tuple[str, str], set[str]] = defaultdict(set)
    founder = [c for c in concepts if c["source"] == "founder"]
    for i, a in enumerate(founder):
        for b in founder[i + 1 :]:
            if _contains(a["gram"], b["gram"]) or _contains(b["gram"], a["gram"]):
                continue
            shared = set(a["passages"]) & set(b["passages"])
            if shared:
                pairs[(a["label"], b["label"])] = shared
    by_label = {c["label"]: c for c in founder}
    relations = []
    for (a, b), shared in pairs.items():
        ra, rb = by_label[a]["role"], by_label[b]["role"]
        if (ra, rb) in RELATION_LABELS:
            source, target, label = a, b, RELATION_LABELS[(ra, rb)]
        elif (rb, ra) in RELATION_LABELS:
            source, target, label = b, a, RELATION_LABELS[(rb, ra)]
        else:
            source, target, label = a, b, "relates to"
        if label == "benefits from" and by_label[source]["gram"][-1] in _BUYER_STEMS:
            label = "pays through"  # an organisation that funds it, not a person who uses it
        relations.append(
            {
                "source": source,
                "target": target,
                "label": label,
                "passages": sorted(shared, key=_passage_order),
                "weight": len(shared),
            }
        )
    # Themes ("context") are shown as groups, not edges, and a vague link needs two sentences.
    relations = [
        r
        for r in relations
        if "context" not in (by_label[r["source"]]["role"], by_label[r["target"]]["role"])
        and (r["label"] != "relates to" or r["weight"] >= 2)
    ]
    relations.sort(key=lambda r: (-r["weight"], r["label"] == "relates to", r["source"]))
    # Keep the picture readable: each concept's strongest few relations.
    per: Counter[str] = Counter()
    kept = []
    for relation in relations:
        if per[relation["source"]] >= 4 or per[relation["target"]] >= 4:
            continue
        per[relation["source"]] += 1
        per[relation["target"]] += 1
        kept.append(relation)
    return kept


# -- citations --------------------------------------------------------------------------


def _heading_role(heading: str) -> str | None:
    text = heading.lower()
    for role, words in _HEADING_ROLES.items():
        if any(w in text for w in words):
            return role
    return None


def _passage_roles(
    passages: list[dict[str, str]], concepts: list[dict[str, Any]]
) -> dict[str, Counter[str]]:
    """How strongly each passage is about each role (cue words plus its concepts)."""
    roles: dict[str, Counter[str]] = defaultdict(Counter)
    for concept in concepts:
        for pid in concept["passages"]:
            roles[pid][concept["role"]] += 0.5
    for passage in passages:
        for role, words in _cues_in(passage["text"]).items():
            if role != "who":
                roles[passage["id"]][role] += len(words)
    return roles


def best_passage(
    line: str,
    passages: list[dict[str, str]],
    *,
    concepts: list[dict[str, Any]] | None = None,
    section_role: str | None = None,
    passage_roles: dict[str, Counter[str]] | None = None,
) -> dict[str, str] | None:
    """The passage a document line most likely draws on, or None when nothing fits."""
    words = content_words(line)
    if not words or not passages:
        return None
    df: Counter[str] = Counter()
    pwords = {p["id"]: content_words(p["text"]) for p in passages}
    for ws in pwords.values():
        df.update(ws)
    total = len(passages)
    line_concepts = {
        c["label"]
        for c in concepts or []
        if _mentions_any(line, c.get("keys") or [key(c["label"])])
    }
    best, best_score = None, 0.0
    for passage in passages:
        shared = words & pwords[passage["id"]]
        shared_concepts = {
            c["label"]
            for c in concepts or []
            if c["label"] in line_concepts and passage["id"] in c["passages"]
        }
        if len(shared) < 2 and not shared_concepts:
            continue
        score = sum(math.log(1 + total / df[w]) for w in shared)
        score += 1.5 * len(shared_concepts)
        if section_role:
            strength = (passage_roles or {}).get(passage["id"], Counter())[section_role]
            score += min(2.0, strength)
        score /= math.sqrt(len(pwords[passage["id"]]) + 1) ** 0.5
        # Near-ties go to the earlier passage: founders lead with what matters most.
        if score > best_score * 1.1:
            best, best_score = passage, score
    return best


def _concept_pattern(concepts: list[dict[str, Any]]) -> re.Pattern[str] | None:
    """Any concept or alias as a whole phrase (plural/possessive/hyphen tolerant)."""
    phrases = sorted(
        {
            p
            for c in concepts
            for p in [c["label"], *c.get("aliases", [])]
            if p.strip() and (p == c["label"] or len(p.split()) > 1)
        },
        key=len,
        reverse=True,
    )
    parts = []
    for phrase in phrases:
        words = _words(phrase)
        if not words:
            continue
        body = r"[\s-]+".join(re.escape(w) for w in words[:-1])
        last = words[-1]
        stemmed = re.escape(last.removesuffix("y")) + (
            r"(?:y|ies)" if last.endswith("y") else r"(?:s|es|ed|ing)?"
        )
        stemmed += r"(?:['’]s)?"
        parts.append((body + r"[\s-]+" if body else "") + stemmed)
    if not parts:
        return None
    # Never link part of a hyphenated word ("late-night") or of an existing link.
    return re.compile(r"(?<![\w\[/#|-])(" + "|".join(parts) + r")(?![\w\]-])", re.IGNORECASE)


def _as_concepts(concepts: list[Any]) -> list[dict[str, Any]]:
    out = []
    for c in concepts:
        if isinstance(c, str):
            out.append(
                {"label": c, "aliases": [], "passages": [], "role": "context", "keys": [key(c)]}
            )
        else:
            out.append(c)
    return out


class _Citer:
    """Adds concept links and source citations to a document, line by line."""

    def __init__(self, idea_target: str, passages: list[dict[str, str]], concepts: list[Any]):
        self.target = idea_target
        self.passages = passages
        self.concepts = _as_concepts(concepts)
        for c in self.concepts:
            c.setdefault("keys", [key(p) for p in [c["label"], *c.get("aliases", [])]])
        self.pattern = _concept_pattern(self.concepts)
        self.by_key = {k: c["label"] for c in self.concepts for k in c["keys"]}
        self.roles = _passage_roles(passages, [c for c in self.concepts if c.get("passages")])
        self.used: set[str] = set()
        self.section_role: str | None = None
        self.cited_any = False

    def _swap(self, match: re.Match[str]) -> str:
        found = match.group(0)
        label = self.by_key.get(key(found))
        if not label or label in self.used:
            return found
        self.used.add(label)
        return f"[[{concept_path(label)}|{found}]]"

    def heading(self, line: str) -> str:
        self.used = set()  # a new section links its concepts again
        self.section_role = _heading_role(line)
        return line

    def prose(self, line: str) -> str:
        stripped = line.strip()
        if self.pattern:
            pieces = _PROTECTED.split(line)
            line = "".join(
                piece if i % 2 else self.pattern.sub(self._swap, piece)
                for i, piece in enumerate(pieces)
            )
        if f"[[{self.target}#" in line or len(content_words(stripped)) < MIN_CITE_WORDS:
            return line
        source = best_passage(
            stripped,
            self.passages,
            concepts=self.concepts,
            section_role=self.section_role,
            passage_roles=self.roles,
        )
        if not source:
            return line
        self.cited_any = True
        return f"{line.rstrip()} [[{self.target}#^{source['id']}|{CITE_LABEL}]]"


def _is_structure(stripped: str) -> bool:
    """Tables, HTML and rules are left exactly as they are."""
    return (
        stripped.startswith("|")
        or stripped.startswith("<")
        or bool(re.fullmatch(r"[-*_=\s]+", stripped))
    )


def cite_document(
    text: str,
    idea_target: str,
    passages: list[dict[str, str]],
    concepts: list[Any],
) -> str:
    """The document with source citations and concept links added.

    ``concepts`` are labels or concept dicts from ``build_graph``. Lines that already link
    to the idea note are left as they are, so the result can be stripped back to the
    stored document.
    """
    if not text or not text.strip():
        return text
    citer = _Citer(idea_target, passages, concepts)
    fence = ""
    out: list[str] = []
    for line in text.split("\n"):
        marker = _FENCE.match(line)
        stripped = line.strip()
        if marker:
            fence = "" if fence and marker.group(1)[0] == fence[0] else (fence or marker.group(1))
        elif fence or not stripped or _is_structure(stripped):
            pass
        elif re.match(r"^#{1,6}\s", stripped):
            line = citer.heading(stripped) and line
        else:
            line = citer.prose(line)
        out.append(line)
    if not citer.cited_any and f"[[{idea_target}" not in text:
        out += ["", f"Source: [[{idea_target}|original idea note]]"]
    return "\n".join(out)


# -- the graph ----------------------------------------------------------------------------


def idea_text(idea: dict[str, Any]) -> str:
    return f"{idea.get('title') or ''}\n{plain(idea.get('description'))}"


def _idea_concepts(idea: dict[str, Any]) -> list[dict[str, Any]]:
    """A light concept pass over another idea, for matching distinctive shared concepts."""
    passages = source_passages(idea.get("description"), [])
    return _derive_concepts(str(idea.get("title") or ""), passages, [], MAX_CONCEPTS)


def _connect_ideas(
    idea: dict[str, Any],
    concepts: list[dict[str, Any]],
    other_ideas: list[dict[str, Any]],
    idea_targets: dict[str, str],
) -> list[dict[str, Any]]:
    """Related ideas, through shared concepts that are distinctive across the person's ideas
    (rarer ones count more) and that the other idea really uses. Sets ``concept["ideas"]``."""
    others = {
        str(o["idea_id"]): o
        for o in other_ideas
        if str(o.get("idea_id")) != str(idea.get("idea_id"))
    }
    total = len(others) + 1
    central: dict[str, set[str]] = {}

    def central_keys(iid: str) -> set[str]:
        if iid not in central:
            central[iid] = {
                key(p) for c in _idea_concepts(others[iid]) for p in [c["label"], *c["aliases"]]
            }
        return central[iid]

    shared: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for concept in concepts:
        found = [iid for iid, o in others.items() if _mentions_any(idea_text(o), concept["keys"])]
        concept["distinctiveness"] = math.log(1 + total / (1 + len(found))) if total > 1 else 1.0
        if total > 3 and len(found) + 1 > max(2, total * 0.6):
            found = []  # in most of the person's ideas: says nothing about this pair
        if len(concept["gram"]) == 1 and concept["source"] == "founder":
            # One shared word that is central to only one of the ideas is a coincidence.
            found = [iid for iid in found if set(concept["keys"]) & central_keys(iid)]
        for iid in found:
            shared[iid].append(concept)
    related = []
    for iid, items in shared.items():
        strength = sum(c["distinctiveness"] * (1 + 0.5 * (len(c["gram"]) - 1)) for c in items)
        if strength < 0.6:
            continue
        about = [f"{c['label']} ({ROLE_LABELS[c['role']].lower()})" for c in items[:3]]
        related.append(
            {
                "idea_id": iid,
                "title": others[iid].get("title") or "Untitled idea",
                "path": idea_targets.get(iid),
                "concepts": [c["label"] for c in sorted(items, key=lambda c: -c["weight"])],
                "reason": f"Both are about {_join(about)}.",
                "strength": round(strength, 2),
            }
        )
    related.sort(key=lambda r: (-r["strength"], r["title"]))
    for concept in concepts:
        concept["ideas"] = [r["idea_id"] for r in related if concept["label"] in r["concepts"]]
    return related


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
    (``idea_id``, ``title``, ``description``); ``idea_targets`` maps idea id → wiki-link
    target. Returns passages, concepts (role, aliases, parent, evidence, why, the documents
    and other ideas that mention them), relations between concepts, related ideas with a
    reason, and the cited documents.
    """
    passages = source_passages(idea.get("description"), answers)
    by_id = {p["id"]: p["text"] for p in passages}
    concepts = _derive_concepts(
        str(idea.get("title") or ""), passages, [s for s in skills or [] if s.strip()], MAX_CONCEPTS
    )
    for concept in concepts:
        # Match by the name and multi-word aliases; a one-word fragment ("plan") is evidence
        # for this idea but would match unrelated text elsewhere.
        concept["keys"] = [
            key(p)
            for p in [concept["label"], *concept["aliases"]]
            if p == concept["label"] or len(p.split()) > 1
        ]
        _assign_role(concept, by_id)
        concept["why"] = _why(concept)
        concept["documents"] = [
            d for d, t in documents.items() if t and _mentions_any(t, concept["keys"])
        ]
    # A broad concept with narrower ones under it is the setting, not one part of the idea.
    parents = {c["parent"] for c in concepts if c["parent"]}
    for concept in concepts:
        if (
            concept["label"] in parents
            and len(concept["gram"]) == 1
            and concept["role"] in ("solution", "problem")
        ):
            concept["role"] = "context"
            concept["why"] = _why(concept)

    related = _connect_ideas(idea, concepts, other_ideas, idea_targets)
    relations = _relations(concepts)
    cited = {
        doc: cite_document(text, idea_target, passages, concepts)
        for doc, text in documents.items()
        if text and text.strip()
    }
    nodes = [
        {
            "label": c["label"],
            "path": concept_path(c["label"]),
            "role": c["role"],
            "role_label": ROLE_LABELS[c["role"]],
            "aliases": c["aliases"],
            "parent": c["parent"],
            "weight": round(c["weight"], 2),
            "why": c["why"],
            "passages": c["passages"],
            "documents": c["documents"],
            "ideas": c["ideas"],
        }
        for c in concepts
    ]
    return {
        "idea_target": idea_target,
        "passages": passages,
        "concepts": nodes,
        "relations": relations,
        "related": related,
        "documents": cited,
    }


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]
