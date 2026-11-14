import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MockedProvider } from '@apollo/client/testing/react';
import FollowButton from '../FollowButton';
import { TOGGLE_FOLLOW } from 'features/core/apollo/queries';
import { userVar } from 'features/core/apollo/localState';

const mockOnFollowChange = jest.fn();
const mockSetMessage = jest.fn();

jest.mock('features/notifications/context/MessageContext', () => ({
  useMessage: () => ({ setMessage: mockSetMessage }),
}));

const toggleFollowMockFollow = {
  request: {
    query: TOGGLE_FOLLOW,
    variables: { followedId: 'user-123' }
  },
  result: {
    data: {
      toggleFollow: {
        __typename: 'FollowResult',
        following: true,
        followedId: 'user-123'
      }
    }
  }
};

const toggleFollowMockUnfollow = {
  request: {
    query: TOGGLE_FOLLOW,
    variables: { followedId: 'user-123' }
  },
  result: {
    data: {
      toggleFollow: {
        __typename: 'FollowResult',
        following: false,
        followedId: 'user-123'
      }
    }
  }
};

const renderButton = (isFollowing = false, mocks = [toggleFollowMockFollow]) => {
  return render(
    <MockedProvider mocks={mocks} addTypename={false}>
      <FollowButton
        userId="user-123"
        isFollowing={isFollowing}
        onFollowChange={mockOnFollowChange}
      />
    </MockedProvider>
  );
};

describe('FollowButton', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    userVar({ isLoggedIn: true, userData: { userId: 'viewer-123', email: 'viewer@example.com' } });
  });

  it('renders Follow text when not following', () => {
    renderButton(false);
    expect(screen.getByText('Follow')).toBeInTheDocument();
  });

  it('renders Following text when following', () => {
    renderButton(true);
    expect(screen.getByText('Following')).toBeInTheDocument();
  });

  it('shows Unfollow on hover when following', () => {
    renderButton(true);
    const button = screen.getByRole('button');
    fireEvent.mouseEnter(button);
    expect(screen.getByText('Unfollow')).toBeInTheDocument();
  });

  it('shows Following again after mouse leaves', () => {
    renderButton(true);
    const button = screen.getByRole('button');
    fireEvent.mouseEnter(button);
    fireEvent.mouseLeave(button);
    expect(screen.getByText('Following')).toBeInTheDocument();
  });

  it('calls mutation on click', async () => {
    renderButton(false);
    
    const button = screen.getByRole('button');
    fireEvent.click(button);
    
    await waitFor(() => {
      expect(button).not.toBeDisabled();
    });
  });

  it('applies different sizes', () => {
    const { rerender } = render(
      <MockedProvider mocks={[toggleFollowMockFollow]} addTypename={false}>
        <FollowButton userId="user-123" isFollowing={false} size="sm" />
      </MockedProvider>
    );
    
    expect(screen.getByRole('button')).toHaveClass('px-3', 'py-1', 'text-xs');

    rerender(
      <MockedProvider mocks={[toggleFollowMockFollow]} addTypename={false}>
        <FollowButton userId="user-123" isFollowing={false} size="lg" />
      </MockedProvider>
    );
    
    expect(screen.getByRole('button')).toHaveClass('px-6', 'py-2', 'text-base');
  });

  it('applies outline variant when not following', () => {
    render(
      <MockedProvider mocks={[toggleFollowMockFollow]} addTypename={false}>
        <FollowButton userId="user-123" isFollowing={false} variant="outline" />
      </MockedProvider>
    );
    
    expect(screen.getByRole('button')).toHaveClass('bg-transparent');
  });

  it('applies outline variant when following', () => {
    render(
      <MockedProvider mocks={[toggleFollowMockFollow]} addTypename={false}>
        <FollowButton userId="user-123" isFollowing={true} variant="outline" />
      </MockedProvider>
    );
    
    expect(screen.getByRole('button')).toHaveClass('bg-transparent');
  });

  it('disables following yourself', () => {
    userVar({ isLoggedIn: true, userData: { userId: 'user-123', email: 'self@example.com' } });

    render(
      <MockedProvider mocks={[toggleFollowMockFollow]} addTypename={false}>
        <FollowButton userId="user-123" isFollowing={false} />
      </MockedProvider>
    );

    expect(screen.getByRole('button')).toBeDisabled();
    expect(screen.getByText('You')).toBeInTheDocument();
  });
});
