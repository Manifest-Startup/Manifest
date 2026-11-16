import { parseVoiceCommand } from '../voiceCommandParser';

describe('voiceCommandParser', () => {
  test('parses idea creation commands with titles', () => {
    expect(parseVoiceCommand('Create a new idea called Climate Ledger')).toEqual({
      kind: 'create_idea',
      title: 'Climate Ledger',
    });
  });

  test('parses idea management commands', () => {
    expect(parseVoiceCommand('Rename this idea to Startup OS')).toEqual({
      kind: 'rename_idea',
      title: 'Startup OS',
    });

    expect(parseVoiceCommand('Publish this idea')).toEqual({
      kind: 'toggle_publish',
      published: true,
    });
  });

  test('parses workspace and search commands', () => {
    expect(parseVoiceCommand('Turn on focus mode')).toEqual({
      kind: 'workspace_layout',
      action: 'enable_focus_mode',
    });

    expect(parseVoiceCommand('Search for climate fintech')).toEqual({
      kind: 'search',
      query: 'climate fintech',
    });
  });

  test('parses idea aspect navigation', () => {
    expect(parseVoiceCommand('Open the pitch deck')).toEqual({
      kind: 'open_idea_aspect',
      aspect: 'pitch-deck',
    });
  });

  test('parses pitch reel actions', () => {
    expect(parseVoiceCommand('Next reel')).toEqual({
      kind: 'shorts',
      action: 'next',
    });

    expect(parseVoiceCommand('Comment on this reel This is sharp')).toEqual({
      kind: 'shorts',
      action: 'comment',
      body: 'This is sharp',
    });

    expect(parseVoiceCommand('Open invest')).toEqual({
      kind: 'shorts',
      action: 'open_invest',
    });
  });

  test('parses help commands', () => {
    expect(parseVoiceCommand('What can you do')).toEqual({
      kind: 'help',
    });
  });

  test('parses guest account claim', () => {
    expect(parseVoiceCommand('Claim my account')).toEqual({ kind: 'claim_account_navigate' });
    expect(parseVoiceCommand('Finish signup')).toEqual({ kind: 'claim_account_navigate' });
  });

  test('parses messages navigation', () => {
    expect(parseVoiceCommand('Open messages')).toEqual({ kind: 'navigate', destination: 'messages' });
  });

  test('parses document generation and integrations commands', () => {
    expect(parseVoiceCommand('Generate pitch deck')).toEqual({
      kind: 'generate_document',
      document: 'pitch_deck',
    });
    expect(parseVoiceCommand('Generate PRD')).toEqual({ kind: 'generate_document', document: 'prd' });
    expect(parseVoiceCommand('Generate patent')).toEqual({ kind: 'generate_document', document: 'patent' });
    expect(parseVoiceCommand('Run background tasks')).toEqual({
      kind: 'generate_document',
      document: 'background_tasks',
    });
    expect(parseVoiceCommand('Open integrations')).toEqual({ kind: 'open_integrations' });
    expect(parseVoiceCommand('Open GitHub integration')).toEqual({ kind: 'open_integrations', focus: 'github' });
    expect(parseVoiceCommand('Bootstrap GitHub repo my-app confirm bootstrap')).toEqual({
      kind: 'github_bootstrap',
      repoName: 'my-app',
    });
  });
});
