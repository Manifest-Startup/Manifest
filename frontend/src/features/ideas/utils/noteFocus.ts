/**
 * Keyboard flow between the ideas list and the note, and where you left off in each note.
 *
 * Apple Notes model: arrows move through the list (the note follows), Return goes into the
 * note, Esc comes back to the list. Each note remembers its cursor, selection and scroll
 * position on this device, so coming back puts you where you were.
 */

const FOCUS_NOTE = "manifest:focus-note";
const FOCUS_LIST = "manifest:focus-list";
const STORAGE_KEY = "manifest.noteCursor.v1";
const MAX_NOTES = 200;

/** Move keyboard focus into the open note (restoring the cursor). */
export const requestNoteFocus = () => window.dispatchEvent(new Event(FOCUS_NOTE));
/** Move keyboard focus back to the open idea in the list. */
export const requestListFocus = () => window.dispatchEvent(new Event(FOCUS_LIST));

export function onNoteFocusRequest(handler: () => void): () => void {
  window.addEventListener(FOCUS_NOTE, handler);
  return () => window.removeEventListener(FOCUS_NOTE, handler);
}

export function onListFocusRequest(handler: () => void): () => void {
  window.addEventListener(FOCUS_LIST, handler);
  return () => window.removeEventListener(FOCUS_LIST, handler);
}

export interface NoteCursor {
  anchor: number;
  head: number;
  scrollTop: number;
  at: number;
}

type Store = Record<string, NoteCursor>;

function readStore(): Store {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" ? (parsed as Store) : {};
  } catch {
    return {};
  }
}

export function readNoteCursor(noteKey: string): NoteCursor | null {
  const entry = readStore()[noteKey];
  return entry && Number.isFinite(entry.anchor) && Number.isFinite(entry.head) ? entry : null;
}

export function saveNoteCursor(noteKey: string, cursor: Omit<NoteCursor, "at">): void {
  try {
    const store = readStore();
    store[noteKey] = { ...cursor, at: Date.now() };
    // Keep the most recent notes only, so storage stays small.
    const keep = Object.entries(store)
      .sort((a, b) => b[1].at - a[1].at)
      .slice(0, MAX_NOTES);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(Object.fromEntries(keep)));
  } catch {
    // Private windows and blocked storage just don't remember.
  }
}

/** True when the platform's command key is ⌘ (macOS, iOS). */
export const isApple = () =>
  typeof navigator !== "undefined" && /Mac|iPhone|iPad|iPod/i.test(navigator.platform || navigator.userAgent);

/** The platform's primary modifier was held (⌘ on Apple, Ctrl elsewhere). */
export const hasMod = (event: KeyboardEvent | React.KeyboardEvent) =>
  isApple() ? event.metaKey && !event.ctrlKey : event.ctrlKey && !event.metaKey;

/** How a ⌥⌘<key> (Ctrl+Alt+<key>) shortcut reads on this platform, e.g. "⌥⌘D". */
export const shortcutLabel = (key: string) => (isApple() ? `⌥⌘${key}` : `Ctrl+Alt+${key}`);

/** The same shortcut for `aria-keyshortcuts`. */
export const ariaShortcut = (key: string) => (isApple() ? `Alt+Meta+${key}` : `Control+Alt+${key}`);

/** The event comes from somewhere the person is typing (inputs, the note, contenteditable). */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return Boolean(target.closest('input, textarea, select, [contenteditable="true"], .ProseMirror'));
}
