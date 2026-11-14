import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MockedProvider } from '@apollo/client/testing/react';
import UpvoteButton from '../UpvoteButton';
import { TOGGLE_UPVOTE } from 'features/core/apollo/queries';

const mockOnVoteChange = jest.fn();

const toggleUpvoteMockAdd = {
  request: {
    query: TOGGLE_UPVOTE,
    variables: { ideaId: 'idea-123' }
  },
  result: {
    data: {
      toggleUpvote: {
        __typename: 'VoteResult',
        voted: true,
        ideaId: 'idea-123',
        voteCount: 43
      }
    }
  }
};

const toggleUpvoteMockRemove = {
  request: {
    query: TOGGLE_UPVOTE,
    variables: { ideaId: 'idea-123' }
  },
  result: {
    data: {
      toggleUpvote: {
        __typename: 'VoteResult',
        voted: false,
        ideaId: 'idea-123',
        voteCount: 41
      }
    }
  }
};

const renderButton = (initialVoted = false, initialCount = 42, mocks = [toggleUpvoteMockAdd]) => {
  return render(
    <MockedProvider mocks={mocks} addTypename={false}>
      <UpvoteButton
        ideaId="idea-123"
        initialVoted={initialVoted}
        initialCount={initialCount}
        onVoteChange={mockOnVoteChange}
      />
    </MockedProvider>
  );
};

describe('UpvoteButton', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders with initial count', () => {
    renderButton(false, 42);
    expect(screen.getByText('42')).toBeInTheDocument();
  });

  it('shows unfilled heart when not voted', () => {
    renderButton(false);
    const button = screen.getByRole('button');
    expect(button).toHaveClass('bg-gray-100', 'text-gray-500');
  });

  it('shows filled heart when voted', () => {
    renderButton(true);
    const button = screen.getByRole('button');
    expect(button).toHaveClass('bg-red-100', 'text-red-500');
  });

  it('calls mutation on click', async () => {
    renderButton(false, 42);
    
    const button = screen.getByRole('button');
    fireEvent.click(button);
    
    await waitFor(() => {
      expect(button).not.toBeDisabled();
    });
  });

  it('displays initial count correctly', () => {
    renderButton(false, 42);
    expect(screen.getByText('42')).toBeInTheDocument();
  });

  it('hides count when showCount is false', () => {
    render(
      <MockedProvider mocks={[toggleUpvoteMockAdd]} addTypename={false}>
        <UpvoteButton
          ideaId="idea-123"
          initialVoted={false}
          initialCount={42}
          showCount={false}
        />
      </MockedProvider>
    );
    
    expect(screen.queryByText('42')).not.toBeInTheDocument();
  });

  it('applies different sizes', () => {
    const { rerender } = render(
      <MockedProvider mocks={[toggleUpvoteMockAdd]} addTypename={false}>
        <UpvoteButton ideaId="idea-123" initialVoted={false} initialCount={0} size="sm" />
      </MockedProvider>
    );
    
    expect(screen.getByRole('button')).toHaveClass('w-8', 'h-8');

    rerender(
      <MockedProvider mocks={[toggleUpvoteMockAdd]} addTypename={false}>
        <UpvoteButton ideaId="idea-123" initialVoted={false} initialCount={0} size="lg" />
      </MockedProvider>
    );
    
    expect(screen.getByRole('button')).toHaveClass('w-12', 'h-12');
  });

  it('has correct aria-label when not voted', () => {
    render(
      <MockedProvider mocks={[toggleUpvoteMockAdd]} addTypename={false}>
        <UpvoteButton ideaId="idea-123" initialVoted={false} initialCount={0} />
      </MockedProvider>
    );
    
    expect(screen.getByRole('button', { name: 'Upvote' })).toBeInTheDocument();
  });

  it('has correct aria-label when voted', () => {
    render(
      <MockedProvider mocks={[toggleUpvoteMockAdd]} addTypename={false}>
        <UpvoteButton ideaId="idea-123" initialVoted={true} initialCount={0} />
      </MockedProvider>
    );
    
    expect(screen.getByRole('button', { name: 'Remove upvote' })).toBeInTheDocument();
  });
});
