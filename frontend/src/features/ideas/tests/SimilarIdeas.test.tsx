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

  it('renders structured competitor and research cards with simpler labels', () => {
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

    expect(screen.getAllByText('Similar').length).toBeGreaterThan(0);
    expect(screen.getByText('Similar Ideas')).toBeInTheDocument();
    expect(screen.getByText('Figma')).toBeInTheDocument();
    expect(screen.getByText(/Collaborative product design platform/i)).toBeInTheDocument();
    expect(screen.getAllByText('Research').length).toBeGreaterThan(0);
    expect(screen.getByText(/Collaboration workflow lock-in/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Gartner' })).toHaveAttribute('href', 'https://www.gartner.com/');
  });

  it('keeps exact research citations linkable without inventing fallback search links', () => {
    render(
      <SimilarIdeas
        similarIdeas={`# Similar Landscape
## Research Watchlist
### [Regulatory Environment for Water Quality](https://www.epa.gov/waterdata)
- Suggested Sources: [Environmental Protection Agency (EPA)](https://www.epa.gov/waterdata), [Google search](https://www.google.com/search?q=water+quality), International Water Association`}
      />,
    );

    const topicLink = screen.getByRole('link', { name: 'Regulatory Environment for Water Quality' });
    const epaLink = screen.getByRole('link', { name: 'Environmental Protection Agency (EPA)' });

    expect(screen.queryByText('[Regulatory Environment for Water Quality]')).not.toBeInTheDocument();
    expect(topicLink).toHaveAttribute('href', 'https://www.epa.gov/waterdata');
    expect(epaLink).toHaveAttribute('href', 'https://www.epa.gov/waterdata');
    expect(screen.queryByRole('link', { name: 'Google search' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'International Water Association' })).not.toBeInTheDocument();
  });

  it('uses compact skeleton cards that stay within the narrow rail while loading', () => {
    mockUseReactiveVar.mockReturnValue({
      ideaId: 'idea-1',
      loading: true,
      error: null,
      data: '',
      byIdeaId: {},
    });

    render(<SimilarIdeas compact ideaId="idea-1" similarIdeas="" />);

    screen.getAllByTestId('similar-ideas-skeleton-card').forEach((card) => {
      expect(card).toHaveClass('w-full', 'overflow-hidden', 'manifest-related-card');
    });
  });

  it('keeps competitor content inside a scrollable panel for narrow layouts', () => {
    render(
      <SimilarIdeas
        compact
        similarIdeas={`# Similar Landscape
## Comparable Companies
### Very Long Competitor Name For Overflow Coverage
- URL: https://avery-long-domain-name-for-competitor-research.example.com/path
- Summary: Collaborative product design platform with an unusually long domain to stress the pill layout.
- Why Similar: Covers nearby workflow needs.
- Distinguishing Signal: Broad distribution.`}
      />,
    );

    const competitorCard = screen.getByText('Very Long Competitor Name For Overflow Coverage').closest('article') as HTMLElement;

    expect(screen.getByTestId('similar-ideas')).toHaveClass('manifest-similar-panel', 'flex', 'min-h-0', 'flex-col');
    expect(screen.getByTestId('similar-ideas-body')).toHaveClass('overflow-y-auto', 'overflow-x-hidden');
    expect(screen.getByText('avery-long-domain-name-for-competitor-research.example.com')).toHaveClass('max-w-full', 'truncate');
    expect(competitorCard).toHaveClass('manifest-related-card');
  });

  it('renders a supplied header action next to the similar ideas title', () => {
    render(
      <SimilarIdeas
        compact
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
