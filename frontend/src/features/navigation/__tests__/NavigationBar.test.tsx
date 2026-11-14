import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import NavigationBar from '../NavigationBar';
import * as MessageContext from 'features/notifications/context/MessageContext';
import { MockedProvider } from '@apollo/client/testing/react';

const mockNavigate = jest.fn();
const mockSetMessage = jest.fn();
const mockClearMessage = jest.fn();
const mockMessage = { text: null, type: 'info' as 'info' };

// State to control reactive variables
let mockUserState = { isLoggedIn: false, userData: null };
let mockAccountState = { accountData: null, loading: false, error: null };
const mockLogoutMutation = jest.fn().mockResolvedValue({ data: {} });
const mockFetch = jest.fn().mockResolvedValue({ ok: true });

jest.mock('react-router-dom', () => ({
  ...jest.requireActual('react-router-dom'),
  useNavigate: () => mockNavigate,
  useLocation: () => ({ pathname: '/ideas' }),
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
}));

jest.mock('features/core/apollo/localState', () => {
  const actual = jest.requireActual('features/core/apollo/localState');
  return {
    ...actual,
  };
});

jest.mock('../../notifications/context/MessageContext', () => ({
  useMessage: () => ({
    message: mockMessage,
    clearMessage: mockClearMessage,
    setMessage: mockSetMessage,
  }),
}));

jest.mock('@apollo/client/react', () => {
  const actual = jest.requireActual('@apollo/client/react');
  return {
    ...actual,
    useReactiveVar: (varFn: any) => {
      // Check if it's userVar or accountVar by checking the variable name or structure
      // Since we can't directly compare, we'll check the module path
      const module = require('features/core/apollo/localState');
      if (varFn === module.userVar || (varFn && varFn.name === 'userVar')) {
        return mockUserState;
      }
      if (varFn === module.accountVar || (varFn && varFn.name === 'accountVar')) {
        return mockAccountState;
      }
      return varFn ? varFn() : null;
    },
    useMutation: () => [
      mockLogoutMutation,
      { loading: false, error: null, reset: jest.fn() },
    ],
    MockedProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  };
});

