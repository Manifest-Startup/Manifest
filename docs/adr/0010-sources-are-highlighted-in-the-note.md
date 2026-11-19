# 0010. Sources are highlighted in the note; the graph stays in the background

- Status: Accepted (2026-11-19). Changes how the app presents [0006](0006-every-idea-grows-a-cited-knowledge-graph.md) and [0009](0009-the-knowledge-graph-is-a-model-of-the-idea.md). The graph itself is unchanged.
- Code: `frontend/src/features/ideas/knowledge/sourceHighlight.ts`, `frontend/src/features/ideas/knowledge/sources.tsx`, `TextArea` (`highlights`), reading theme in `frontend/src/index.css` and `display/documents.css`

## Context

The idea's knowledge graph had its own page in the app, and document links opened it. Founders found a whole graph clumsy: it's not what the app is for. When they follow a citation they want to see the words they wrote, in their note. Agents, the CLI and the vault still benefit from the full graph.

## Decision

- **No graph page in the app.** The "Knowledge Graph" entry is gone, and old `/knowledge-graph` links redirect to the note. `ideaKnowledgeGraph` (GraphQL, CLI, plugin tool `idea_knowledge_graph`) and the vault keep the full graph: roles, `why`, relations and reasons.
- **Citations highlight the source in the note.** A citation (`↩`, `?cite=p3`) opens the note with that sentence highlighted and scrolled into view. A concept link (`?mark=<Concept>`) highlights every place the founder wrote that concept, including its plurals, hyphenated spellings and multi-word aliases; one-word fragments are not highlighted. Highlights are editor decorations, so the note and the shared live document never change. Typing clears them. A cited interview answer isn't part of the note, so it is quoted above the note instead.
- **One reading theme.** The note and every document use the workspace Markdown preview's type (`.vscode/markdown.css`): SF Pro Text at 17px with 1.62 line height and −0.012em tracking, SF Pro Display headlines tight-tracked, a 2px rule above each section, Apple greys, a 720px measure and a soft yellow highlight (`#fff3b0`, `#5c4a00` in dark mode) with a subtle underline edge. The tokens live in `index.css` (`--read-*`). Slides and canvas blocks keep their compact sizes.
- The app's graph query asks only for what it uses: passages, concept names and aliases, and cited documents.

## Consequences

- People see their own words, not a diagram, and the reading surfaces look the same as in the editor.
- The graph is explained by agents (the `manifest-vault` skill says so) and in the vault's Obsidian graph, not in the app.
