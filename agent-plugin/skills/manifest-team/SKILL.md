---
name: manifest-team
description: "Work on Manifest ideas together: invite collaborators, accept invitations, change roles, see who is editing a shared note live, and keep or restore versions of an idea. Use when a person wants to share an idea, see who has access or who is in the note now, edit a note others are editing, respond to an invite, or go back to an earlier version."
---

# Collaborators and versions

## Collaborators
- `idea_collaborators`: who has access to an idea and their roles.
- `invite_collaborator` (ideaId, email, optional role): sends an email invitation. Confirm the address first.
- `my_collaboration_invitations`: invitations waiting for the person; `respond_to_invitation` accepts or declines one.
- `my_shared_ideas`: ideas others shared with the person.
- `update_collaborator_role` and `remove_collaborator` change someone's access (both need `confirm: true`; name the person and the idea).

## Editing a shared note live
Shared notes are edited together in real time in the Manifest app, with each person's cursor and photo, like Google Docs.
- `idea_live_presence` (ideaId): who is in the note right now (name, photo, `via` app/agent/cli). Check it before changing a shared note and tell the person who else is there.
- To edit, read the note with `idea`, change only what was asked, and save with `update_idea` (full description HTML). The change merges into the live document; everyone sees it appear at the edited spot with the person's photo labelled "via AI agent" (or "via CLI" from the `manifest` CLI). Keep the rest of the HTML exactly as read so you don't undo what others just typed; re-read first if some time has passed.

## Versions
- `idea_versions`: the history of an idea.
- `create_idea_version` saves a snapshot with a short changeSummary: suggest one before big edits.
- `restore_idea_version` brings an older version back (needs `confirm: true`); offer to snapshot the current version first.
