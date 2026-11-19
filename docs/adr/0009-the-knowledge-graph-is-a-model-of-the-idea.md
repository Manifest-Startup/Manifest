# 0009. The knowledge graph is a model of the idea, not a word cloud

- Status: Accepted (2026-11-19). Revises the concept and citation rules of [0006](0006-every-idea-grows-a-cited-knowledge-graph.md); everything else in 0006 stands.
- Code: `backend/app/services/ideas/knowledge_graph.py`, `vault._idea_body`, GraphQL `ideaKnowledgeGraph`, `frontend/src/features/ideas/knowledge/KnowledgeGraphView.tsx`

## Context

Founders said the graph linked "randomly, for the sake of linking". The 0006 rules caused it:

- Every repeated 1–3 word run became a concept, including runs from generated documents. Deck boilerplate ("healthcare staffing market") became concepts, and one idea produced `meal`, `plan`, `meal plan`, `night`, `shift`, `night shift`, `shift schedule` and `scheduling` side by side.
- Concepts were a flat list. Nothing said which were the people, the problem or the product, or how they connect.
- Any shared word linked two ideas (`plan` linked a meal planner to a textbook marketplace).
- Concept links matched inside hyphenated words ("late-night" → `night`), and citations ignored which section a line was in.

## Decision

The graph stays deterministic, free and rebuilt live (0006), but it now builds a small semantic model of the idea:

1. **Only the founder's words make concepts.** These are the title, the note's sentences (`p1`…) and the interview answers (`a1`…). Documents can mention a concept, never create one.
2. **Phrases are ranked by C-value**, a standard term-extraction score, softened for short notes. Phrases with a stopword, a generic business word ("app", "platform"), a verb or a preposition at either end are excluded. A plural before the head ("plans healthy meals") marks a clause, not a name. A phrase said once counts half.
3. **Fragments fold, variants merge.** A fragment that mostly occurs inside a longer kept phrase becomes its alias (`plan` → `meal plan`). Spelling and inflection variants merge, and hyphens split ("night-shift" = "night shift"). A kept phrase inside another becomes its narrower child (`night shift` under `shift`). Only the name and multi-word aliases are used for matching, so a fragment never links unrelated text.
4. **Roles.** Each concept gets the part it plays: who it's for, problem, solution, how it works, business, a theme (context) or a skill. The role is scored from what the concept is (people and buyer organisations, technologies, problem and money words in the phrase) and from cue words in the sentences that mention it ("skip", "closed" → problem; "pay", "benefit" → business). A broad concept with narrower ones under it is a theme.
5. **Relations.** Two concepts in the same founder sentence are related. The label comes from their roles: who → *struggles with* → problem, solution → *addresses* / *serves* / *uses*, an organisation → *pays through* → business. Each relation cites its sentences. Themes aren't drawn as edges, and an unlabelled *relates to* needs two sentences.
6. **Every concept explains itself.** `why` says where it came from and why it has its role, for example "You wrote it 4× (p1, p3, a2, a3). It names people or organisations the idea is for."
7. **Other ideas connect only through distinctive concepts.** A concept is weighted by how rare it is across the person's ideas, ignored when it appears in most of them, and a one-word concept counts only when it is also a concept of the other idea. Each related idea carries a `reason`.
8. **Citations weigh what matters.** Rare words weigh more, shared concepts add weight, and a passage whose role matches the section heading gets a bonus (a "Problem" slide cites the problem sentence). Near-ties go to the earlier passage. Concept links never match part of a hyphenated word.

The app shows the model as lanes (Who it's for → Problem → Solution → How it works → Business) with the founder's connections drawn between them. It also lists themes and skills, a "How it connects" list and, for a selected concept, how it was found with its words highlighted in the founder's sentences. The vault groups concepts by role and adds `## How it connects`.

## Consequences

- Fewer, better concepts: at most 14 from the founder's words, plus listed skills.
- The model is heuristic and English-first. Roles come from cue words, so an unusual sentence can mislabel a concept, and the `why` text shows the evidence so the founder can tell. A model-based extractor (with the person's own key, ADR 0002/BYOK) could later replace steps 2–4 behind the same output.
- GraphQL fields are additive (`role`, `roleLabel`, `aliases`, `parent`, `weight`, `why`, `relations`, `reason`). Old clients keep working.
