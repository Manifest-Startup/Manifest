# 0019. Feedback said to Manifest becomes one GitHub issue, with everyone who asked counted

- Status: Accepted (2026-11-22).
- Code: `backend/app/services/operations/user_feedback.py` (matching, counting, redaction), `backend/app/services/integrations/github_issues.py` (token, headers, labels), GraphQL `reportFeedback` in `backend/app/graphql/resolvers/survey.py` / `types/survey.py`; voice: `services/voice/live/bot.py` (prompt) and `tools.py` (core tool); local voice: `mcp_server/src/manifest_cli/agents.py` (`VOICE_STYLE`); plugin: `agent-plugin/skills/manifest/SKILL.md`, `commands/feedback.md`. Tests: `backend/tests/test_user_feedback.py`.

## Context

The owner wants every bug, enhancement and improvement people mention while talking to Manifest to land in the `Manifest-Startup/Manifest` issues directly, without duplicates, and with a visible count of how many people asked for the same thing. Issues used to live on a GitHub Project board (removed 2026-11-22; its issues were recreated in the public repo as #67–#102, because GitHub won't transfer issues from a private repository to a public one).

## Decision

- **One GraphQL mutation, everywhere.** `reportFeedback(kind, title, details, source, duplicateOf, forceNew)` reaches voice (a core tool), `/mcp`, the plugin (`/feedback`) and the CLI through the generated catalog. Any signed-in person can call it (`account.read`), up to 10 times an hour.
- **Manifest's token, not the person's.** Issues are filed with the server's `MANIFEST_GITHUB_TOKEN` (needs Issues read/write on the repo) into `MANIFEST_FEEDBACK_REPO`, then `MANIFEST_GITHUB_REPO`, then `Manifest-Startup/Manifest`. A person's own GitHub connection (ADR 0016) is never used.
- **No duplicates; the model judges paraphrases.** Candidates come from GitHub search (all words, then any word) plus open `user-feedback` issues, ranked by title similarity. A close match (≥ 0.72) gets the person added automatically. Anything else that shares a meaningful word goes back as `possible_duplicates`, without filing. The agent, which understands meaning, then picks one (`duplicateOf`) or files it as new (`forceNew`). Only open issues are matched.
- **People are counted once and stay anonymous.** The issue body keeps a hidden list of reporter hashes (`sha256("manifest-feedback:" + user id)`, 16 hex characters) and a visible "Reported by N people" line. Each new person adds a comment with their words. The same person reporting again changes nothing. An issue that was written by hand counts its author as one.
- **The repository is public.** Titles and details are redacted (emails, phone and long numbers, key-like strings), and no name or id is posted. The voice tells the person once that it's public.

## Consequences

- Production needs `MANIFEST_GITHUB_TOKEN` on Render. Without it, the tool answers that feedback filing isn't set up.
- GitHub search indexes new issues with a delay of a few seconds. Two people reporting the same thing within that window are still matched through the `user-feedback` label listing.
- Body edits race if two people join the same issue in the same second. One count can be lost, but both comments stay.
