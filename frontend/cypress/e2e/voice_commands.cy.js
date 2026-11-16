describe('Voice Commands E2E Tests', () => {
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

  const login = () => {
    cy.signInWithOpenMedia('legacy-default', {
      onBeforeLoad: installVoiceStubs,
    });
  };

  beforeEach(() => {
    login();

    cy.intercept('POST', '**/api/voice-agent/start', {
      statusCode: 200,
      body: {
        conversation_id: 'voice-session-1',
        response: {
          message: 'Ready when you are. Start anywhere and I will keep the workspace moving.',
          is_qualified: false,
          summary: null,
          suggested_title: null,
          transcript: null,
          voice_note_html: null,
          covered_topics: [],
          missing_topics: ['problem', 'target_customer'],
          qualification_confidence: 0.1,
          context: {},
        },
        messages: [
          {
            role: 'assistant',
            content: JSON.stringify({
              message: 'Ready when you are. Start anywhere and I will keep the workspace moving.',
              is_qualified: false,
              summary: null,
              suggested_title: null,
              covered_topics: [],
              missing_topics: ['problem', 'target_customer'],
              qualification_confidence: 0.1,
            }),
          },
        ],
      },
    }).as('voiceStart');

    cy.intercept('POST', '**/api/voice-agent/tts', {
      statusCode: 200,
      body: {
        audio_base64: null,
        success: false,
        fallback_to_browser: true,
      },
    }).as('voiceTts');

    cy.intercept('POST', '**/api/voice-agent/process').as('voiceProcess');
  });

  it('routes a spoken app command without sending it to the idea strategist endpoint', () => {
    cy.get('button[aria-label*="voice"]').click();
    cy.wait('@voiceStart');
    cy.wait('@voiceTts');

    cy.window().then((win) => {
      const recognition = win.__lastRecognition;
      expect(recognition).to.exist;

      recognition.onresult({
        resultIndex: 0,
        results: [
          {
            0: { transcript: 'Open account' },
            isFinal: true,
            length: 1,
          },
        ],
      });
    });

    cy.contains(/opening account/i).should('be.visible');
    cy.url().should('include', '/account');
    cy.get('@voiceProcess.all').should('have.length', 0);
  });
});
