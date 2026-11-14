import React from 'react';
import { render, screen } from '@testing-library/react';

import { BusinessModelCanvasDisplay } from '../BusinessModelCanvasDisplay';
import { CostStructureDisplay } from '../CostStructureDisplay';
import { MarkdownDisplay } from '../MarkdownDisplay';

jest.mock('features/notifications/context/MessageContext', () => ({
  useMessage: () => ({
    setMessage: jest.fn(),
  }),
}));

const generationState = {
  startedAt: Date.now(),
  pendingDocuments: ['pitch-deck', 'product-requirements-document'],
  mode: 'initial' as const,
};

describe('document generation loading states', () => {
  it('shows a full generation placeholder for empty markdown documents', () => {
    render(
      <MarkdownDisplay
        content=""
        fallbackMessage="Fallback"
        generationState={generationState}
        title="Pitch Deck"
        variant="pitch-deck"
      />
    );

    expect(screen.getByText('Generating Pitch Deck')).toBeInTheDocument();
    expect(screen.getByText(/You can keep editing/i)).toBeInTheDocument();
  });

  it('shows an inline refresh banner above existing generated content', () => {
    render(
      <MarkdownDisplay
        content={'# Product Requirements Document\n## Goals\n- Improve clarity'}
        fallbackMessage="Fallback"
        generationState={{ ...generationState, mode: 'refresh' }}
        title="Product Requirements Document"
        variant="prd"
      />
    );

    expect(screen.getByText(/Updating product requirements document/i)).toBeInTheDocument();
    expect(screen.getAllByText('Product Requirements Document').length).toBeGreaterThan(0);
  });

  it('shows a professional loading canvas instead of a blank fallback', () => {
    render(
      <BusinessModelCanvasDisplay
        content=""
        fallbackMessage="Fallback"
        generationState={{
          startedAt: Date.now(),
          pendingDocuments: ['business-model-canvas'],
          mode: 'initial',
        }}
      />
    );

    expect(screen.getByText('Generating Business Model Canvas')).toBeInTheDocument();
    expect(screen.getByText(/Canvas Build/i)).toBeInTheDocument();
  });

  it('shows the same generation experience for cost structure when the canvas is still building', () => {
    render(
      <CostStructureDisplay
        cost=""
        generationState={{
          startedAt: Date.now(),
          pendingDocuments: ['business-model-canvas'],
          mode: 'initial',
        }}
      />
    );

    expect(screen.getByText('Generating Cost Structure')).toBeInTheDocument();
    expect(screen.getByText(/Cost Model/i)).toBeInTheDocument();
  });
});
