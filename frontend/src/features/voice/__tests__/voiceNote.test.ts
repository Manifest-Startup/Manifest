import { buildMinimalVoiceNoteHtml, mergeVoiceNoteSection } from '../voiceNote';

describe('buildMinimalVoiceNoteHtml', () => {
  test('returns null when nothing to persist', () => {
    expect(
      buildMinimalVoiceNoteHtml({
        message: '',
        is_qualified: false,
        summary: null,
        suggested_title: null,
        transcript: null,
        qualification_confidence: 0,
      }),
    ).toBeNull();
  });

  test('wraps summary and transcript with manifest markers', () => {
    const html = buildMinimalVoiceNoteHtml({
      message: 'Thanks for sharing.',
      is_qualified: false,
      summary: 'B2B tool for landlords.',
      suggested_title: 'Lease Ops',
      transcript: 'We help automate renewals.',
      qualification_confidence: 0.4,
    });
    expect(html).toContain('<!-- manifest-voice-note:start -->');
    expect(html).toContain('<!-- manifest-voice-note:end -->');
    expect(html).toContain('Lease Ops');
    expect(html).toContain('B2B tool for landlords.');
    expect(html).toContain('We help automate renewals.');
    expect(html).not.toContain('<script');
  });

  test('escapes HTML in user-visible strings', () => {
    const html = buildMinimalVoiceNoteHtml({
      message: 'Ok.',
      is_qualified: false,
      summary: '<img src=x onerror=alert(1)>',
      suggested_title: null,
      transcript: null,
      qualification_confidence: 0,
    });
    expect(html).toContain('&lt;img');
    expect(html).not.toContain('<img src=x');
  });
});

describe('mergeVoiceNoteSection with minimal block', () => {
  test('replaces existing voice note region', () => {
    const existing =
      '<p>Intro</p>\n<!-- manifest-voice-note:start --><section>old</section><!-- manifest-voice-note:end -->';
    const minimal =
      buildMinimalVoiceNoteHtml({
        message: 'Hi',
        is_qualified: false,
        summary: 'New summary',
        suggested_title: 'T',
        transcript: null,
        qualification_confidence: 0.2,
      }) || '';
    const merged = mergeVoiceNoteSection(existing, minimal);
    expect(merged).toContain('New summary');
    expect(merged).not.toContain('old');
    expect(merged).toContain('<p>Intro</p>');
  });
});
