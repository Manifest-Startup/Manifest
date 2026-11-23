import React, { useMemo, useState } from 'react';
import { useMutation, useQuery } from '@apollo/client/react';

import type { MemoryItem } from '../core/apollo/operationTypes';
import { FORGET_MEMORY, GET_MEMORIES, UPDATE_MEMORY } from '../core/apollo/queries';

const GENERAL = 'About you';

function MemoryRow({ memory, onChanged }: { memory: MemoryItem; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(memory.text);
  const [error, setError] = useState<string | null>(null);
  const [update, { loading: saving }] = useMutation(UPDATE_MEMORY);
  const [forget, { loading: forgetting }] = useMutation(FORGET_MEMORY);

  const run = async (action: () => Promise<unknown>) => {
    setError(null);
    try {
      await action();
      setEditing(false);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "That didn't go through. Try again.");
    }
  };

  return (
    <li className="manifest-memory-row" data-testid={`memory-${memory.id}`}>
      {editing ? (
        <form
          className="manifest-memory-edit"
          onSubmit={event => {
            event.preventDefault();
            void run(() => update({ variables: { memoryId: memory.id, text } }));
          }}
        >
          <input aria-label="Memory" value={text} maxLength={500} onChange={event => setText(event.target.value)} autoFocus />
          <button type="submit" disabled={saving || text.trim().length < 3}>
            Save
          </button>
          <button
            type="button"
            onClick={() => {
              setText(memory.text);
              setEditing(false);
            }}
          >
            Cancel
          </button>
        </form>
      ) : (
        <>
          <span className="manifest-memory-text">{memory.text}</span>
          <span className="manifest-memory-actions">
            <button type="button" onClick={() => setEditing(true)} aria-label={`Edit: ${memory.text}`}>
              Edit
            </button>
            <button
              type="button"
              disabled={forgetting}
              onClick={() => void run(() => forget({ variables: { memoryId: memory.id } }))}
              aria-label={`Forget: ${memory.text}`}
            >
              Forget
            </button>
          </span>
        </>
      )}
      {error ? (
        <p role="alert" className="manifest-memory-error">
          {error}
        </p>
      ) : null}
    </li>
  );
}

/**
 * Account → Data & storage → Memory (ADR 0021): what Manifest remembers from voice and from
 * agents, by idea, to edit or forget. The same notes are in the vault's Memory/ folder.
 */
export const MemorySection: React.FC = () => {
  const { data, loading, error, refetch } = useQuery(GET_MEMORIES, { fetchPolicy: 'cache-and-network' });
  const [filter, setFilter] = useState('');

  const groups = useMemo(() => {
    const words = filter.toLowerCase().split(/\s+/).filter(Boolean);
    const byIdea = new Map<string, MemoryItem[]>();
    for (const memory of data?.memories ?? []) {
      const haystack = `${memory.text} ${memory.ideaTitle ?? ''}`.toLowerCase();
      if (words.some(word => !haystack.includes(word))) continue;
      const key = memory.ideaTitle || GENERAL;
      byIdea.set(key, [...(byIdea.get(key) ?? []), memory]);
    }
    return [...byIdea.entries()].sort(([a], [b]) => (a === GENERAL ? -1 : b === GENERAL ? 1 : a.localeCompare(b)));
  }, [data, filter]);

  const total = data?.memories.length ?? 0;
  return (
    <section id="memory" className="manifest-panel settings-card" aria-labelledby="memory-title">
      <header className="settings-card-header">
        <div className="min-w-0">
          <h3 id="memory-title" className="settings-card-title">
            Memory
          </h3>
          <p className="settings-card-description">
            What Manifest remembers from your conversations, so voice and any agent you use (Claude Code, Codex and
            others) pick up where you left off. Only you can see it. It&apos;s also in your vault&apos;s Memory folder,
            and conversations are in Conversations.
          </p>
        </div>
      </header>
      <div className="settings-card-body">
        {total > 6 ? (
          <input
            className="manifest-memory-filter"
            type="search"
            placeholder="Search memories"
            aria-label="Search memories"
            value={filter}
            onChange={event => setFilter(event.target.value)}
          />
        ) : null}
        {loading && !data ? <p className="manifest-memory-empty">Loading…</p> : null}
        {error && !data ? <p className="manifest-memory-error">Memory didn&apos;t load. Try again in a moment.</p> : null}
        {data && total === 0 ? (
          <p className="manifest-memory-empty">
            Nothing yet. Talk to Manifest voice, or tell any agent with the Manifest plugin to remember something.
          </p>
        ) : null}
        {groups.map(([title, memories]) => (
          <div key={title} className="manifest-memory-group">
            <h4>{title}</h4>
            <ul>
              {memories.map(memory => (
                <MemoryRow key={memory.id} memory={memory} onChanged={() => void refetch()} />
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
};

export default MemorySection;
