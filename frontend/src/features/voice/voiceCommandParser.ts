import type { VoiceCommandDescriptor } from './voiceCommandCatalog';
import { VOICE_COMMAND_CATALOG } from './voiceCommandCatalog';
import type { VoiceShortsAction, VoiceWorkspaceLayoutAction } from './voiceCommandEvents';

export type VoiceIdeaAspect =
  | 'description'
  | 'business-model-canvas'
  | 'cost-structure'
  | 'pitch-deck'
  | 'product-requirements-document'
  | 'patent';

export type VoiceRouteDestination =
  | 'ideas'
  | 'account'
  | 'shorts'
  | 'docs'
  | 'learn-more'
  | 'auth'
  | 'messages';

export type VoiceGenerateDocumentKind = 'pitch_deck' | 'prd' | 'patent' | 'background_tasks';

export type VoiceCommandIntent =
  | { kind: 'help' }
  | { kind: 'navigate'; destination: VoiceRouteDestination }
  | { kind: 'open_workspace' }
  | { kind: 'open_idea_aspect'; aspect: VoiceIdeaAspect }
  | { kind: 'create_idea'; title: string | null }
  | { kind: 'rename_idea'; title: string }
  | { kind: 'delete_idea' }
  | { kind: 'toggle_publish'; published: boolean }
  | { kind: 'search'; query: string | null }
  | { kind: 'workspace_layout'; action: VoiceWorkspaceLayoutAction }
  | { kind: 'open_modal'; target: 'share' | 'history' }
  | { kind: 'logout' }
  | { kind: 'shorts'; action: VoiceShortsAction; body?: string }
  | { kind: 'claim_account_navigate' }
  | { kind: 'request_upgrade_email'; email: string }
  | { kind: 'open_integrations'; focus?: 'github' }
  | { kind: 'generate_document'; document: VoiceGenerateDocumentKind }
  | { kind: 'github_bootstrap'; repoName: string };

const IDEA_ASPECT_ALIASES: Array<{ aspect: VoiceIdeaAspect; pattern: RegExp }> = [
  { aspect: 'description', pattern: /\b(note|notes|description|workspace note)\b/i },
  { aspect: 'business-model-canvas', pattern: /\b(business model canvas|canvas|bmc)\b/i },
  { aspect: 'cost-structure', pattern: /\b(cost structure|costs)\b/i },
  // Exclude bare "deck" so phrases like "generate pitch deck" match generate_document first.
  { aspect: 'pitch-deck', pattern: /\b(pitch deck|slides)\b/i },
  { aspect: 'product-requirements-document', pattern: /\b(product requirements document|requirements|prd)\b/i },
  { aspect: 'patent', pattern: /\b(patent|provisional patent)\b/i },
];

const NAVIGATION_ALIASES: Array<{ destination: VoiceRouteDestination; pattern: RegExp }> = [
  { destination: 'ideas', pattern: /\b(ideas|idea list|workspace|founder workspace)\b/i },
  { destination: 'account', pattern: /\b(account|profile|settings)\b/i },
  { destination: 'shorts', pattern: /\b(shorts|pitch reels|pitch shorts|discover)\b/i },
  { destination: 'docs', pattern: /\b(api docs|docs|documentation)\b/i },
  { destination: 'learn-more', pattern: /\b(learn more|about manifest)\b/i },
  { destination: 'auth', pattern: /\b(sign in|login|log in|auth)\b/i },
  { destination: 'messages', pattern: /\b(messages|inbox|direct messages|dms)\b/i },
];

