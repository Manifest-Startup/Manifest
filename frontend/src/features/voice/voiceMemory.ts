/**
 * Voice remembers (ADR 0021): what was said is kept as a conversation note in the vault, and
 * lasting facts as memory notes any agent can read.
 *
 * - `recallForVoice` fetches what Manifest remembers for the idea in view, for the agent.
 * - `ConversationRecorder` keeps every caption of one conversation (the panel only shows
 *   the latest few).
 * - `finishConversation` runs after the panel closes: the local agent's last pass for
 *   memories, then the transcript is saved and `MEMORIES_SAVED_EVENT` tells the app what was
 *   remembered, so it can show "Remembered 3 things" with an undo for each.
 */
import type { ApolloClient } from '@apollo/client';

import type { ConversationTurn, MemoryItem } from '../core/apollo/operationTypes';
import { RECALL, SAVE_VOICE_CONVERSATION } from '../core/apollo/queries';
import { createLogger } from '../core/logError';
import type { LiveCaption } from './liveVoice';
import { wrapUpBridge, type BridgeMemory } from './localAgent';

const log = createLogger('voiceMemory');

export const MEMORIES_SAVED_EVENT = 'manifest:memories-saved';
const RECALL_LIMIT = 12;

export interface MemoriesSavedDetail {
  path: string | null;
  memories: MemoryItem[];
}

export async function recallForVoice(apollo: ApolloClient, ideaId: string | null | undefined): Promise<BridgeMemory[]> {
  try {
    const { data } = await apollo.query({
      query: RECALL,
      variables: { ideaId: ideaId ?? null, limit: RECALL_LIMIT },
      fetchPolicy: 'network-only',
    });
    return (data?.recall ?? []).map(m => ({ id: m.id, text: m.text }));
  } catch (error) {
    log.warn('recall failed', error);
    return []; // voice works without memory
  }
}

/** Every caption of one conversation, by id, latest text wins. */
export class ConversationRecorder {
  private readonly captions = new Map<number, LiveCaption>();
  private readonly order: number[] = [];
  startedAt: string | null = null;
  ideaId: string | null = null;

  record(captions: LiveCaption[], ideaId?: string | null): void {
    for (const caption of captions) {
      if (!this.captions.has(caption.id)) this.order.push(caption.id);
      this.captions.set(caption.id, caption);
    }
    if (captions.length && !this.startedAt) this.startedAt = new Date().toISOString();
    if (ideaId) this.ideaId = ideaId;
  }

  turns(): ConversationTurn[] {
    return this.order
      .map(id => this.captions.get(id))
      .filter((c): c is LiveCaption => Boolean(c && c.text.trim()))
      .map(c => ({ role: c.role, text: c.text.trim() }));
  }

  get heardSomeone(): boolean {
    return this.turns().some(t => t.role === 'user');
  }
}

export interface FinishOptions {
  apollo: ApolloClient;
  recorder: ConversationRecorder;
  /** The person's own agent through `manifest bridge`: give it a last pass for memories. */
  localAgent?: string | null;
  wrapUp?: typeof wrapUpBridge;
}

export async function finishConversation({ apollo, recorder, localAgent, wrapUp = wrapUpBridge }: FinishOptions): Promise<MemoriesSavedDetail | null> {
  if (!recorder.heardSomeone) return null;
  if (localAgent) await wrapUp();
  try {
    const { data } = await apollo.mutate({
      mutation: SAVE_VOICE_CONVERSATION,
      variables: {
        turns: recorder.turns(),
        ideaId: recorder.ideaId,
        startedAt: recorder.startedAt,
        agent: localAgent ?? 'Manifest voice',
        // The local agent remembered as it went; the hosted voice already has the person's key.
        extract: !localAgent,
      },
    });
    const saved = data?.saveVoiceConversation;
    if (!saved) return null;
    const detail: MemoriesSavedDetail = { path: saved.path, memories: saved.memories };
    window.dispatchEvent(new CustomEvent<MemoriesSavedDetail>(MEMORIES_SAVED_EVENT, { detail }));
    return detail;
  } catch (error) {
    log.warn('saving the conversation failed', error);
    return null;
  }
}
