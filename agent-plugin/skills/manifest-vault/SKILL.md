---
name: manifest-vault
description: "Keep the founder's ideas, Manifest documents and their own notes as an Obsidian-style vault of linked Markdown files on their computer, and save notes while they talk or write about an idea. Use when a person shares an idea, thinks out loud, asks to save or find a note, wants their ideas in Obsidian or as files, asks to see how their ideas connect (knowledge graph), or wants the vault synced across computers like iCloud or OneDrive."
---

# Local vault and knowledge graph

The vault is a folder of Markdown files the person owns: `$MANIFEST_VAULT`, or `~/Manifest Vault` by default (`manifest_vault.py where` prints it; an existing Obsidian vault works too, Manifest only writes under `Manifest/`). Obsidian's Graph view turns it into a knowledge graph: ideas link to their documents, the skills they need, related ideas, interviews and notes.

The helper is `scripts/manifest_vault.py` next to this file (Claude Code: `${CLAUDE_PLUGIN_ROOT}/skills/manifest-vault/scripts/manifest_vault.py`; run it with `python3`). It needs Python 3.9+, uses only the standard library and works offline; changes sync when back online. It never deletes anything, keeps the person's own writing outside the generated block, and never overwrites a file it didn't write. You need a local shell for it; hosts without one (claude.ai, ChatGPT) can't keep a local vault, so say so.

## Save notes as the person talks
Whenever the person describes an idea, thinks out loud, or dictates a note, save it right away; don't wait to be asked twice:

1. Keep their words. Light cleanup only (typos, filler); put your summary or open questions under a `## Summary` or `## Questions` heading after their text.
2. `manifest_vault.py note --title "<short title>" --idea "<idea title>" [--tag <tag>] -` with the text on stdin. Link every idea the note is about with `--idea` (the idea's exact Manifest title) so the graph connects.
3. If it's a new idea, also create it in Manifest (`create_idea`, after `find_similar_ideas`; see manifest-ideas), then `manifest_vault.py sync` so the idea's file exists for the note's link and the note reaches their account.
4. Tell them where it was saved in one line.

## Sync with the account (like iCloud Drive or OneDrive)
The vault syncs both ways with the person's Manifest account, so every computer they sign in on has the same vault. Set it up once per computer:

1. `manifest_vault.py login` opens the browser to approve this computer (it shares the `manifest` CLI's sign-in).
2. `manifest_vault.py sync` runs the first sync and prints what changed.
3. `manifest_vault.py install` keeps it syncing in the background from login (macOS LaunchAgent, Linux systemd user service): edits upload within seconds, other computers' changes arrive within about 30 s. Offline, changes wait and sync when back online.

`manifest_vault.py status` shows the account, last sync, pending changes and whether background sync runs; `uninstall` turns it off and leaves the files. Sync after you create an idea, write documents or finish an interview if background sync isn't on.

What syncs: `Manifest/` comes from the account; the person's own .md/.txt/.canvas files elsewhere (like `Notes/`) and their writing around the generated block in `Manifest/` files go both ways. Hidden folders (`.obsidian`, `.trash`) and images stay local. Nothing is lost: a file changed on two computers keeps both (`… (conflicted copy <computer> <time>).md`), a file deleted on another computer moves to `.trash/`, and if most files vanish at once (an unplugged drive) deletions aren't sent.

The sync client calls `vault_files` and `put_vault_file` itself; agents rarely need them, except to read a note from another computer when there's no local vault (`vault_files`) or save one there (`put_vault_file` with `path` like `Notes/<date> <title>.md` and no `baseSha256` for a new file).

**No local sign-in (agent only):** call `vault_export` with `sinceUpdatedAt` from `manifest_vault.py since`, save the JSON result to a temporary file, run `manifest_vault.py sync <file>` (one way, offline), and remove the file.

## What's in the vault
- `Manifest/Home.md`: the map of everything, with the Manifest logo (`Manifest/Assets/Manifest logo.svg`) and an Obsidian snippet (`.obsidian/snippets/manifest.css`, Settings → Appearance → CSS snippets) that styles it.
- `Manifest/Ideas/<title>.md`: description, documents, skills needed, related ideas, link to the app, and a `## My notes` section that's theirs.
- `Manifest/Documents/<idea>/<document>.md`: canvas, pitch deck, PRD, patent draft, similar ideas.
- `Manifest/Skills/<skill>.md` and `Manifest/Interviews/<date> <idea>.md`.
- `Notes/<date> <title>.md`: their notes, with `ideas:` and `tags:` frontmatter.

## Finding things
Search the vault folder (filenames, frontmatter, `[[links]]`) before answering "what did I say about…" questions, and quote the note with its path. Notes are private: never paste them into public places (published ideas, comments, pitch shorts).
