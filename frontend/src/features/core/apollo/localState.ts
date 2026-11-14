import { makeVar } from '@apollo/client';

/* --------------------------------------------------------------------------
 * Apollo local (client-only) reactive variables
 * We keep them in one place so components can import and call
 *   const user = useReactiveVar(userVar);
 * This replaces Redux slices while we are migrating away from Redux.
 * ------------------------------------------------------------------------ */

// ------------------------- User / Auth -----------------------------------
export interface UserVar {
  isLoggedIn: boolean;
  /** True once the app has completed its initial profile check for this session. */
  authChecked?: boolean;
  /** Try-before-signup server guest; also synced from `profile.isGuest` after refresh. */
  isGuest?: boolean;
  userData?: {
    userId?: string;
    email?: string;
  } | null;
}

export const userVar = makeVar<UserVar>({ isLoggedIn: false, authChecked: false, isGuest: false, userData: null });

// ------------------------- Account ---------------------------------------
export interface AccountVar {
  accountData: Record<string, any> | null;
  loading: boolean;
  error?: string | null;
}

export const accountVar = makeVar<AccountVar>({ accountData: null, loading: false, error: null });

// ---------------------- Editor / Sidebar ---------------------------------
export interface SidebarVar {
  currentIdeaId: string | null;
  currentIdeaAspect: string;
  allIdeaIds: string[];
}

export const sidebarVar = makeVar<SidebarVar>({
  currentIdeaId: null,
  currentIdeaAspect: 'description',
  allIdeaIds: [],
});

export type EditorStatus = 'idle' | 'typing' | 'saving';
export const editorStatusVar = makeVar<EditorStatus>('idle');

// ---------------------- Similar Ideas ------------------------------------
export interface SimilarIdeasEntry {
  loading: boolean;
  error: string | null;
  data: string;
  updatedAt?: number;
}

export interface SimilarIdeasVar {
  ideaId: string | null;
  loading: boolean;
  error: string | null;
  data: string; // markdown string
  byIdeaId: Record<string, SimilarIdeasEntry>;
}

export const createSimilarIdeasEntry = (overrides: Partial<SimilarIdeasEntry> = {}): SimilarIdeasEntry => ({
  loading: false,
  error: null,
  data: '',
  ...overrides,
});

export const getSimilarIdeasEntry = (
  state: SimilarIdeasVar,
  ideaId: string | null | undefined,
): SimilarIdeasEntry | null => {
  if (!ideaId) {
    return null;
  }

  return state.byIdeaId?.[ideaId] || null;
};

export const similarIdeasVar = makeVar<SimilarIdeasVar>({
  ideaId: null,
  loading: false,
  error: null,
  data: '',
  byIdeaId: {},
});

// ---------------------- Voice launcher -----------------------------------
/** Increment to ask the floating voice shell to open and start a session (e.g. from PitchPage). */
export const voiceOpenRequestVar = makeVar(0);
