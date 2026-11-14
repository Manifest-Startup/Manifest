import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import IOSTabBar from '../components/IOSTabBar';
import IOSNavigationBar from '../components/IOSNavigationBar';
import IOSPageWrapper from '../components/IOSPageWrapper';

const mockSetMessage = jest.fn();
const mockNavigate = jest.fn();

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: jest.fn().mockImplementation((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: jest.fn(),
    removeListener: jest.fn(),
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
  })),
});

jest.mock('react-router-dom', () => ({
  ...jest.requireActual('react-router-dom'),
  useNavigate: () => mockNavigate,
  useLocation: () => ({ pathname: '/ideas' }),
}));

jest.mock('features/notifications/context/MessageContext', () => ({
  useMessage: () => ({
    setMessage: mockSetMessage,
    clearMessage: jest.fn(),
    message: { text: null, type: 'info' as const },
  }),
}));

jest.mock('@apollo/client/react', () => ({
  ...jest.requireActual('@apollo/client/react'),
  useReactiveVar: () => ({
    isLoggedIn: true,
    userData: { id: 'user-1' },
    accountData: { email: 'test@example.com' },
    loading: false,
    error: null,
  }),
  useMutation: () => [jest.fn(), { loading: false }],
  useQuery: () => ({
    data: { unreadMessageCount: { count: 0 } },
    loading: false,
    error: undefined,
  }),
}));

const renderWithRouter = (component: React.ReactElement) => {
  return render(
    <BrowserRouter>
      {component}
    </BrowserRouter>
  );
};

describe('iOS Feature Parity Tests', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('IOSPageWrapper', () => {
    it('renders children correctly', () => {
      render(
        <IOSPageWrapper>
          <div data-testid="child">Test Content</div>
        </IOSPageWrapper>
      );
      expect(screen.getByTestId('child')).toBeInTheDocument();
    });

    it('applies correct CSS classes for dark mode support', () => {
      const { container } = render(
        <IOSPageWrapper>
          <div>Content</div>
        </IOSPageWrapper>
      );
      const wrapper = container.firstChild as HTMLElement;
      expect(wrapper.className).toContain('bg-gray-50');
      expect(wrapper.className).toContain('dark:bg-neutral900');
      expect(wrapper.className).toContain('transition-colors');
    });

    it('applies tab bar padding by default', () => {
      const { container } = render(
        <IOSPageWrapper>
          <div>Content</div>
        </IOSPageWrapper>
      );
      const content = container.querySelector('.ios-content');
      expect(content?.className).toContain('pb-20');
    });
  });

  describe('IOSTabBar - Feature Parity with Web Navigation', () => {
    it('renders Ideas, Pitch Reels, and Account tabs', () => {
      renderWithRouter(<IOSTabBar />);
      expect(screen.getByText('Ideas')).toBeInTheDocument();
      expect(screen.getByText('Pitch Reels')).toBeInTheDocument();
      expect(screen.getByText('Account')).toBeInTheDocument();
    });

    it('has three navigation tabs', () => {
      renderWithRouter(<IOSTabBar />);
      const buttons = screen.getAllByRole('button');
      expect(buttons).toHaveLength(3);
    });

    it('navigates when tab is clicked', () => {
      renderWithRouter(<IOSTabBar />);
      fireEvent.click(screen.getByText('Pitch Reels'));
      expect(mockNavigate).toHaveBeenCalled();
    });

    it('applies dark mode styles correctly', () => {
      const { container } = renderWithRouter(<IOSTabBar />);
      const tabBar = container.querySelector('.ios-tab-bar');
      expect(tabBar?.className).toContain('dark:bg-neutral800/95');
      expect(tabBar?.className).toContain('dark:border-neutral700/50');
    });

    it('shows active indicator for current tab', () => {
      renderWithRouter(<IOSTabBar />);
      const ideasTab = screen.getByText('Ideas').closest('button');
      expect(ideasTab?.className).toContain('text-accent-600');
    });
  });

  describe('IOSNavigationBar', () => {
    it('renders the Manifest logo', () => {
      renderWithRouter(<IOSNavigationBar />);
      expect(screen.getByText('Manifest')).toBeInTheDocument();
    });

    it('applies dark mode styles', () => {
      const { container } = renderWithRouter(<IOSNavigationBar />);
      const navBar = container.querySelector('.ios-nav-bar');
      expect(navBar?.className).toContain('dark:bg-neutral800/95');
    });
  });

  describe('Feature Parity Completeness', () => {
    it('iOS tab bar has 3 tabs (Ideas, Pitch Reels, Account)', () => {
      renderWithRouter(<IOSTabBar />);
      expect(screen.getByText('Ideas')).toBeInTheDocument();
      expect(screen.getByText('Pitch Reels')).toBeInTheDocument();
      expect(screen.getByText('Account')).toBeInTheDocument();
    });

    it('each tab has an icon', () => {
      const { container } = renderWithRouter(<IOSTabBar />);
      const svgIcons = container.querySelectorAll('svg');
      expect(svgIcons.length).toBeGreaterThanOrEqual(3);
    });
  });
});

describe('iOS Dark Mode Parity Tests', () => {
  it('IOSPageWrapper supports dark mode classes', () => {
    const { container } = render(
      <IOSPageWrapper>
        <div>Content</div>
      </IOSPageWrapper>
    );
    expect(container.innerHTML).toContain('dark:bg-neutral900');
  });

  it('IOSTabBar has dark mode background', () => {
    const { container } = renderWithRouter(<IOSTabBar />);
    const tabBar = container.querySelector('.ios-tab-bar');
    expect(tabBar?.className).toContain('dark:bg-neutral800/95');
  });

  it('IOSNavigationBar has dark mode background', () => {
    const { container } = renderWithRouter(<IOSNavigationBar />);
    const navBar = container.querySelector('.ios-nav-bar');
    expect(navBar?.className).toContain('dark:bg-neutral800/95');
  });
});

describe('iOS Responsive Design Tests', () => {
  it('IOSPageWrapper uses min-h-screen for full height', () => {
    const { container } = render(
      <IOSPageWrapper>
        <div>Content</div>
      </IOSPageWrapper>
    );
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper.className).toContain('min-h-screen');
  });

  it('IOSTabBar has max-w-screen-sm for mobile-first design', () => {
    const { container } = renderWithRouter(<IOSTabBar />);
    expect(container.innerHTML).toContain('max-w-screen-sm');
  });
});
