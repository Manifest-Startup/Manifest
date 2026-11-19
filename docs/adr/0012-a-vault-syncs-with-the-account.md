# 0012. A vault syncs with the account; every idea keeps a version history in the folder

- Status: Accepted (2026-11-19). Builds on [0011](0011-ideas-live-in-a-local-vault-folder.md).
- Code: `frontend/src/features/vault/sync.ts` (the engine), `cloudSync.ts` (account API, schedule, status), `history.ts`, `store.ts` (`snapshot`, `writeIdea`, versions), Settings → Storage; GraphQL `Idea.updatedAt`, `IdeaSummary.updatedAt`

## Context

People want one set of ideas: open a vault folder (offline, synced by iCloud Drive) and sign in, and see the folder's notes and the account's combined, with edits going both ways. If the same idea changed in both places, the latest version should win. They also asked for version history, "git or something".

## Decision

- **Vault plus account.** In vault mode, Settings → Storage → *Sync with your Manifest account*: sign in (Open Media, back to Settings) and turn sync on. Signed-in people can also choose *Use a vault folder…* from the account, which opens a folder with sync on. The folder stays the working copy, so it works offline and at full speed. Sync runs 4 s after an edit, every minute while the app is visible, when the connection returns, and on *Sync now*.
- **Knowing what changed.** Each synced idea has a baseline: the vault content's FNV-1a hash and the account's `updatedAt` (now exposed in GraphQL; a database trigger keeps it current). The baselines live in `Manifest/.sync/<account>.json` inside the vault, so another computer opening the same folder through iCloud continues from them.
- **Merging.**
  - **Changed on one side:** that side's version goes to the other. This covers title, note, skills and the five documents; documents go up through `saveIdeaDocument`.
  - **Changed on both:** the newer one wins (the file's time against the account's `updatedAt`), and the other version is saved in the vault's history.
  - **Only on one side:** copied to the other. Ideas copied with the account's id are recognised as the same idea.
  - **Deleted on one side and untouched on the other:** deleted on the other side too. The vault's copy goes to `Manifest/.trash`.
  - **Edited after being deleted elsewhere:** the edit wins and the idea comes back.
  - A failure on one idea is reported and doesn't stop the rest.
- **Version history without git.** `Manifest/.history/<manifest_id>/<time> <kind>.md` keeps the whole idea file as it was. Snapshots are taken while writing (at most every 90 s, like the account's checkpoints), on *Save version*, before a restore, and for the side that lost a sync or conflict. The existing Versions panel lists and restores them in vault mode. Git isn't used: a `.git` folder inside iCloud Drive is corrupted by file-level sync, and a browser git would add a large library for little gain over readable snapshots.

## Consequences

- Nothing is lost by a merge: the replaced version is always in history or in `.trash`.
- "Newest wins" works per idea, not per paragraph. Two people editing the same idea offline don't get a combined text; the other version is one click away in history. Live collaboration (ADR 0008) remains the way to write together.
- Snapshots grow the folder slowly (one small Markdown file per checkpoint). Pruning old automatic snapshots can come later.
- Sharing, publishing and the other account features still run from the account. In vault mode they appear once the synced idea is opened in account mode.
