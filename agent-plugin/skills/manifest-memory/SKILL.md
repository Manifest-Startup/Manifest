---
name: manifest-memory
description: "Remember the person across conversations and across agents with Manifest memory: recall what was decided earlier, remember new lasting facts (decisions, preferences, people, plans), correct or forget them, and find saved voice conversations. Use at the start of any Manifest work, whenever earlier context would help, when the person tells you something worth keeping, or says remember this, forget that, or what did we decide."
---

# Manifest memory

Manifest keeps one memory for the person, shared by every agent they use: Manifest voice, Claude Code, Codex, Cursor, Gemini CLI or any other app with the `manifest` server. Each memory is one short Markdown file in their vault's `Memory/` folder (`Memory/<idea>/…`, or `Memory/General/` for facts about the person), and each voice conversation is a transcript in `Conversations/`. Both sync to every computer and to the account, and only the person can see them, never an idea's collaborators.

## Rules for every agent

1. **Recall first.** At the start of Manifest work, call `recall` with the idea's idea id (or no idea for the person in general). Use what comes back naturally; don't read it out.
2. **Remember as you go.** When the person tells you something lasting, call `remember` right away: one short third-person sentence ("Mihir wants TideLine to sell to insurers first."), the idea id when it's about an idea, a `kind` (`fact`, `decision`, `preference`, `person`, `plan`, `question`) and `source` naming you (`claude-code`, `codex`, `cursor`, `voice`…). Don't ask permission for each one, and don't announce each one either; a short "noted" is enough when it fits.
3. **Keep Manifest facts in Manifest memory.** You may have a memory of your own; facts about the person's Manifest ideas belong here too, so the next agent sees them. Never store them only in your own memory.
4. **Change, don't pile up.** Saying the same thing again only refreshes it (status already_known). When a fact changed ("we're selling to cities now"), call `remember` with `replaces` set to the old memory's `id`; the old one moves to the vault's `.trash`.
5. **Forget on request.** "Forget that" means `forget_memory` with that memory's id. `update_memory` fixes a memory's wording.
6. **Never remember secrets.** No passwords, keys, tokens, account or ID numbers, or health details.

## Reading more

- `recall` with `query` finds memories by words ("pricing", "Ana"); without it, it returns the idea's and the general memories, newest first.
- `memories` lists all of them (or one idea's), for a review the person asks for. They can also edit them in the app under Account → Data & storage → Memory.
- Conversations: the app saves each voice conversation with `save_voice_conversation` when it ends, so you don't need to. A local agent can read `Conversations/*.md` in the vault folder (`manifest vault-folder` says where); each one links the idea and what was remembered from it.
- No plugin, only the folder? Read and write `Memory/*.md` directly: front matter (`type: memory`, `idea`, idea id, `kind`, `created`, `updated`, `source`), then the fact as the body. Sync picks it up.
