# 0008. Shared notes are edited live together, like Google Docs

- Status: Accepted (2026-11-18).
- Code: `backend/app/services/ideas/live_notes.py`, `backend/app/routes/live_notes_socket.py`, `frontend/src/features/collaboration/live/`, `frontend/src/features/common-ui/TextArea.tsx` (the `live` prop)

## Context

Founders invite collaborators to an idea, but the note was saved whole by whoever typed last: two people writing at once overwrote each other, and nobody could see who else was there. People expect what Google Docs and Confluence do: everyone types into one note, sees each other's cursors with a name and photo, and nothing is lost. Agents (the plugin) and the `manifest` CLI edit notes too, and their changes should appear the same way.

## Decision

- **Only shared notes go live.** When an idea has at least one accepted collaborator, the Note view joins a live room; a solo note keeps the plain editor and opens no socket.
- **One shared Yjs document per note.** The editor uses TipTap's Collaboration and CollaborationCaret extensions over a Yjs document. It syncs through the backend's existing authenticated Socket.IO server (`note:join`, `note:update`, `note:awareness`, `note:leave`), not a new service. The server keeps a `pycrdt` copy of each room's document, so late joiners get the current state. A room exists only while someone is in it.
- **The saved note stays HTML.** Each browser saves its own edits through `updateIdea` as before (versions, documents and the knowledge graph are unchanged), marked `X-Manifest-Live-Note: 1`. The first editor in an empty room fills it from a fresh read of the saved note. The server lets only one person do that (`seed` / `already-seeded`), so content can't double.
- **Cursors carry verified identities.** The server overwrites each awareness state with the sender's real name, photo, colour and role, and drops states for other client ids. Viewers and commenters see the note and the cursors live, but the server refuses their document updates.
- **Agents, the CLI and other devices join through the API.** An `updateIdea` without the live header (agent plugin, CLI, iOS, a tab that isn't live) goes to one editor in the room. That editor merges only the changed range into the shared document, so others keep typing. Everyone sees the author's photo in the presence stack and a caret labelled "via AI agent" or "via CLI" where the text changed. Version restores are announced the same way. If no editor is in the room, it restarts from the saved note.
- **Presence is a GraphQL field.** `ideaLivePresence(ideaId)` (`ideas.read`) lists who is in the note now and how (`app`, `agent`, `cli`). The CLI catalog and the agent tools are generated from it as usual, and the `manifest-team` skill tells agents to check it before editing a shared note.
- **Collaborators can open shared ideas.** `idea(ideaId)` now also returns ideas the caller has view access to, not only their own.

## Consequences

- Rooms live in the backend's memory. That's correct for one backend process (production runs `WEB_CONCURRENCY=1`). Running several processes needs a shared Socket.IO manager (Redis) and a shared document store, or sticky routing by idea.
- A redeploy drops rooms. Browsers reconnect and send what the new process is missing, so nothing typed is lost.
- An agent or CLI edit replaces the note's HTML. Text typed into the same paragraph in the second before the agent saved can be overwritten, as before. The skill tells agents to change only what was asked and to re-read first.
- The iOS app saves through the API, so its edits appear live in browsers ("via Manifest"). It doesn't show live cursors yet.
