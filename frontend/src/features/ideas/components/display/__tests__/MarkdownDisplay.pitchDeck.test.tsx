import React from 'react';
import { render, screen } from '@testing-library/react';

import { MarkdownDisplay } from '../MarkdownDisplay';

jest.mock('../../../utils/exportPitchDeckPptx', () => ({
  exportPitchDeckPptx: jest.fn().mockResolvedValue(undefined),
}));

const SAMPLE_DECK = `# Slide 1: Company Purpose
We help retailers retain customers with blockchain-backed loyalty rewards.
- Headline takeaway
- Wedge segment

# Slide 2: Problem
Retailers lose repeat buyers because loyalty programs are fragmented.
- Points expire across brands
- Redemption feels opaque

# Slide 3: Solution
A shared ledger lets shoppers earn once and redeem anywhere in the network.
- Unified wallet
- Real-time settlement`;

describe('MarkdownDisplay pitch deck', () => {
  it('renders all slide sections in a single-column layout without side panels', () => {
    render(
      <MarkdownDisplay
        content={SAMPLE_DECK}
        fallbackMessage="Fallback"
        title="Blockchain Loyalty Rewards Program"
        variant="pitch-deck"
      />,
    );

    expect(screen.getByText('Blockchain Loyalty Rewards Program')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Download PowerPoint/i })).toBeInTheDocument();
    expect(screen.getByText('Slide 1')).toBeInTheDocument();
    expect(screen.getByText('Slide 2')).toBeInTheDocument();
    expect(screen.getByText('Slide 3')).toBeInTheDocument();
    expect(screen.getByText('Company Purpose')).toBeInTheDocument();
    expect(screen.getByText('Problem')).toBeInTheDocument();
    expect(screen.queryByText(/Slide Highlights/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Deck section/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Signal 1/i)).not.toBeInTheDocument();
  });

  it('shows slide 1 body on its own card instead of only in the header summary', () => {
    render(
      <MarkdownDisplay
        content={SAMPLE_DECK}
        fallbackMessage="Fallback"
        title="Blockchain Loyalty Rewards Program"
        variant="pitch-deck"
      />,
    );

    expect(screen.getAllByText(/blockchain-backed loyalty rewards/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Unified wallet')).toBeInTheDocument();
  });
});
