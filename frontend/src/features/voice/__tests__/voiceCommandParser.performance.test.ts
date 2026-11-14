import { parseVoiceCommand } from '../voiceCommandParser';

describe('voiceCommandParser performance', () => {
  test('matches a large batch of commands quickly enough for live voice loops', () => {
    const commands = [
      'Open account',
      'Create a new idea called Climate Ledger',
      'Publish this idea',
      'Open the pitch deck',
      'Turn on focus mode',
      'Search for climate fintech',
      'Next reel',
      'Comment on this reel This is sharp',
    ];

    const iterations = 2500;
    const startedAt = performance.now();

    for (let index = 0; index < iterations; index += 1) {
      parseVoiceCommand(commands[index % commands.length]);
    }

    const durationMs = performance.now() - startedAt;

    expect(durationMs).toBeLessThan(900);
  });
});
