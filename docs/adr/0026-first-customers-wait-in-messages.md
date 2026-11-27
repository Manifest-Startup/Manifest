# 0026. Outreach waits in Messages, goes from your own mailbox, and comes back in their words

- Status: Proposed (2026-11-27).
- Builds on: ADR 0018 (idea to first customers), ADR 0020 (goals, exact-scope approvals), ADR 0001 (Open Media carries communication).
- Code: `backend/app/services/ideas/outreach.py` (the writing rules, checks, the hand-off to goals), `customer_discovery.py` (contact checks, `queue_outreach`, `set_recipient`), `services/goals/capabilities.py` (`email.prepare`, `email.send`, email replies), `engine.py` (`email_outreach_plan`, `edit_draft`), `integrations/open_media/mail.py`; `frontend/src/features/messaging/components/OutreachDraft.tsx`, `GoalsPanel.tsx`; the voice prompt and `SPEECH_SHAPES` in `services/voice/live/`; the `manifest-customers` skill; Open Media `POST /v1/me/email`, `GET /v1/me/mailboxes`, `POST /v1/me/mailboxes/{id}/sync`.
- Evidence for the writing rules: `docs/CUSTOMER_OUTREACH.md`.

## Context

ADR 0018 stopped at prepared emails in a note, with Open in Gmail links. Founders had to copy every message out, nothing tracked who answered, and voice couldn't send anything. The drafts could also read like sales email, and an address counted as verified whenever the agent attached any URL to it.

## Decision

- **Every prepared message with a verified recipient becomes a goal** (ADR 0020): prepare → send (tier 2, exact-scope approval) → wait for the reply → remember it. It shows in Messages under "Waiting for your OK". The card shows who it's for and why (evidence with links), the from address, the subject and the full text, with Send, Edit and Don't send. After a decision the next waiting message opens. Re-drafting updates a waiting message in place, and a sent one is never touched.
- **Email goes from the person's own mailbox through Open Media**, the mailbox they connected there. Manifest never holds mail credentials. Open Media's new `POST /v1/me/email` takes an `Idempotency-Key` (the goal step id) and derives the Message-ID from it, so a retry finds the stored copy and doesn't send twice. A send with no sending mailbox blocks with an Open in Gmail fallback, and the card warns about that before Send, using the mailbox looked up when the draft was prepared. Prospects reachable on Open Media get a direct message instead (`message.send`).
- **Replies come back in their words.** The reply step fetches new mail through `POST /v1/me/mailboxes/{id}/sync`, takes the first email from that address after the send, strips the quoted original, stores it verbatim as an `external_claim` with the email as its source, and fences it for any model. Answered goals stay listed for 14 days, so the reply is visible in Messages and to voice.
- **An edit needs a new yes.** `editGoalDraft` changes the held text and the pending approval is superseded, so the old hash no longer works. Voice reads the new version back before asking again.
- **Rules enforced in code** (`outreach.check`): drafts with placeholders, fake Re:/Fwd: subjects, invented familiarity, sales clichés, or fewer than 25 or more than 150 words are refused, and agents get back what to fix. Every message gets an easy opt-out line (placed above any sign-off) and the sender's name. Softer issues become notes on the card: more than 90 words, a long subject, several questions, extra links.
- **An address is a recipient only when it's really found.** The cited page is read and must show it (also as "name [at] domain" or a mailto link), a provider like Apollo or Hunter vouched for it, or the founder gave it (`setOutreachRecipient`). An agent can't just claim it's verified. Open Media handles are checked against real profiles.
- **Voice** goes through waiting messages one at a time. It says who and why, reads the message word for word, and calls `decide_approval` only after a clear yes; "change it" calls `edit_goal_draft`. "Send them all" covers only messages already read aloud. Voice sees goals reshaped (draft, pending approvals, spoken report) so eight drafts fit in one answer. `edit_goal_draft` joined the core voice tools.

## Consequences

- Sending email needs a mailbox with outgoing (SMTP) settings connected in Open Media. Without one, the card offers Open in Gmail.
- A reply is only seen after Manifest syncs the mailbox. The goal sweep does that every 15 minutes while a reply is awaited, and the mailbox sync is rate-limited by Open Media.
- One crash window remains: SMTP accepted the email, then the Worker died before storing the copy. A retry would then send a second time. That window is milliseconds and is documented here.
- Follow-ups (2026-11-27): after at least three days without a reply, `followUpGoal` (the card's "Draft follow-up" button, or voice) prepares the drafted follow-up, or the founder's own words, as "Re: <subject>" with `in_reply_to` set to the first email's Message-ID, so it threads in the reader's mail app. It waits for a yes like the first email. There are at most two follow-ups, a bare "bumping this" is refused, and the first goal stops waiting. Nothing is followed up automatically.
- Voice greets only after the pipeline has started and the person has connected. A greeting queued earlier was dropped on slow servers.
