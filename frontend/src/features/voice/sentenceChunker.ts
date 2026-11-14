const NON_TERMINAL_ABBREVIATIONS = new Set([
  'dr',
  'mr',
  'mrs',
  'ms',
  'prof',
  'sr',
  'jr',
  'st',
  'vs',
  'etc',
  'e.g',
  'i.e',
  'u.s',
  'u.k',
]);

export interface SpeechChunkResult {
  chunks: string[];
  remainder: string;
}

function isDecimalPoint(text: string, index: number): boolean {
  return /\d/.test(text[index - 1] || '') && /\d/.test(text[index + 1] || '');
}

function isLikelyAbbreviation(text: string, index: number): boolean {
  if (text[index] !== '.') {
    return false;
  }

  const prefix = text.slice(Math.max(0, index - 12), index).trim();
  const token = prefix.split(/\s+/).pop()?.replace(/[^a-zA-Z.]/g, '').toLowerCase() || '';
  return NON_TERMINAL_ABBREVIATIONS.has(token);
}

function isSentenceBoundaryFollow(text: string, index: number): boolean {
  for (let cursor = index + 1; cursor < text.length; cursor += 1) {
    const value = text[cursor];
    if (/\s/.test(value)) {
      return true;
    }
    if (/["')\]}]/.test(value)) {
      continue;
    }
    return false;
  }
  return true;
}

function normalizeChunk(text: string): string {
  return text.replace(/\s+/g, ' ').trim();
}

function bestSplitInWindow(text: string, start: number, maxEnd: number): number {
  let lastClauseInWindow = -1;
  for (let i = start; i <= maxEnd; i += 1) {
    const char = text[i];
    const isClauseBoundary =
      char === ',' ||
      char === ';' ||
      char === ':' ||
      char === '—' ||
      (char === '-' && text[i + 1] === '-');
    if (isClauseBoundary) {
      lastClauseInWindow = i;
    }
  }
  if (lastClauseInWindow >= start) {
    return lastClauseInWindow;
  }
  for (let i = maxEnd; i >= start; i -= 1) {
    if (/\s/.test(text[i])) {
      return i;
    }
  }
  return -1;
}

/** Larger windows → fewer TTS round trips and smoother perceived speech (see speechPlaybackMerge). */
export const DEFAULT_VOICE_CHUNK_MAX = 280;

/**
 * @param firstChunkMaxLength When set, the FIRST chunk emitted in this call is
 *   capped to this (smaller) length. This shrinks the time-to-first-audio: the
 *   opening clause is synthesized and starts playing fast, while the rest of the
 *   reply uses the larger `maxChunkLength` window so playback stays smooth.
 */
export function extractSpeakableChunks(
  buffer: string,
  options: { maxChunkLength?: number; firstChunkMaxLength?: number } = {},
): SpeechChunkResult {
  const maxChunkLength = options.maxChunkLength ?? DEFAULT_VOICE_CHUNK_MAX;
  const firstChunkMaxLength = options.firstChunkMaxLength;
  const chunks: string[] = [];
  let cursor = 0;
  let lastSafeBreak = -1;

  for (let index = 0; index < buffer.length; index += 1) {
    const char = buffer[index];
    // The first emitted chunk may use a tighter cap for fast first audio.
    const activeMax =
      chunks.length === 0 && firstChunkMaxLength
        ? Math.min(maxChunkLength, firstChunkMaxLength)
        : maxChunkLength;

    const isClauseBoundary =
      char === ',' ||
      char === ';' ||
      char === ':' ||
      char === '—' ||
      (char === '-' && buffer[index + 1] === '-');

    if (isClauseBoundary || /\s/.test(char)) {
      lastSafeBreak = index;
    }

    const isSentenceEnd = char === '!' || char === '?' || char === '.' || char === '\n';
    if (isSentenceEnd) {
      if (char === '.' && (isDecimalPoint(buffer, index) || isLikelyAbbreviation(buffer, index))) {
        continue;
      }

      if (!isSentenceBoundaryFollow(buffer, index)) {
        continue;
      }

      // Long single sentence: split at the best safe break inside the first activeMax window,
      // then re-process from there (same terminal punctuation).
      if (index - cursor + 1 > activeMax) {
        const maxEnd = Math.min(index - 1, cursor + activeMax - 1);
        const splitAt = bestSplitInWindow(buffer, cursor, maxEnd);
        if (splitAt >= cursor) {
          const splitChunk = normalizeChunk(buffer.slice(cursor, splitAt + 1));
          if (splitChunk) {
            chunks.push(splitChunk);
          }
          cursor = splitAt + 1;
          lastSafeBreak = -1;
          index = cursor - 1;
          continue;
        }
      }

      const chunk = normalizeChunk(buffer.slice(cursor, index + 1));
      if (chunk) {
        chunks.push(chunk);
      }
      cursor = index + 1;
      lastSafeBreak = -1;
      continue;
    }

    if (index - cursor + 1 >= activeMax && lastSafeBreak >= cursor) {
      const chunk = normalizeChunk(buffer.slice(cursor, lastSafeBreak + 1));
      if (chunk) {
        chunks.push(chunk);
      }
      cursor = lastSafeBreak + 1;
      lastSafeBreak = -1;
    }
  }

  return {
    chunks,
    remainder: normalizeChunk(buffer.slice(cursor)),
  };
}
