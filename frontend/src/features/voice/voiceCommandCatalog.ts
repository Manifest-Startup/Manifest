export type VoiceCommandCategory = 'navigation' | 'ideas' | 'workspace' | 'search' | 'reels' | 'account';

export interface VoiceCommandDescriptor {
  id: string;
  category: VoiceCommandCategory;
  title: string;
  description: string;
  examples: string[];
}

export const VOICE_COMMAND_CATALOG: VoiceCommandDescriptor[] = [
  {
    id: 'navigate-ideas',
    category: 'navigation',
    title: 'Open the founder workspace',
    description: 'Move between the main app surfaces without reaching for the keyboard or pointer.',
    examples: ['Open ideas', 'Go to account', 'Open messages', 'Open pitch reels', 'Open API docs'],
  },
  {
    id: 'account-claim',
    category: 'account',
    title: 'Claim a full account (guest tryouts)',
    description: 'Open account access or email a one-time upgrade link to an address you say aloud.',
    examples: ['Claim my account', 'Send upgrade link to you at example dot com'],
  },
  {
    id: 'integrations-github',
    category: 'account',
    title: 'Integrations and GitHub bootstrap',
    description:
      'Open Account integrations to connect GitHub, or create a private repo from the current idea when GitHub is connected.',
    examples: ['Open integrations', 'Open GitHub integration', 'Bootstrap GitHub repo my-startup confirm bootstrap'],
  },
  {
    id: 'ideas-create-open',
    category: 'ideas',
    title: 'Create and open ideas',
    description: 'Start new ideas and jump straight into the part of the workspace you want.',
    examples: ['Create a new idea called Climate Ledger', 'Open the canvas', 'Open the patent'],
  },
  {
    id: 'ideas-manage',
    category: 'ideas',
    title: 'Manage the current idea',
    description: 'Rename, publish, unpublish, share, open history, or delete the current idea.',
    examples: ['Rename this idea to Startup OS', 'Publish this idea', 'Open share', 'Open history'],
  },
  {
    id: 'ideas-generate',
    category: 'ideas',
    title: 'Generate core documents',
    description: 'Kick off pitch deck, PRD, provisional patent, or background tasks from your idea note.',
    examples: ['Generate pitch deck', 'Generate PRD', 'Generate patent', 'Run background tasks'],
  },
  {
    id: 'workspace-layout',
    category: 'workspace',
    title: 'Tune the workspace layout',
    description: 'Control focus mode and side panels by voice when you want a cleaner workspace.',
    examples: ['Turn on focus mode', 'Collapse the library', 'Expand the context panel'],
  },
  {
    id: 'search',
    category: 'search',
    title: 'Search Manifest',
    description: 'Open universal search and seed it with a spoken query.',
    examples: ['Search for climate fintech', 'Open search', 'Find marketplace ideas'],
  },
  {
    id: 'reels',
    category: 'reels',
    title: 'Control pitch reels',
    description: 'Move through reels and perform the same social actions available on screen.',
    examples: [
      'Next reel',
      'Like this reel',
      'Repost this reel',
      'Follow this creator',
      'Open comments',
      'Open invest',
      'Comment on this reel This is sharp',
      'Open workspace for this reel',
    ],
  },
];

export const VOICE_COMMAND_INLINE_HINTS = [
  'Open account',
  'Create a new idea',
  'Generate pitch deck',
  'Open integrations',
  'Search for climate fintech',
  'Turn on focus mode',
  'Next reel',
] as const;

export const VOICE_COMMAND_HELP_SUMMARY =
  'You can navigate the app, create and manage ideas, generate documents, open integrations and GitHub bootstrap, control the workspace layout, search Manifest, and run pitch-reel actions by voice.';
