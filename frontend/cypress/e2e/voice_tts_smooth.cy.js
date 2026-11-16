/**
 * Client-side chunking/coalescing (see speechPlaybackMerge + sentenceChunker) is covered by Jest.
 * This smoke test ensures a long assistant greeting still opens the voice UI and completes initial TTS handoff.
 */
describe('Voice long greeting smoke', () => {
  const installVoiceStubs = (win) => {
    class FakeSpeechRecognition {
      constructor() {
        win.__lastRecognition = this;
        this.continuous = false;
        this.interimResults = true;
        this.lang = 'en-US';
        this.maxAlternatives = 1;
      }

      abort() {
        if (this.onend) {
          this.onend(new Event('end'));
        }
      }

      start() {
        if (this.onstart) {
          this.onstart(new Event('start'));
        }
      }

      stop() {
        if (this.onend) {
          this.onend(new Event('end'));
        }
      }
    }

    win.SpeechRecognition = FakeSpeechRecognition;
    win.webkitSpeechRecognition = FakeSpeechRecognition;

    win.navigator.mediaDevices = {
      getUserMedia: () =>
        Promise.resolve({
          getTracks: () => [{ stop: () => undefined }],
        }),
    };

    win.speechSynthesis = {
      cancel: () => undefined,
      getVoices: () => [],
      speak: (utterance) => {
        setTimeout(() => {
          if (utterance.onend) {
            utterance.onend(new Event('end'));
          }
        }, 0);
      },
    };
  };

  it('opens voice modal and receives TTS for a long spoken greeting', () => {
    cy.signInWithOpenMedia('legacy-default', {
      onBeforeLoad: installVoiceStubs,
    });

    const longGreeting = 'Welcome. We will take this one step at a time. '.repeat(14);

    cy.intercept('POST', '**/api/voice-agent/start', {
      statusCode: 200,
      body: {
        conversation_id: 'voice-session-long-greeting',
        response: {
          message: longGreeting,
          is_qualified: false,
          summary: null,
          suggested_title: null,
          transcript: null,
          voice_note_html: null,
          covered_topics: [],
          missing_topics: ['problem', 'target_customer'],
          qualification_confidence: 0.05,
          context: {},
        },
        messages: [
          {
            role: 'assistant',
            content: JSON.stringify({
              message: longGreeting,
              is_qualified: false,
              summary: null,
              suggested_title: null,
              covered_topics: [],
              missing_topics: ['problem', 'target_customer'],
              qualification_confidence: 0.05,
            }),
          },
        ],
      },
    }).as('voiceStartLong');

    cy.intercept('POST', '**/api/voice-agent/tts', {
      statusCode: 200,
      body: {
        audio_base64: null,
        success: false,
        fallback_to_browser: true,
      },
    }).as('voiceTts');

    cy.visit('/ideas');
    cy.get('button[aria-label*="voice"]', { timeout: 15000 }).click();
    cy.wait('@voiceStartLong');
    cy.wait('@voiceTts');
    cy.contains('Manifest Voice').should('be.visible');
  });
});
