---
description: Sync your Manifest vault with your account (like iCloud Drive or OneDrive)
---

Sync my Manifest vault (manifest-vault skill). Run `manifest_vault.py status`; if this computer isn't signed in, run `manifest_vault.py login`. Then `manifest_vault.py sync`, and if background sync is off, offer `manifest_vault.py install`. Tell me what changed, any conflicted copies, and where the vault is; remind me to start at `Manifest/Home.md` in Obsidian. Without a local shell, fall back to `vault_export` + `manifest_vault.py sync <file>`.
