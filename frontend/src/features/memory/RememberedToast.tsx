import React, { useEffect, useState } from 'react';
import { useMutation } from '@apollo/client/react';

import type { MemoryItem } from '../core/apollo/operationTypes';
import { FORGET_MEMORY } from '../core/apollo/queries';
import { MEMORIES_SAVED_EVENT, type MemoriesSavedDetail } from '../voice/voiceMemory';

const SHOW_MS = 12_000;

/**
 * After a voice conversation: "Remembered 3 things", each with an undo (ADR 0021). Nothing
 * to save by hand; nothing shows when nothing new was remembered.
 */
const RememberedToast: React.FC = () => {
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [hover, setHover] = useState(false);
  const [forget] = useMutation(FORGET_MEMORY);

  useEffect(() => {
    const onSaved = (event: Event) => {
      const detail = (event as CustomEvent<MemoriesSavedDetail>).detail;
      if (detail?.memories?.length) setMemories(detail.memories);
    };
    window.addEventListener(MEMORIES_SAVED_EVENT, onSaved);
    return () => window.removeEventListener(MEMORIES_SAVED_EVENT, onSaved);
  }, []);

  useEffect(() => {
    if (!memories.length || hover) return undefined;
    const timer = window.setTimeout(() => setMemories([]), SHOW_MS);
    return () => window.clearTimeout(timer);
  }, [memories, hover]);

  if (!memories.length) return null;
  const undo = (id: string) => {
    setMemories(current => current.filter(m => m.id !== id));
    void forget({ variables: { memoryId: id } }).catch(() => undefined);
  };
  const count = memories.length === 1 ? '1 thing' : `${memories.length} things`;
  return (
    <aside
      className="manifest-remembered"
      role="status"
      aria-live="polite"
      data-testid="remembered-toast"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <header className="manifest-remembered-header">
        <strong>Remembered {count}</strong>
        <button type="button" className="manifest-remembered-close" aria-label="Close" onClick={() => setMemories([])}>
          ×
        </button>
      </header>
      <ul>
        {memories.map(memory => (
          <li key={memory.id}>
            <span>{memory.text}</span>
            <button type="button" onClick={() => undo(memory.id)} aria-label={`Forget: ${memory.text}`}>
              Undo
            </button>
          </li>
        ))}
      </ul>
      <a className="manifest-remembered-link" href="/account#memory">
        See everything Manifest remembers
      </a>
    </aside>
  );
};

export default RememberedToast;
