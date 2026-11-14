require('@testing-library/jest-dom');
global.setImmediate = global.setImmediate || ((fn, ...args) => setTimeout(fn, 0, ...args));
require('whatwg-fetch');

// Polyfill for TextEncoder and TextDecoder
const { TextEncoder, TextDecoder } = require('util');
global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

// Polyfill for BroadcastChannel
class BroadcastChannel {
  constructor(name) {
    this.name = name;
    this.listeners = {};
  }
  addEventListener(name, listener) {
    this.listeners[name] = this.listeners[name] || [];
    this.listeners[name].push(listener);
  }
  removeEventListener(name, listener) {
    if (this.listeners[name]) {
      this.listeners[name] = this.listeners[name].filter(l => l !== listener);
    }
  }
  postMessage(message) {
    if (this.listeners.message) {
      this.listeners.message.forEach(listener => listener({ data: message }));
    }
  }
  close() {
    this.listeners = {};
  }
}
global.BroadcastChannel = BroadcastChannel;

// Apollo Client 4: React hooks live in @apollo/client/react.
jest.mock('@apollo/client/react', () => {
  const actual = jest.requireActual('@apollo/client/react');
  return {
    ...actual,
    useMutation: () => [jest.fn(), { loading: false, error: null }],
  };
});

// Basic stub for 'msw' and 'msw/node' to satisfy imports in integration tests.
jest.mock('msw', () => ({
  http: {},
  HttpResponse: {
    json: jest.fn(),
  },
}), { virtual: true });

jest.mock('msw/node', () => ({
  setupServer: () => ({
    listen: jest.fn(),
    resetHandlers: jest.fn(),
    close: jest.fn(),
  }),
}), { virtual: true });
