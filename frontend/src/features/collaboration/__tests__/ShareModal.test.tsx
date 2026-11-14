import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MockedProvider } from '@apollo/client/testing/react';
import { ShareModal } from '../components/ShareModal';
import { GET_IDEA_COLLABORATORS, INVITE_COLLABORATOR, REMOVE_COLLABORATOR } from 'features/core/apollo/queries';
import { MessageProvider } from 'features/notifications/context/MessageContext';

const mockCollaborators = [
  {
    collaboratorId: null,
    ideaId: 'idea-123',
    userId: 'owner-123',
    role: 'owner',
    status: 'accepted',
    userEmail: 'owner@test.com',
    userName: 'Test Owner',
    userAvatar: null,
    invitedAt: null,
    acceptedAt: null,
  },
  {
    collaboratorId: 'collab-1',
    ideaId: 'idea-123',
    userId: 'user-456',
    role: 'editor',
    status: 'accepted',
    userEmail: 'editor@test.com',
    userName: 'Test Editor',
    userAvatar: null,
    invitedAt: '2024-01-01T00:00:00Z',
    acceptedAt: '2024-01-01T01:00:00Z',
  },
];

const mocks = [
  {
    request: {
      query: GET_IDEA_COLLABORATORS,
      variables: { ideaId: 'idea-123' },
    },
    result: {
      data: {
        ideaCollaborators: mockCollaborators,
      },
    },
  },
  {
    request: {
      query: INVITE_COLLABORATOR,
      variables: {
        input: {
          ideaId: 'idea-123',
          email: 'new@test.com',
          role: 'viewer',
        },
      },
    },
    result: {
      data: {
        inviteCollaborator: {
          success: true,
          message: 'Invitation sent to new@test.com',
        },
      },
    },
  },
];

const renderShareModal = (isOpen = true) => {
  return render(
    <MockedProvider mocks={mocks} addTypename={false}>
      <MessageProvider>
        <ShareModal ideaId="idea-123" isOpen={isOpen} onClose={() => {}} />
      </MessageProvider>
    </MockedProvider>
  );
};

describe('ShareModal', () => {
  it('renders nothing when closed', () => {
    const { container } = renderShareModal(false);
    expect(container.firstChild).toBeNull();
  });

  it('renders modal when open', async () => {
    renderShareModal();
    expect(screen.getByText('Share Idea')).toBeInTheDocument();
  });

  it('displays loading state initially', () => {
    renderShareModal();
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('displays collaborators after loading', async () => {
    renderShareModal();
    await waitFor(() => {
      expect(screen.getByText('Test Owner')).toBeInTheDocument();
    });
    expect(screen.getByText('Test Editor')).toBeInTheDocument();
  });

  it('shows owner badge for idea owner', async () => {
    renderShareModal();
    await waitFor(() => {
      expect(screen.getByText('Owner')).toBeInTheDocument();
    });
  });

  it('has email input field', () => {
    renderShareModal();
    expect(screen.getByPlaceholderText('Enter email address')).toBeInTheDocument();
  });

  it('has role selector', () => {
    renderShareModal();
    expect(screen.getByRole('combobox')).toBeInTheDocument();
  });

  it('has send invite button', () => {
    renderShareModal();
    expect(screen.getByText('Send Invite')).toBeInTheDocument();
  });

  it('disables send button when email is empty', () => {
    renderShareModal();
    const button = screen.getByText('Send Invite');
    expect(button).toBeDisabled();
  });

  it('enables send button when email is entered', () => {
    renderShareModal();
    const input = screen.getByPlaceholderText('Enter email address');
    fireEvent.change(input, { target: { value: 'new@test.com' } });
    const button = screen.getByText('Send Invite');
    expect(button).not.toBeDisabled();
  });
});
