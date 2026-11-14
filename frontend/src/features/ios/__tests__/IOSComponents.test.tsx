import React from 'react';
import { render, screen } from '@testing-library/react';
import IOSPageWrapper from '../components/IOSPageWrapper';
import IOSViewToggle from '../components/IOSViewToggle';

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

describe('IOSPageWrapper Component', () => {
  it('renders children', () => {
    render(
      <IOSPageWrapper>
        <div data-testid="test-child">Test</div>
      </IOSPageWrapper>
    );
    expect(screen.getByTestId('test-child')).toBeInTheDocument();
  });

  it('has ios-page-wrapper class', () => {
    const { container } = render(
      <IOSPageWrapper>
        <div>Content</div>
      </IOSPageWrapper>
    );
    expect(container.querySelector('.ios-page-wrapper')).toBeInTheDocument();
  });

  it('has ios-content class for child wrapper', () => {
    const { container } = render(
      <IOSPageWrapper>
        <div>Content</div>
      </IOSPageWrapper>
    );
    expect(container.querySelector('.ios-content')).toBeInTheDocument();
  });

  it('applies custom className', () => {
    const { container } = render(
      <IOSPageWrapper className="custom-class">
        <div>Content</div>
      </IOSPageWrapper>
    );
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper.className).toContain('custom-class');
  });

  it('supports dark mode styling', () => {
    const { container } = render(
      <IOSPageWrapper>
        <div>Content</div>
      </IOSPageWrapper>
    );
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper.className).toContain('dark:bg-neutral900');
  });

  it('applies transition-colors for smooth theme changes', () => {
    const { container } = render(
      <IOSPageWrapper>
        <div>Content</div>
      </IOSPageWrapper>
    );
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper.className).toContain('transition-colors');
  });
});

describe('IOSViewToggle Component', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('renders toggle button', () => {
    render(<IOSViewToggle />);
    const button = screen.getByRole('button');
    expect(button).toBeInTheDocument();
  });
});

describe('iOS Design System Compliance', () => {
  it('IOSPageWrapper uses iOS-standard background colors', () => {
    const { container } = render(
      <IOSPageWrapper>
        <div>Content</div>
      </IOSPageWrapper>
    );
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper.className).toContain('bg-gray-50');
  });

  it('IOSPageWrapper adds bottom padding for tab bar', () => {
    const { container } = render(
      <IOSPageWrapper showTabBar={true}>
        <div>Content</div>
      </IOSPageWrapper>
    );
    const content = container.querySelector('.ios-content');
    expect(content?.className).toContain('pb-20');
  });

  it('IOSPageWrapper removes bottom padding when showTabBar is false', () => {
    const { container } = render(
      <IOSPageWrapper showTabBar={false}>
        <div>Content</div>
      </IOSPageWrapper>
    );
    const content = container.querySelector('.ios-content');
    expect(content?.className).toContain('pb-4');
    expect(content?.className).not.toContain('pb-20');
  });
});
