# 0006. Every idea grows a cited knowledge graph

- Status: Accepted (2026-11-17). Builds on [0005](0005-agents-write-documents-and-keep-a-local-vault.md).
- Code: `backend/app/services/ideas/knowledge_graph.py`, `vault.idea_knowledge_graph`, GraphQL `ideaKnowledgeGraph`, `frontend/src/features/ideas/knowledge/`

## Context

Generated documents (canvas, deck, PRD, patent draft) said things about an idea without showing where they came from, and the vault's `[[wiki-links]]` showed up as raw brackets, or not at all, in the app. Founders want to check a claim against what they actually said, and see how their ideas connect.

## Decision

- **Built live, no AI, no stored state.** Each time an idea's graph is read, `knowledge_graph.build_graph` rebuilds it from the idea note, the founder's own qualification answers and the documents. It grows with every interview answer and every generated or agent-written document, costs nothing, and can never drift.
- **Passages.** The note is split into sentences (`p1`…) and the founder's interview answers into `a1`…. In the vault they are Obsidian block ids (`^p1`) on the idea note.
- **Citations.** Every substantial document line (not headings, tables or code) ends with `[[Manifest/Ideas/<idea>#^pN|↩]]`, pointing at the passage it shares the most content words with. A document with nothing to match still links the note.
- **Concepts.** Recurring 1–3 word phrases from the founder's words (plus phrases the documents repeat, plus required skills) become `Manifest/Concepts/<concept>` hubs. The first mention in each section links to its hub. A concept links every one of the person's ideas that mentions it, so the network is dense across ideas.
- **One link format everywhere.** The vault and the app use the same wiki-link targets. The app turns them into routes: a citation opens the idea note with the cited passage shown (`?cite=p3`), a concept opens the idea's Knowledge Graph view, and an idea or document link opens it. The app shows a cited copy only while it still matches the stored document (`citedFor`), so the stored documents never change.
- **Owner only.** The graph names the person's other ideas, so collaborators get `null` and see the plain documents.

## Consequences

- Citations are lexical matches, not proof of reasoning. They show the closest source passage, and the founder still reviews the draft.
- The concept list is heuristic. Phrases are stemmed and stop-worded, so some hubs will be broad. Moving extraction to a model later would only change `extract_concepts`.
- Incremental vault sync re-exports an idea when its interviews change. When another idea changes, related-idea lists on the first idea refresh only on a full sync, but concept hubs are always rewritten.
