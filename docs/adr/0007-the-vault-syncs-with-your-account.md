# 0007. The vault syncs with your account, like iCloud Drive or OneDrive

- Status: Accepted (2026-11-18). Builds on [0005](0005-agents-write-documents-and-keep-a-local-vault.md), which left notes local only.
- Code: `backend/app/services/ideas/vault_sync.py`, `supabase/migrations/20261118060000_vault_files.sql`, `agent-plugin/skills/manifest-vault/scripts/manifest_vault.py`

## Context

The vault was one-way and agent-driven: an agent pulled `vaultExport` into `~/Manifest Vault`, and notes lived on one computer. Founders expect it to behave like iCloud Drive or OneDrive: sign in once, edit offline, and see the same vault on every computer without asking an agent.

## Decision

- **Your part of the vault lives in your account.** `vault_files` holds one row per path (`user_id`, `path`, `content`, `sha256`, `deleted`, `device`). It stores the person's files outside `Manifest/` (.md, .txt, .canvas up to 512 KB, 5,000 files, no hidden folders) and their writing around the generated block in `Manifest/` files (the "overlay", with the block replaced by `<!-- manifest:generated -->`). `Manifest/` itself still comes from `vaultExport`.
- **Two GraphQL fields.** `vaultFiles(sinceUpdatedAt)` lists changes including tombstones; `putVaultFile(path, content, baseSha256, delete)` is compare-and-swap on the hash, returning `saved`, `unchanged` or `conflict` with the account's version. Both use `ideas.read` / `ideas.write`, so the CLI and MCP tools are regenerated as usual.
- **A sync client with no dependencies.** `manifest_vault.py login` uses the CLI's browser sign-in (ADR 0003) and shares `~/.config/manifest/cli.json`. `sync` runs a three-way sync against the last synced hashes; `install` adds a LaunchAgent (macOS) or systemd user service (Linux) running `watch`, which uploads edits within seconds, checks the account every 30 s and refreshes `Manifest/` every 5 minutes. Offline, edits wait and `status` shows them as pending.
- **Nothing is lost.** Changed in two places: both kept, the local one as `<name> (conflicted copy <computer> <time>).md`. Deleted elsewhere: moved to the vault's `.trash/`. Edited here after a delete elsewhere: re-uploaded. If more than half of the synced files vanish at once, deletions aren't sent unless `--allow-mass-delete`.
- **It looks like Manifest.** The client writes the Manifest mark to `Manifest/Assets/Manifest logo.svg`, the export's `Home.md` embeds it with a summary callout and the `manifest-home` CSS class, and a one-time Obsidian snippet (`.obsidian/snippets/manifest.css`) styles it in light and dark themes.

## Consequences

- Vault notes are now personal data in Manifest: they're in the DSAR export and the erasure purge, and cascade with the user.
- Binary attachments (images, PDFs) stay on the computer they were added on.
- Concurrent edits are resolved per file, not merged line by line.
