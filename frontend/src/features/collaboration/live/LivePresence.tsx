import React from "react";
import type { LiveExternalEditor, LivePeer, LiveSnapshot } from "./liveNoteSession";

interface Person {
  key: string;
  name: string;
  avatarUrl: string | null;
  color: string;
  detail: string;
  badge?: string;
}

const initials = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("") || "?";

const BADGES: Record<string, string> = { agent: "AI", cli: ">_" };

export function livePeople(snapshot: LiveSnapshot): Person[] {
  const selfUser = snapshot.self?.userId;
  const seen = new Set<string>();
  const people: Person[] = [];
  snapshot.peers.forEach((peer: LivePeer) => {
    if (peer.userId === selfUser || seen.has(peer.userId)) return;
    seen.add(peer.userId);
    people.push({
      key: `app-${peer.userId}`,
      name: peer.name,
      avatarUrl: peer.avatarUrl,
      color: peer.color,
      detail: peer.canEdit ? "Editing now" : "Viewing now",
    });
  });
  snapshot.external.forEach((editor: LiveExternalEditor) => {
    people.push({
      key: `${editor.via}-${editor.userId}`,
      name: editor.name,
      avatarUrl: editor.avatarUrl,
      color: editor.color,
      detail: `Just edited via ${editor.viaLabel}`,
      badge: BADGES[editor.via],
    });
  });
  return people;
}

const MAX_SHOWN = 4;

/** Photos of everyone else in this note right now, Google Docs style. */
export const LivePresence: React.FC<{ snapshot: LiveSnapshot }> = ({ snapshot }) => {
  const people = livePeople(snapshot);
  const shown = people.slice(0, MAX_SHOWN);
  const extra = people.length - shown.length;
  const offline = snapshot.status === "offline" || snapshot.status === "denied";

  return (
    <div className="manifest-live-presence" data-testid="live-presence" aria-live="polite">
      <span
        className={`manifest-live-presence__dot ${offline ? "is-offline" : ""}`}
        title={offline ? snapshot.error || "Reconnecting…" : "Live: changes appear for everyone as you type"}
      />
      {snapshot.status === "live" && !snapshot.canEdit ? (
        <span className="manifest-live-presence__note">View only</span>
      ) : null}
      <ul className="manifest-live-presence__stack" aria-label="People in this note">
        {shown.map((person) => (
          <li
            key={person.key}
            className="manifest-live-presence__person"
            style={{ borderColor: person.color }}
            title={`${person.name} — ${person.detail}`}
          >
            {person.avatarUrl ? (
              <img src={person.avatarUrl} alt={person.name} referrerPolicy="no-referrer" />
            ) : (
              <span style={{ backgroundColor: person.color }} aria-label={person.name}>
                {initials(person.name)}
              </span>
            )}
            {person.badge ? <em className="manifest-live-presence__badge">{person.badge}</em> : null}
          </li>
        ))}
        {extra > 0 ? (
          <li className="manifest-live-presence__more" title={people.slice(MAX_SHOWN).map((p) => p.name).join(", ")}>
            +{extra}
          </li>
        ) : null}
      </ul>
    </div>
  );
};

export default LivePresence;
