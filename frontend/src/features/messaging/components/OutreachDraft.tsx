import React, { useEffect, useRef, useState } from "react";
import { useMutation } from "@apollo/client/react";

import { DECIDE_APPROVAL, EDIT_GOAL_DRAFT, FOLLOW_UP_GOAL, RETRY_GOAL_STEP } from "features/core/apollo/queries";
import type { GoalDraft, GoalSummary } from "features/core/apollo/operationTypes";

import InboxAvatar from "./InboxAvatar";

export const draftName = (draft: GoalDraft) =>
  draft.toName || (draft.channel === "open_media" && draft.to ? `@${draft.to}` : draft.to) || "Someone";

export const initialsOf = (name: string) =>
  name
    .replace(/^@/, "")
    .split(/[\s.@_-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]!.toUpperCase())
    .join("");

export const pendingApproval = (goal: GoalSummary) => goal.approvals.find((a) => a.status === "pending") ?? null;

const countWords = (text: string) => (text.match(/[A-Za-z0-9'’-]+/g) ?? []).length;
const OPT_OUT = /(won'?t (follow up|write|email|reach out|bother)|not (relevant|a fit|for you)|no worries if not|just say so)/i;

/** Words in the message itself, as Manifest counts them: not the easy-out line or the sign-off. */
const words = (text: string) => {
  const lines = text.trim().split("\n").filter((line) => !OPT_OUT.test(line));
  while (lines.length && countWords(lines[lines.length - 1]!) <= 5) lines.pop();
  return countWords(lines.join("\n"));
};

const host = (url: string) => {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "source";
  }
};

const when = (iso: string | null) => {
  if (!iso) return "";
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleString(undefined, { weekday: "short", hour: "numeric", minute: "2-digit" });
};

/** Where a message stands once it's out of the person's hands, in one plain line. */
export function draftStatus(goal: GoalSummary): string {
  const draft = goal.draft;
  if (!draft) return "";
  if (pendingApproval(goal)) return "Waiting for your OK";
  if (draft.reply) return `Replied: “${draft.reply.replace(/<<<UNTRUSTED_(BEGIN|END):reply>>>/g, "").trim().slice(0, 120)}”`;
  if (draft.sendStatus === "blocked" || draft.sendStatus === "failed") return "Not sent yet: needs you";
  if (draft.followedUp) return "Followed up";
  if (draft.sendStatus === "cancelled") return "Not sent";
  if (draft.replyStatus === "blocked") return "No reply yet";
  if (draft.sentAt) return `${draft.followUpNumber ? "Follow-up sent" : "Sent"} ${when(draft.sentAt)} · waiting for a reply`;
  return goal.status === "cancelled" ? "Not sent" : "Sending…";
}

interface OutreachDraftProps {
  goal: GoalSummary;
  /** How many messages are waiting, and this one's place, for "2 of 5". */
  position?: { index: number; total: number };
  onBack: () => void;
  /** After Send or Skip: open the next waiting message (or close). */
  onDecided: () => void;
  /** Open another goal's card (a follow-up just prepared). */
  onOpenGoal?: (goalId: string) => void;
}

/** One prepared message in full: who and why, the exact text, and Send / Edit / Skip. Sending
 * approves exactly this text (ADR 0020); an edit replaces the approval before anything goes out. */
const OutreachDraft: React.FC<OutreachDraftProps> = ({ goal, position, onBack, onDecided, onOpenGoal }) => {
  const draft = goal.draft as GoalDraft;
  const approval = pendingApproval(goal);
  const [decide, { loading: deciding }] = useMutation(DECIDE_APPROVAL);
  const [edit, { loading: saving }] = useMutation(EDIT_GOAL_DRAFT);
  const [retry, { loading: retrying }] = useMutation(RETRY_GOAL_STEP);
  const [followUp, { loading: following }] = useMutation(FOLLOW_UP_GOAL);
  const [editing, setEditing] = useState(false);
  const [subject, setSubject] = useState(draft.subject ?? "");
  const [body, setBody] = useState(draft.body ?? "");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const bodyRef = useRef<HTMLTextAreaElement>(null);
  const isEmail = draft.channel === "email";
  const name = draftName(draft);
  const busy = deciding || saving || retrying || following;
  const canOfferFollowUp = Boolean(draft.sentAt && !draft.reply && !draft.followedUp && draft.followUpState);
  const prepareFollowUp = () =>
    void run(async () => {
      const result = await followUp({ variables: { goalId: goal.id } });
      const next = result?.data?.followUpGoal.id;
      if (next) onOpenGoal?.(next);
    });

  useEffect(() => {
    if (!editing) {
      setSubject(draft.subject ?? "");
      setBody(draft.body ?? "");
    }
  }, [draft.subject, draft.body, editing]);
  useEffect(() => {
    if (editing) bodyRef.current?.focus();
  }, [editing]);

  const run = async (work: () => Promise<unknown>) => {
    setError(null);
    try {
      await work();
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "That didn't go through. Try again.");
      return false;
    }
  };
  const answer = async (approve: boolean) => {
    if (!approval) return;
    const ok = await run(() => decide({ variables: { approvalId: approval.id, approve, scopeSha256: approval.scopeSha256 } }));
    if (ok) onDecided();
  };
  const save = async () => {
    const ok = await run(() =>
      edit({ variables: { goalId: goal.id, body, subject: isEmail ? subject : undefined } }),
    );
    if (ok) {
      setEditing(false);
      setNotice("Saved. Read it once more, then send.");
    }
  };

  const evidence = draft.evidence.filter((e) => e.text);
  // A send that stopped (no mailbox) or failed (Open Media refused it) waits for "Try again";
  // the person's yes still covers exactly this text.
  const blocked = draft.sendStatus === "blocked" || draft.sendStatus === "failed";
  const count = words(editing ? body : draft.body ?? "");

  return (
    <section className="om-thread-pane" aria-label={`Message to ${name}`} data-testid={`outreach-draft-${goal.id}`}>
      <header className="om-thread-header">
        <button type="button" className="om-icon-button om-back" aria-label="Back to messages" onClick={onBack}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" d="m15 18-6-6 6-6" />
          </svg>
        </button>
        <div className="om-thread-who">
          <InboxAvatar name={name} initials={initialsOf(name)} small />
          <p className="om-thread-name">{name}</p>
          <span className="om-thread-meta">
            {[draft.organization, isEmail ? "Email" : "Open Media"].filter(Boolean).join(" · ")}
            {position && position.total > 1 ? ` · ${position.index + 1} of ${position.total}` : ""}
          </span>
        </div>
        <span className="om-header-spacer" />
      </header>
      <div className="om-thread-scroll">
        <div className="om-draft">
          {draft.why || evidence.length ? (
            <div className="om-draft-why">
              <p className="om-draft-label">{draft.followUpNumber ? "Following up" : "Why them"}</p>
              {draft.why ? <p>{draft.why}</p> : null}
              {evidence.length ? (
                <ul>
                  {evidence.map((e) => (
                    <li key={e.text}>
                      {e.text}
                      {e.url ? (
                        <>
                          {" "}
                          <a href={e.url} target="_blank" rel="noreferrer noopener">
                            {host(e.url)}
                          </a>
                        </>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}

          <div className="om-draft-card" data-editing={editing}>
            <dl className="om-draft-fields">
              <div>
                <dt>To</dt>
                <dd>{isEmail ? `${draft.toName ? `${draft.toName} · ` : ""}${draft.to}` : `@${draft.to} on Open Media`}</dd>
              </div>
              <div>
                <dt>From</dt>
                <dd>
                  {draft.from ??
                    (!isEmail
                      ? "Your Open Media account"
                      : draft.mailboxReady === false
                        ? "No mailbox can send yet"
                        : "Your email, connected in Open Media")}
                </dd>
              </div>
              {isEmail ? (
                <div>
                  <dt>Subject</dt>
                  <dd>
                    {editing ? (
                      <input
                        className="om-draft-input"
                        value={subject}
                        maxLength={200}
                        onChange={(e) => setSubject(e.target.value)}
                        aria-label="Subject"
                      />
                    ) : (
                      <strong>{draft.subject}</strong>
                    )}
                  </dd>
                </div>
              ) : null}
            </dl>
            {editing ? (
              <textarea
                ref={bodyRef}
                className="om-draft-body om-draft-input"
                value={body}
                rows={Math.min(20, Math.max(8, body.split("\n").reduce((n, line) => n + Math.max(1, Math.ceil(line.length / 64)), 1)))}
                onChange={(e) => setBody(e.target.value)}
                aria-label="Message"
                onKeyDown={(e) => {
                  if (e.key === "Escape") setEditing(false);
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void save();
                }}
              />
            ) : (
              <p className="om-draft-body">{draft.body}</p>
            )}
            <p className="om-draft-meta">
              {count} words{draft.edited ? " · edited by you" : ""}
              {count > 110 ? " · shorter messages get more replies" : ""}
            </p>
          </div>

          {draft.followUp && approval && !draft.followUpNumber ? (
            <details className="om-draft-follow">
              <summary>Follow-up for later, if there&apos;s no reply</summary>
              <p>{draft.followUp}</p>
            </details>
          ) : null}

          {draft.reply ? (
            <div className="om-draft-reply">
              <p className="om-draft-label">{name} replied</p>
              <p>{draft.reply.replace(/<<<UNTRUSTED_(BEGIN|END):reply>>>/g, "").trim()}</p>
              <p className="om-draft-meta">The whole conversation is in your inbox. Ask Voice to help you answer.</p>
            </div>
          ) : null}

          {blocked ? (
            <div className="om-draft-blocked">
              <p>{draft.sendError}</p>
              {error ? <p role="alert" className="om-goal-error">{error}</p> : null}
              <div className="om-draft-actions">
                <button
                  type="button"
                  className="om-goal-primary"
                  disabled={busy}
                  onClick={() => void run(() => retry({ variables: { goalId: goal.id, stepKey: "send" } }))}
                >
                  {retrying ? "Trying…" : "Try again"}
                </button>
                {draft.composeUrl ? (
                  <a className="om-goal-secondary om-draft-link" href={draft.composeUrl} target="_blank" rel="noreferrer noopener">
                    Open in Gmail
                  </a>
                ) : null}
              </div>
            </div>
          ) : !approval ? (
            <p className="om-draft-meta">{draftStatus(goal)}</p>
          ) : null}

          {canOfferFollowUp ? (
            <div className="om-draft-why" data-testid="follow-up-offer">
              <p className="om-draft-label">No reply yet?</p>
              {draft.followUp ? <p className="om-draft-body">{draft.followUp}</p> : null}
              {draft.followUpState?.allowed ? (
                <div className="om-draft-actions" style={{ marginTop: 10 }}>
                  <button type="button" className="om-goal-primary" disabled={busy} onClick={prepareFollowUp}>
                    {following ? "Preparing…" : "Draft follow-up"}
                  </button>
                </div>
              ) : (
                <p className="om-draft-meta">{draft.followUpState?.reason}</p>
              )}
              {error ? <p role="alert" className="om-goal-error">{error}</p> : null}
            </div>
          ) : null}
        </div>
      </div>
      {approval ? (
        <footer className="om-draft-footer">
          {notice && !error ? <p role="status" className="om-draft-notice">{notice}</p> : null}
          {error ? (
            <p role="alert" className="om-goal-error">
              {error}
            </p>
          ) : null}
          {draft.mailboxReady === false && isEmail ? (
            <p className="om-draft-warning">
              No mailbox in Open Media can send yet. Connect yours (Open Media, Settings, Email &amp; connections)
              before you send{draft.composeUrl ? (
                <>
                  , or{" "}
                  <a href={draft.composeUrl} target="_blank" rel="noreferrer noopener">
                    open it in Gmail
                  </a>
                </>
              ) : null}
              .
            </p>
          ) : null}
          <div className="om-draft-actions">
              {editing ? (
                <>
                  <button type="button" className="om-goal-primary" disabled={busy || !body.trim()} onClick={() => void save()}>
                    Save changes
                  </button>
                  <button type="button" className="om-goal-secondary" disabled={busy} onClick={() => setEditing(false)}>
                    Cancel
                  </button>
                </>
              ) : (
                <>
                  <button type="button" className="om-goal-primary" disabled={busy} onClick={() => void answer(true)} data-testid="outreach-send">
                    {deciding ? "Sending…" : isEmail ? "Send email" : "Send message"}
                  </button>
                  <button type="button" className="om-goal-secondary" disabled={busy} onClick={() => { setNotice(null); setEditing(true); }}>
                    Edit
                  </button>
                  <button type="button" className="om-goal-secondary" disabled={busy} onClick={() => void answer(false)} data-testid="outreach-skip">
                    Don&apos;t send
                  </button>
                </>
              )}
          </div>
          {!editing ? (
            <p className="om-draft-meta">
              {approval.consequences} Or ask Voice to read it to you.
            </p>
          ) : null}
        </footer>
      ) : null}
    </section>
  );
};

export default OutreachDraft;
