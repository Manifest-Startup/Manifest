import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ApiAccessSection from '../ApiAccessSection';

global.fetch = jest.fn();

const mockFetch = global.fetch as jest.MockedFunction<typeof global.fetch>;

describe('ApiAccessSection', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    localStorage.setItem('access_token', 'test-token');
  });

  afterEach(() => {
    localStorage.clear();
  });

  describe('Loading State', () => {
    it('shows loading skeleton initially', () => {
      mockFetch.mockImplementation(() => new Promise(() => {}));
      
      const { container } = render(<ApiAccessSection />);
      
      expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
    });
  });

  describe('Empty State', () => {
    it('shows empty state when no API keys exist', async () => {
      mockFetch.mockImplementation((url) => {
        if (url === '/api/keys/clients') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ clients: [] })
          } as Response);
        }
        if (url === '/api/keys/usage') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ usage: { tier: 'free', requests_used: 0, requests_limit: 1000, tokens_used: 0, rate_limit_per_minute: 10 } })
          } as Response);
        }
        if (url === '/api/keys/tiers') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ tiers: [] })
          } as Response);
        }
        return Promise.reject(new Error('Unknown URL'));
      });

      render(<ApiAccessSection />);

      await waitFor(() => {
        expect(screen.getByText(/No API keys yet/i)).toBeInTheDocument();
      });
    });
  });

  describe('API Access UI', () => {
    it('displays API Access heading', async () => {
      mockFetch.mockImplementation((url) => {
        if (url === '/api/keys/clients') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ clients: [] })
          } as Response);
        }
        if (url === '/api/keys/usage') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ usage: { tier: 'free', requests_used: 50, requests_limit: 1000, tokens_used: 0, rate_limit_per_minute: 10 } })
          } as Response);
        }
        if (url === '/api/keys/tiers') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ tiers: [] })
          } as Response);
        }
        return Promise.reject(new Error('Unknown URL'));
      });

      render(<ApiAccessSection />);

      await waitFor(() => {
        expect(screen.getByText('API Access')).toBeInTheDocument();
      });
    });

    it('displays View API Docs link', async () => {
      mockFetch.mockImplementation((url) => {
        if (url === '/api/keys/clients') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ clients: [] })
          } as Response);
        }
        if (url === '/api/keys/usage') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ usage: { tier: 'free', requests_used: 0, requests_limit: 1000, tokens_used: 0, rate_limit_per_minute: 10 } })
          } as Response);
        }
        if (url === '/api/keys/tiers') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ tiers: [] })
          } as Response);
        }
        return Promise.reject(new Error('Unknown URL'));
      });

      render(<ApiAccessSection />);

      await waitFor(() => {
        expect(screen.getByText('View API Docs')).toBeInTheDocument();
      });
    });

    it('shows Create Key button', async () => {
      mockFetch.mockImplementation((url) => {
        if (url === '/api/keys/clients') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ clients: [] })
          } as Response);
        }
        if (url === '/api/keys/usage') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ usage: { tier: 'free', requests_used: 0, requests_limit: 1000, tokens_used: 0, rate_limit_per_minute: 10 } })
          } as Response);
        }
        if (url === '/api/keys/tiers') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ tiers: [] })
          } as Response);
        }
        return Promise.reject(new Error('Unknown URL'));
      });

      render(<ApiAccessSection />);

      await waitFor(() => {
        expect(screen.getByText('Create Key')).toBeInTheDocument();
      });
    });
  });

  describe('Usage Display', () => {
    it('shows monthly usage progress', async () => {
      mockFetch.mockImplementation((url) => {
        if (url === '/api/keys/clients') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ clients: [] })
          } as Response);
        }
        if (url === '/api/keys/usage') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ 
              usage: { 
                tier: 'free', 
                requests_used: 500, 
                requests_limit: 1000, 
                tokens_used: 0, 
                rate_limit_per_minute: 10 
              } 
            })
          } as Response);
        }
        if (url === '/api/keys/tiers') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ tiers: [] })
          } as Response);
        }
        return Promise.reject(new Error('Unknown URL'));
      });

      render(<ApiAccessSection />);

      await waitFor(() => {
        expect(screen.getByText('Monthly Usage')).toBeInTheDocument();
        expect(screen.getByText(/500/)).toBeInTheDocument();
      });
    });
  });

  describe('Create Key Modal', () => {
    it('opens modal when Create Key is clicked', async () => {
      mockFetch.mockImplementation((url) => {
        if (url === '/api/keys/clients') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ clients: [] })
          } as Response);
        }
        if (url === '/api/keys/usage') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ usage: { tier: 'free', requests_used: 0, requests_limit: 1000, tokens_used: 0, rate_limit_per_minute: 10 } })
          } as Response);
        }
        if (url === '/api/keys/tiers') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ tiers: [] })
          } as Response);
        }
        return Promise.reject(new Error('Unknown URL'));
      });

      render(<ApiAccessSection />);

      await waitFor(() => {
        expect(screen.getByText('Create Key')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Create Key'));

      await waitFor(() => {
        expect(screen.getByText('Create API Key')).toBeInTheDocument();
        expect(screen.getByText('Key Name')).toBeInTheDocument();
      });
    });
  });

  describe('Recent sign-in', () => {
    it('asks for a fresh Open Media sign-in when the backend requires step-up', async () => {
      mockFetch.mockImplementation((url, init) => {
        if (url === '/api/keys/clients' && (!init || init.method !== 'POST')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ clients: [{ id: 'c1', name: 'Default', tier: 'free', status: 'active', keys: [] }] })
          } as Response);
        }
        if (url === '/api/keys/usage') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ usage: { tier: 'free', requests_used: 0, requests_limit: 1000, tokens_used: 0, rate_limit_per_minute: 10 } })
          } as Response);
        }
        if (url === '/api/keys/tiers') {
          return Promise.resolve({ ok: true, json: () => Promise.resolve({ tiers: [] }) } as Response);
        }
        if (url === '/api/keys/keys') {
          return Promise.resolve({
            ok: false,
            status: 401,
            headers: new Headers({ 'X-Step-Up-Required': '1' }),
            json: () => Promise.resolve({ detail: 'Re-authentication required' })
          } as Response);
        }
        return Promise.reject(new Error('Unknown URL'));
      });

      render(<ApiAccessSection />);
      await waitFor(() => expect(screen.getByText('Create Key')).toBeInTheDocument());
      fireEvent.click(screen.getByText('Create Key'));
      fireEvent.change(await screen.findByPlaceholderText('e.g., Production Key'), { target: { value: 'CI' } });
      fireEvent.click(screen.getAllByRole('button', { name: /create/i }).pop() as HTMLElement);

      const link = await screen.findByTestId('api-keys-sign-in-again');
      expect(link).toHaveAttribute('href', '/api/auth/open-media/start?next=%2Faccount');
      expect(screen.queryByText('Failed to create API key')).not.toBeInTheDocument();
    });
  });

  describe('Billing Tiers', () => {
    it('displays billing tier options', async () => {
      mockFetch.mockImplementation((url) => {
        if (url === '/api/keys/clients') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ clients: [] })
          } as Response);
        }
        if (url === '/api/keys/usage') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ usage: { tier: 'free', requests_used: 0, requests_limit: 1000, tokens_used: 0, rate_limit_per_minute: 10 } })
          } as Response);
        }
        if (url === '/api/keys/tiers') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ 
              tiers: [
                { id: 'free', name: 'Free', price: 0, requests_per_month: 1000, rate_limit_per_minute: 10, features: [] },
                { id: 'starter', name: 'Starter', price: 29, requests_per_month: 10000, rate_limit_per_minute: 60, features: [] },
                { id: 'pro', name: 'Pro', price: 99, requests_per_month: 100000, rate_limit_per_minute: 300, features: [] },
                { id: 'enterprise', name: 'Enterprise', price: -1, requests_per_month: -1, rate_limit_per_minute: 1000, features: [] }
              ] 
            })
          } as Response);
        }
        return Promise.reject(new Error('Unknown URL'));
      });

      render(<ApiAccessSection />);

      await waitFor(() => {
        expect(screen.getAllByText('Free').length).toBeGreaterThan(0);
        expect(screen.getByText('Starter')).toBeInTheDocument();
        expect(screen.getByText('Pro')).toBeInTheDocument();
        expect(screen.getByText('Enterprise')).toBeInTheDocument();
      });
    });
  });
});
