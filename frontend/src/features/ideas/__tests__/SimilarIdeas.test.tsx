import React from 'react';
import { render, screen } from '@testing-library/react';
import SimilarIdeas from '../components/SimilarIdeas';

const mockUseReactiveVar = jest.fn();

jest.mock('@apollo/client/react', () => {
  const actual = jest.requireActual('@apollo/client/react');
  return {
    ...actual,
    useReactiveVar: (...args: any[]) => mockUseReactiveVar(...args),
  };
});

jest.mock('react-markdown', () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => <div data-testid="mock-markdown">{children}</div>,
}));

jest.mock('remark-gfm', () => () => {});

describe('SimilarIdeas', () => {
  beforeEach(() => {
    mockUseReactiveVar.mockReturnValue({
      ideaId: 'idea-1',
      loading: false,
      error: null,
      data: '',
      byIdeaId: {},
    });
  });

  it('shows each competitor and research topic as one linked line', () => {
    render(
      <SimilarIdeas
        similarIdeas={`# Similar Landscape
## Comparable Companies
### Figma
- URL: https://www.figma.com/
- Summary: Collaborative product design platform.
- Why Similar: Teams use it as a shared workspace for structured product work.
- Distinguishing Signal: Strong multiplayer collaboration and workflow depth.

## Research Watchlist
### Collaboration workflow lock-in
- Suggested Sources: [Gartner](https://www.gartner.com/), https://www.cbinsights.com/
- Why It Matters: Retention improves when the workflow becomes a team system.
- What To Validate: Which artifact becomes the durable system of record.`}
      />,
    );

    expect(screen.getByRole('heading', { name: 'Similar ideas' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Competitors/ })).toHaveTextContent('Competitors 1');
    expect(screen.getByRole('heading', { name: /Research/ })).toHaveTextContent('Research 1');

    const figma = screen.getByRole('link', { name: /Figma/ });
    expect(figma).toHaveAttribute('href', 'https://www.figma.com/');
    expect(figma).toHaveTextContent('Collaborative product design platform.');
    // Longer reasoning moves to the tooltip instead of the panel.
    expect(screen.queryByText(/Strong multiplayer collaboration/)).not.toBeInTheDocument();
    expect(figma.getAttribute('title')).toContain('Strong multiplayer collaboration');

    const research = screen.getByRole('link', { name: /Collaboration workflow lock-in/ });
    expect(research).toHaveAttribute('href', 'https://www.gartner.com/');
    expect(research).toHaveTextContent('Retention improves when the workflow becomes a team system.');
  });

  it('links research rows to exact citations, never to search pages', () => {
    render(
      <SimilarIdeas
        similarIdeas={`# Similar Landscape
## Research Watchlist
### [Regulatory Environment for Water Quality](https://www.epa.gov/waterdata)
- Suggested Sources: [Environmental Protection Agency (EPA)](https://www.epa.gov/waterdata), [Google search](https://www.google.com/search?q=water+quality), International Water Association`}
      />,
    );

    const topicLink = screen.getByRole('link', { name: /Regulatory Environment for Water Quality/ });
    expect(screen.queryByText('[Regulatory Environment for Water Quality]')).not.toBeInTheDocument();
    expect(topicLink).toHaveAttribute('href', 'https://www.epa.gov/waterdata');
    expect(screen.getAllByRole('link')).toHaveLength(1);
    expect(document.querySelector('a[href*="google.com"]')).toBeNull();
  });

  it('shows skeleton rows while loading', () => {
    mockUseReactiveVar.mockReturnValue({
      ideaId: 'idea-1',
      loading: true,
      error: null,
      data: '',
      byIdeaId: {},
    });

    render(<SimilarIdeas ideaId="idea-1" similarIdeas="" />);

    expect(screen.getAllByTestId('similar-ideas-skeleton-card')).toHaveLength(4);
  });

  it('keeps long names and domains inside the scrollable rail', () => {
    render(
      <SimilarIdeas
        similarIdeas={`# Similar Landscape
## Comparable Companies
### Very Long Competitor Name For Overflow Coverage
- URL: https://avery-long-domain-name-for-competitor-research.example.com/path
- Summary: Collaborative product design platform with an unusually long domain to stress the layout.
- Why Similar: Covers nearby workflow needs.
- Distinguishing Signal: Broad distribution.`}
      />,
    );

    expect(screen.getByTestId('similar-ideas')).toHaveClass('manifest-similar-panel', 'flex', 'min-h-0', 'flex-col');
    expect(screen.getByTestId('similar-ideas-body')).toHaveClass('overflow-y-auto', 'overflow-x-hidden');
    expect(screen.getByText('avery-long-domain-name-for-competitor-research.example.com')).toHaveClass('max-w-full', 'truncate');
    expect(screen.getByText('Very Long Competitor Name For Overflow Coverage')).toHaveClass('truncate');
  });

  it('renders a supplied header action next to the similar ideas title', () => {
    render(
      <SimilarIdeas
        headerAction={<button type="button">Collapse similar ideas</button>}
        similarIdeas=""
      />,
    );

    expect(screen.getByRole('button', { name: 'Collapse similar ideas' })).toBeInTheDocument();
  });

  it('shows a professional empty state when no similar ideas are found', () => {
    render(<SimilarIdeas similarIdeas="" />);
    expect(screen.getByText('No similar ideas yet')).toBeInTheDocument();
  });
});
