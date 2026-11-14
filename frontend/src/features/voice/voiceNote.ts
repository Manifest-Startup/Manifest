const VOICE_NOTE_START = '<!-- manifest-voice-note:start -->';
const VOICE_NOTE_END = '<!-- manifest-voice-note:end -->';

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export function mergeVoiceNoteSection(existingHtml: string | null | undefined, voiceNoteHtml: string): string {
  const current = (existingHtml || '').trim();
  if (!current) {
    return voiceNoteHtml;
  }

  if (current.includes(VOICE_NOTE_START) && current.includes(VOICE_NOTE_END)) {
    const pattern = new RegExp(
      `${escapeRegExp(VOICE_NOTE_START)}[\\s\\S]*?${escapeRegExp(VOICE_NOTE_END)}`,
      'm',
    );
    return current.replace(pattern, voiceNoteHtml);
  }

  return `${current}\n\n${voiceNoteHtml}`;
}

export function buildDraftIdeaTitle(suggestedTitle: string | null, transcript: string | null): string {
  const cleanedTitle = (suggestedTitle || '').trim();
  if (cleanedTitle) {
    return cleanedTitle;
  }

  const cleanedTranscript = (transcript || '').trim();
  if (!cleanedTranscript) {
    return 'Voice Idea';
  }

  const words = cleanedTranscript.match(/[A-Za-z0-9][A-Za-z0-9'-]*/g) || [];
  if (words.length === 0) {
    return 'Voice Idea';
  }

  return words
    .slice(0, 4)
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

/** When the voice API omits voice_note_html (e.g. error-shaped payloads), build a minimal marked block so GraphQL updates still persist. */
export function buildMinimalVoiceNoteHtml(response: {
  message: string;
  is_qualified: boolean;
  summary: string | null;
  suggested_title: string | null;
  transcript: string | null;
  qualification_confidence: number;
}): string | null {
  const title = (response.suggested_title || '').trim();
  const summary = (response.summary || '').trim();
  const transcript = (response.transcript || '').trim();
  const message = (response.message || '').trim();

  if (!title && !summary && !transcript && !message) {
    return null;
  }

  const pct = Math.round(Math.max(0, Math.min(1, response.qualification_confidence)) * 100);
  const status = response.is_qualified ? 'Qualified for first-pass docs' : 'Still qualifying';

  const blocks: string[] = [
    '<h2>Voice Strategy Session</h2>',
    `<p><strong>Status:</strong> ${escapeHtml(status)} (${pct}% confidence)</p>`,
  ];

  if (title) {
    blocks.push(`<p><strong>Working title:</strong> ${escapeHtml(title)}</p>`);
  }
  if (summary) {
    blocks.push(`<p>${escapeHtml(summary)}</p>`);
  }
  if (transcript) {
    blocks.push(`<p><strong>Your last turn:</strong> ${escapeHtml(transcript)}</p>`);
  }
  if (message && message !== summary && message !== transcript) {
    blocks.push(`<p><strong>Assistant:</strong> ${escapeHtml(message)}</p>`);
  }

  return `${VOICE_NOTE_START}<section data-manifest-voice-note="true">${blocks.join('')}</section>${VOICE_NOTE_END}`;
}
