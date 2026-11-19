# 0011. Ideas can live in a local vault folder; the account is opt-in Cloud sync

- Status: Accepted (2026-11-19). Phase 1: the desktop web app.
- Code: `frontend/src/features/vault/` (`mode.ts`, `fs.ts`, `format.ts`, `convert.ts`, `store.ts`, `execute.ts`, `runtime.ts`, `VaultGate.tsx`, `StorageSection.tsx`), `frontend/public/vault-sw.js`, the vault link in `core/apollo/client.ts`

## Context

Founders want their ideas to be files they own: a folder synced by iCloud Drive (or Dropbox, OneDrive) that works offline and opens in Obsidian too, like an Obsidian vault. Keeping everything in Supabase made the account mandatory, and the app was useless offline. Supabase stays, as an opt-in for what really needs a server.

## Decision

- **Storage mode per browser.** "Cloud" is today's account, the default and the only choice in Safari and Firefox, which can't open folders. "Vault" is a folder on this computer, available where the File System Access API exists (Chrome, Edge, Arc, Brave on desktop). The sign-in screen in those browsers offers "Open a vault folder" first. The choice and the folder handle live in this browser (`localStorage` `manifest.storage.v1`, IndexedDB `manifest-vault`).
- **The folder is the source of truth.** `Manifest/Ideas/<Title>.md` holds YAML frontmatter (`manifest_id`, `type: idea`, `created`, `updated`, `published`, `skills`, plus any other keys, kept as written), a `# Title` line and the note in Markdown. `Manifest/Documents/<Title>/<Document>.md` holds documents, with the same names as the account export (ADR 0005). Notes written in another app get a `manifest_id` the first time Manifest reads them. Account exports open too: their generated block is read, and the writing after it is kept. Renaming an idea renames its file and documents folder. Deleting moves them to `Manifest/.trash`.
- **Same app, different link.** In vault mode, an Apollo link answers the app's GraphQL operations from the folder (`execute.ts`). It resolves `profile`, `ideas`, `idea`, `createIdea`, `updateIdea` and `deleteIdea`, then walks the selection set so every screen works unchanged. Other queries come back empty. Mutations that need the account fail with "… needs Cloud sync". Share, versions, publish, Pitch Reels and voice are hidden. The vault code is a lazy chunk, so cloud users don't download it.
- **Markdown ↔ the editor.** Notes convert with Turndown (HTML → Markdown) and marked (Markdown → HTML). A save returns the editor's own HTML for the Markdown it just wrote, so the note never reflows under the cursor.
- **Sync is the folder's job.** Manifest re-reads the folder every 4 s while the tab is visible and refreshes the screen when files change. That is how edits from another computer (via iCloud), Obsidian or a text editor appear. Unsaved typing is never overwritten (the editor's existing rule).
- **Offline.** In vault mode, `vault-sw.js` caches the app shell and fingerprinted assets, never ideas or API responses. The app opens offline after one online visit. Switching to cloud unregisters it.
- **Moving over.** Settings → Storage shows the mode. In cloud mode, "Copy my ideas to a folder…" copies every idea and its documents, keeping their ids; already-copied ideas are skipped. "Turn on Cloud sync" switches the browser back to the account. The folder stays as it is.

## Consequences

- iPhone and iPad browsers, Safari and Firefox stay on the account. A native Apple app reading the same folder layout through iCloud Drive is the next step.
- AI document generation, the knowledge graph, live collaboration, sharing, publishing, versions, messages and universal search need Cloud sync in this phase. Generating documents into a vault with the founder's own key is planned next.
- A vault and the account don't sync with each other automatically yet. Moving is an explicit copy. Two-way Cloud sync of a vault is a later, paid-tier option.
- Concurrent edits of the same file on two computers resolve the way the folder sync resolves them (iCloud keeps a conflicted copy). Manifest shows whatever is in the file.