const normalizeVoiceText = (value: string) =>
  value
    .toLowerCase()
    .replace(/[^\w\s'-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

const extractTrailingValue = (value: string, pattern: RegExp) => {
  const match = value.match(pattern);
  const extractedValue = match?.groups?.value?.trim();
  return extractedValue && extractedValue.length > 0 ? extractedValue : null;
};

const cleanCommandValue = (value: string | null) => {
  if (!value) {
    return null;
  }

  const cleaned = value.replace(/^["'\s]+|["'\s]+$/g, '').trim();
  return cleaned || null;
};

export const getVoiceCommandCatalog = (): VoiceCommandDescriptor[] => VOICE_COMMAND_CATALOG;

export const parseVoiceCommand = (spokenText: string): VoiceCommandIntent | null => {
  const normalized = normalizeVoiceText(spokenText);
  if (!normalized) {
    return null;
  }

  if (
    normalized === 'help' ||
    normalized === 'voice help' ||
    normalized === 'voice commands' ||
    normalized.includes('what can you do') ||
    normalized.includes('what commands can you') ||
    normalized.includes('show commands')
  ) {
    return { kind: 'help' };
  }

  if (/\b(log out|logout|sign out)\b/i.test(normalized)) {
    return { kind: 'logout' };
  }

  const upgradeEmailMatch = spokenText.match(
    /\b(?:send|email)\s+(?:me\s+)?(?:an\s+)?(?:upgrade|claim)\s+link\s+to\s+(\S+@\S+)/i,
  );
  if (upgradeEmailMatch?.[1]) {
    return { kind: 'request_upgrade_email', email: upgradeEmailMatch[1].replace(/[.,;]+$/, '').toLowerCase() };
  }

  if (
    /\b(claim my account|upgrade my account|create a full account|finish signup|sign up for real)\b/i.test(normalized)
  ) {
    return { kind: 'claim_account_navigate' };
  }

  const createIdeaTitle = cleanCommandValue(
    extractTrailingValue(spokenText, /(?:create|start|make)(?: me)?(?: a)?(?: new)? idea(?: called| named| titled)?\s+(?<value>.+)$/i),
  );
  if (/^(?:create|start|make)(?: me)?(?: a)?(?: new)? idea\b/i.test(spokenText)) {
    return { kind: 'create_idea', title: createIdeaTitle };
  }

  const renameIdeaTitle = cleanCommandValue(
    extractTrailingValue(spokenText, /(?:rename|retitle)(?: this| current)? idea(?: to)?\s+(?<value>.+)$/i),
  );
  if (renameIdeaTitle) {
    return { kind: 'rename_idea', title: renameIdeaTitle };
  }

  if (/\b(delete|remove)(?: this| current)? idea\b/i.test(normalized)) {
    return { kind: 'delete_idea' };
  }

  if (/\bunpublish(?: this| current)? idea\b/i.test(normalized)) {
    return { kind: 'toggle_publish', published: false };
  }

  if (/\bpublish(?: this| current)? idea\b/i.test(normalized)) {
    return { kind: 'toggle_publish', published: true };
  }

  if (/\b(open|show)(?: the)? share\b/i.test(normalized)) {
    return { kind: 'open_modal', target: 'share' };
  }

  if (/\b(open|show)(?: the)? (?:version history|history|versions)\b/i.test(normalized)) {
    return { kind: 'open_modal', target: 'history' };
  }

  const githubBootstrapRepo = cleanCommandValue(
    extractTrailingValue(
      spokenText,
      /(?:bootstrap|create)\s+(?:a\s+)?github\s+repo(?:sitory)?(?:\s+(?:named|called))?\s+(?<value>[\w.-]+)\s+confirm\s+bootstrap\s*$/i,
    ),
  );
  if (githubBootstrapRepo && /^[\w.-]+$/.test(githubBootstrapRepo)) {
    return { kind: 'github_bootstrap', repoName: githubBootstrapRepo };
  }

  if (
    /\b(open|show|go to)\b.*\bgithub\b.*\b(integration|connection|settings)\b/i.test(normalized) ||
    /\bconnect\b.*\bgithub\b/i.test(normalized)
  ) {
    return { kind: 'open_integrations', focus: 'github' };
  }

  if (
    /\b(open|show|go to)\b.*\bintegrations\b/i.test(normalized) ||
    normalized === 'open integrations' ||
    normalized === 'show integrations'
  ) {
    return { kind: 'open_integrations' };
  }

  if (
    /\b(generate|create|run|start|refresh)\b.*\bpitch deck\b/i.test(normalized) ||
    /\b(generate|create)\b.*\bdeck\b/i.test(normalized)
  ) {
    return { kind: 'generate_document', document: 'pitch_deck' };
  }

  if (
    /\b(generate|create|run|start|refresh)\b.*\b(product requirements document|prd|requirements doc)\b/i.test(
      normalized,
    )
  ) {
    return { kind: 'generate_document', document: 'prd' };
  }

  if (
    /\b(generate|create|run|start|refresh)\b.*\b(provisional patent|patent draft|patent)\b/i.test(normalized)
  ) {
    return { kind: 'generate_document', document: 'patent' };
  }

  if (
    /\b(run|start|refresh)\b.*\bbackground tasks\b/i.test(normalized) ||
    /\b(run|sync)\b.*\bbackground\b.*\b(generation|tasks)\b/i.test(normalized)
  ) {
    return { kind: 'generate_document', document: 'background_tasks' };
  }

  if (
    /\b(turn on|enable|enter)\b.*\bfocus mode\b/i.test(normalized) ||
    /\bfocus mode on\b/i.test(normalized)
  ) {
    return { kind: 'workspace_layout', action: 'enable_focus_mode' };
  }

  if (
    /\b(turn off|disable|exit)\b.*\bfocus mode\b/i.test(normalized) ||
    /\bfocus mode off\b/i.test(normalized)
  ) {
    return { kind: 'workspace_layout', action: 'disable_focus_mode' };
  }

  if (/\b(collapse|hide|close)\b.*\b(library|sidebar)\b/i.test(normalized)) {
    return { kind: 'workspace_layout', action: 'collapse_library' };
  }

  if (/\b(expand|show|open)\b.*\b(library|sidebar)\b/i.test(normalized)) {
    return { kind: 'workspace_layout', action: 'expand_library' };
  }

  if (/\b(collapse|hide|close)\b.*\b(context|details|owner panel)\b/i.test(normalized)) {
    return { kind: 'workspace_layout', action: 'collapse_context' };
  }

  if (/\b(expand|show|open)\b.*\b(context|details|owner panel)\b/i.test(normalized)) {
    return { kind: 'workspace_layout', action: 'expand_context' };
  }

  if (
    (!/\b(reel|clip)\b/i.test(normalized) &&
      /\b(open|show|go to)\b.*\b(current|this)?\s*workspace\b/i.test(normalized)) ||
    normalized === 'open workspace'
  ) {
    return { kind: 'open_workspace' };
  }

  if (/\b(next)\b.*\b(reel|clip)\b/i.test(normalized)) {
    return { kind: 'shorts', action: 'next' };
  }

  if (/\b(previous|back|last)\b.*\b(reel|clip)\b/i.test(normalized)) {
    return { kind: 'shorts', action: 'previous' };
  }

  if (/\b(like|unlike)\b.*\b(reel|clip)\b/i.test(normalized)) {
    return { kind: 'shorts', action: 'toggle_like' };
  }

  if (/\b(repost|reshare|unrepost)\b.*\b(reel|clip)\b/i.test(normalized)) {
    return { kind: 'shorts', action: 'toggle_reshare' };
  }

  if (/\b(follow|unfollow)\b.*\b(creator|founder|reel|clip)\b/i.test(normalized)) {
    return { kind: 'shorts', action: 'toggle_follow' };
  }

  if (/\b(open|show)\b.*\bcomments\b/i.test(normalized)) {
    return { kind: 'shorts', action: 'open_comments' };
  }

  if (/\b(open|show)\b.*\b(invest|investment)\b/i.test(normalized)) {
    return { kind: 'shorts', action: 'open_invest' };
  }

  if (/\b(close|hide)\b.*\bcomments\b/i.test(normalized)) {
    return { kind: 'shorts', action: 'close_comments' };
  }

  if (/\bshare\b.*\b(reel|clip)\b/i.test(normalized)) {
    return { kind: 'shorts', action: 'share' };
  }

  if (/\b(unmute|sound on)\b.*\b(reel|reels|shorts)?\b/i.test(normalized)) {
    return { kind: 'shorts', action: 'unmute' };
  }

  if (/\b(mute|sound off)\b.*\b(reel|reels|shorts)?\b/i.test(normalized)) {
    return { kind: 'shorts', action: 'mute' };
  }

  if (/\b(open|show)\b.*\bworkspace\b.*\b(reel|clip)\b/i.test(normalized)) {
    return { kind: 'shorts', action: 'open_workspace' };
  }

  const reelCommentBody = cleanCommandValue(
    extractTrailingValue(
      spokenText,
      /(?:comment on (?:this|current) (?:reel|clip)|add a comment to (?:this|current) (?:reel|clip))(?: that says| saying| with)?\s+(?<value>.+)$/i,
    ),
  );
  if (reelCommentBody) {
    return { kind: 'shorts', action: 'comment', body: reelCommentBody };
  }

  const openAspectCommand = /\b(open|show|go to)\b/i.test(normalized)
    ? IDEA_ASPECT_ALIASES.find(({ pattern }) => pattern.test(normalized))
    : null;
  if (openAspectCommand) {
    return { kind: 'open_idea_aspect', aspect: openAspectCommand.aspect };
  }

  if (normalized === 'open search' || normalized === 'search manifest' || normalized === 'search the app') {
    return { kind: 'search', query: null };
  }

  const searchQuery = cleanCommandValue(
    extractTrailingValue(spokenText, /(?:search(?: manifest| the app)?(?: for)?|look up|find)(?: for)?\s+(?<value>.+)$/i),
  );
  if (searchQuery) {
    return { kind: 'search', query: searchQuery };
  }

  if (/^(?:open|go to|navigate to|show)\b/i.test(normalized)) {
    const destination = NAVIGATION_ALIASES.find(({ pattern }) => pattern.test(normalized));
    if (destination) {
      return { kind: 'navigate', destination: destination.destination };
    }
  }

  return null;
};