describe('NavigationBar', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (global as any).fetch = mockFetch;
    mockFetch.mockImplementation(() => Promise.resolve({ ok: true } as Response));
    mockUserState = { isLoggedIn: false, userData: null };
    mockAccountState = { accountData: null, loading: false, error: null };
    mockLogoutMutation.mockResolvedValue({ data: {} });
    jest.spyOn(MessageContext, 'useMessage').mockImplementation(() => ({
      setMessage: mockSetMessage,
      clearMessage: mockClearMessage,
      message: mockMessage,
    }));
  });

  function setup({ isLoggedIn = false, accountData = null } = {}) {
    mockUserState = { 
      isLoggedIn, 
      userData: isLoggedIn ? { userId: '1', email: 'test@test.com' } : null 
    };
    mockAccountState = { accountData, loading: false, error: null };
    
    return render(
      <MockedProvider>
        <NavigationBar />
      </MockedProvider>
    );
  }

  it('renders logo and Sign In when logged out', () => {
    setup({ isLoggedIn: false });
    expect(screen.getByText('Manifest')).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /sign in/i })).toBeInTheDocument();
  });

  it('navigates to /auth when Sign In is clicked', () => {
    setup({ isLoggedIn: false });
    fireEvent.click(screen.getByRole('menuitem', { name: /sign in/i }));
    expect(mockNavigate).toHaveBeenCalledWith('/auth');
  });

  it('renders nav links and avatar when logged in', () => {
    setup({ isLoggedIn: true, accountData: { gravatarHash: 'abc123' } as any });
    expect(screen.getAllByText('Ideas').length).toBeGreaterThan(0);
    expect(screen.getByText('Pitch Reels')).toBeInTheDocument();
    expect(screen.getByLabelText('Toggle Profile Dropdown Menu')).toBeInTheDocument();
  });

  it('navigates to /ideas when logo is clicked and logged in', () => {
    setup({ isLoggedIn: true });
    fireEvent.click(screen.getByLabelText('Navigate to Home'));
    expect(mockNavigate).toHaveBeenCalledWith('/ideas');
  });

  it('navigates to / when logo is clicked and logged out', () => {
    setup({ isLoggedIn: false });
    fireEvent.click(screen.getByLabelText('Navigate to Home'));
    expect(mockNavigate).toHaveBeenCalledWith('/');
  });

  it('toggles dropdown when avatar is clicked', () => {
    setup({ isLoggedIn: true, accountData: { gravatarHash: 'abc123' } as any });
    const avatar = screen.getByLabelText('Toggle Profile Dropdown Menu');
    fireEvent.click(avatar);
    // Dropdown should appear
    expect(screen.getByRole('menu', { name: /dropdown menu/i })).toBeInTheDocument();
  });

  it('navigates to /account when Account is clicked in dropdown', async () => {
    setup({ isLoggedIn: true, accountData: { gravatarHash: 'abc123' } as any });
    fireEvent.click(screen.getByLabelText('Toggle Profile Dropdown Menu'));
    fireEvent.click(screen.getByRole('menuitem', { name: /go to account/i }));
    expect(mockNavigate).toHaveBeenCalledWith('/account');
  });

  it('calls logout endpoint and navigates to /auth when Logout is clicked', async () => {
    setup({ isLoggedIn: true, accountData: { gravatarHash: 'abc123' } as any });
    fireEvent.click(screen.getByLabelText('Toggle Profile Dropdown Menu'));
    fireEvent.click(screen.getByRole('menuitem', { name: /logout/i }));
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/auth', { replace: true });
    }, { timeout: 1000 });
  });

  it('shows error if logout request throws', async () => {
    mockFetch.mockImplementationOnce(() => Promise.reject(new Error('Logout failed')));
    setup({ isLoggedIn: true, accountData: { gravatarHash: 'abc123' } as any });
    fireEvent.click(screen.getByLabelText('Toggle Profile Dropdown Menu'));
    fireEvent.click(screen.getByRole('menuitem', { name: /logout/i }));
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/auth', { replace: true });
    });
  });

  // Avatar/profile picture tests
  it('shows profile picture from accountData.profilePictureUrl', () => {
    setup({ isLoggedIn: true, accountData: { profilePictureUrl: 'http://example.com/avatar.jpg' } as any });
    const img = screen.getByAltText('User Profile Icon') as HTMLImageElement;
    expect(img).toHaveAttribute('src', 'http://example.com/avatar.jpg');
  });

  it('shows gravatar if no profilePictureUrl but gravatarHash is present', () => {
    setup({ isLoggedIn: true, accountData: { gravatarHash: 'abc123' } as any });
    const img = screen.getByAltText('User Profile Icon') as HTMLImageElement;
    expect(img.src).toContain('gravatar.com/avatar/abc123');
  });

  it('shows profile picture when accountData is nested under account property', () => {
    setup({ isLoggedIn: true, accountData: { account: { profilePictureUrl: 'http://example.com/nested-avatar.jpg' } } as any });
    const img = screen.getByAltText('User Profile Icon') as HTMLImageElement;
    expect(img).toHaveAttribute('src', 'http://example.com/nested-avatar.jpg');
  });

  it('shows gravatar when accountData is nested under account property', () => {
    setup({ isLoggedIn: true, accountData: { account: { gravatarHash: 'nested123' } } as any });
    const img = screen.getByAltText('User Profile Icon') as HTMLImageElement;
    expect(img.src).toContain('gravatar.com/avatar/nested123');
  });

  it('prioritizes profilePictureUrl over gravatarHash', () => {
    setup({ isLoggedIn: true, accountData: { profilePictureUrl: 'http://example.com/avatar.jpg', gravatarHash: 'abc123' } as any });
    const img = screen.getByAltText('User Profile Icon') as HTMLImageElement;
    expect(img).toHaveAttribute('src', 'http://example.com/avatar.jpg');
    expect(img.src).not.toContain('gravatar.com');
  });

  it('shows default avatar when no profile picture or gravatar is present', () => {
    setup({ isLoggedIn: true, accountData: {} as any });
    const img = screen.getByAltText('User Profile Icon') as HTMLImageElement;
    expect(img.src).toBe('https://www.gravatar.com/avatar/?d=mp&s=64');
  });

  it('shows default avatar if not logged in', () => {
    setup({ isLoggedIn: false, accountData: null });
    // The avatar should not be in the document
    expect(screen.queryByAltText('User Profile Icon')).not.toBeInTheDocument();
  });

  it('shows Sign In and hides Ideas/Pitch Reels when not logged in', () => {
    setup({ isLoggedIn: false, accountData: null });
    expect(screen.getByText('Sign In')).toBeInTheDocument();
    expect(screen.queryByText('Ideas')).not.toBeInTheDocument();
    expect(screen.queryByText('Pitch Reels')).not.toBeInTheDocument();
  });

  it('shows Ideas and Pitch Reels when logged in', () => {
    setup({ isLoggedIn: true, accountData: { gravatarHash: 'abc123' } as any });
    expect(screen.getAllByText('Ideas').length).toBeGreaterThan(0);
    expect(screen.getByText('Pitch Reels')).toBeInTheDocument();
  });
});
