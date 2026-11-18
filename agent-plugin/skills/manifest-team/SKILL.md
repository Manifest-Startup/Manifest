---
name: manifest-team
description: "Work on Manifest ideas together: invite collaborators, accept invitations, change roles, and keep or restore versions of an idea. Use when a person wants to share an idea, see who has access, respond to an invite, or go back to an earlier version."
---

# Collaborators and versions

## Collaborators
- `idea_collaborators`: who has access to an idea and their roles.
- `invite_collaborator` (ideaId, email, optional role): sends an email invitation. Confirm the address first.
- `my_collaboration_invitations`: invitations waiting for the person; `respond_to_invitation` accepts or declines one.
- `my_shared_ideas`: ideas others shared with the person.
- `update_collaborator_role` and `remove_collaborator` change someone's access (both need `confirm: true`; name the person and the idea).

## Versions
- `idea_versions`: the history of an idea.
- `create_idea_version` saves a snapshot with a short changeSummary: suggest one before big edits.
- `restore_idea_version` brings an older version back (needs `confirm: true`); offer to snapshot the current version first.
