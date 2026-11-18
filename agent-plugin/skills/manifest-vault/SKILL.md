---
name: manifest-vault
description: "Keep the founder's ideas, Manifest documents and their own notes as an Obsidian-style vault of linked Markdown files on their computer, and save notes while they talk or write about an idea. Use when a person shares an idea, thinks out loud, asks to save or find a note, wants their ideas in Obsidian or as files, or asks to see how their ideas connect (knowledge graph)."
---

# Local vault and knowledge graph

The vault is a folder of Markdown files the person owns: `$MANIFEST_VAULT`, or `~/Manifest Vault` by default (`manifest_vault.py where` prints it; an existing Obsidian vault works too, Manifest only writes under `Manifest/`). Obsidian's Graph view turns it into a knowledge graph: ideas link to their documents, the skills they need, related ideas, interviews and notes.

The helper is `scripts/manifest_vault.py` next to this file (Claude Code: `${CLAUDE_PLUGIN_ROOT}/skills/manifest-vault/scripts/manifest_vault.py`; run it with `python3`). It needs Python 3.9+, uses only the standard library and works offline. It never deletes anything, keeps the person's own writing outside the generated block, and never overwrites a file it didn't write. You need a local shell for it; hosts without one (claude.ai, ChatGPT) can't keep a local vault, so say so.

## Save notes as the person talks
Whenever the person describes an idea, thinks out loud, or dictates a note, save it right away; don't wait to be asked twice:

1. Keep their words. Light cleanup only (typos, filler); put your summary or open questions under a `## Summary` or `## Questions` heading after their text.
2. `manifest_vault.py note --title "<short title>" --idea "<idea title>" [--tag <tag>] -` with the text on stdin. Link every idea the note is about with `--idea` (the idea's exact Manifest title) so the graph connects.
3. If it's a new idea, also create it in Manifest (`create_idea`, after `find_similar_ideas`; see manifest-ideas), then sync so the idea's file exists for the note's link.
4. Tell them where it was saved in one line.

## Sync Manifest into the vault
1. `manifest_vault.py since` prints the last sync time (empty the first time).
2. Call `vault_export` with `sinceUpdatedAt` set to it (omit it the first time, or for a full refresh).
3. Save the tool's JSON result to a temporary file and run `manifest_vault.py sync <file>`; it prints what was created or updated. Remove the temporary file.
4. Sync after you create an idea, write or generate documents, or finish an interview, so the vault matches Manifest.

## What's in the vault
- `Manifest/Home.md`: the map of everything.
- `Manifest/Ideas/<title>.md`: description, documents, skills needed, related ideas, link to the app, and a `## My notes` section that's theirs.
- `Manifest/Documents/<idea>/<document>.md`: canvas, pitch deck, PRD, patent draft, similar ideas.
- `Manifest/Skills/<skill>.md` and `Manifest/Interviews/<date> <idea>.md`.
- `Notes/<date> <title>.md`: their notes, with `ideas:` and `tags:` frontmatter.

## Finding things
Search the vault folder (filenames, frontmatter, `[[links]]`) before answering "what did I say about…" questions, and quote the note with its path. Notes are private: never paste them into public places (published ideas, comments, pitch shorts).
