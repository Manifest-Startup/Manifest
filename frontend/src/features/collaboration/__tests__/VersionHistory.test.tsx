import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MockedProvider } from '@apollo/client/testing/react';
import { VersionHistory } from '../components/VersionHistory';
import { GET_IDEA_VERSIONS, CREATE_IDEA_VERSION, RESTORE_IDEA_VERSION } from 'features/core/apollo/queries';
import { MessageProvider } from 'features/notifications/context/MessageContext';

const mockVersions = [
  {
    versionId: 'v-3',
    ideaId: 'idea-123',
    versionNumber: 3,
    title: 'Latest Title',
    description: 'Latest description',
    createdBy: 'user-123',
    createdAt: new Date().toISOString(),
    changeSummary: 'Updated description',
    creatorName: 'John Doe',
    creatorAvatar: null,
    versionKind: 'manual',
  },
  {
    versionId: 'v-2',
    ideaId: 'idea-123',
    versionNumber: 2,
    title: 'Previous Title',
    description: 'Previous description',
    createdBy: 'user-123',
    createdAt: new Date(Date.now() - 3600000).toISOString(),
    changeSummary: 'Initial draft',
    creatorName: 'John Doe',
    creatorAvatar: null,
    versionKind: 'auto',
  },
  {
    versionId: 'v-1',
    ideaId: 'idea-123',
    versionNumber: 1,
    title: 'First Title',
    description: 'First description',
    createdBy: 'user-123',
    createdAt: new Date(Date.now() - 86400000).toISOString(),
    changeSummary: 'Version 1',
    creatorName: 'John Doe',
    creatorAvatar: null,
    versionKind: 'manual',
  },
];

const mocks = [
  {
    request: {
      query: GET_IDEA_VERSIONS,
      variables: { ideaId: 'idea-123' },
    },
    result: {
      data: {
        ideaVersions: mockVersions,
      },
    },
  },
  {
    request: {
      query: CREATE_IDEA_VERSION,
      variables: { ideaId: 'idea-123', changeSummary: 'Test save' },
    },
    result: {
      data: {
        createIdeaVersion: {
          versionId: 'v-4',
          versionNumber: 4,
          changeSummary: 'Test save',
          createdAt: new Date().toISOString(),
          versionKind: 'manual',
        },
      },
    },
  },
];

const emptyMocks = [
  {
    request: {
      query: GET_IDEA_VERSIONS,
      variables: { ideaId: 'idea-empty' },
    },
    result: {
      data: {
        ideaVersions: [],
      },
    },
  },
];

const renderVersionHistory = (ideaId = 'idea-123', isOpen = true, customMocks = mocks) => {
  return render(
    <MockedProvider mocks={customMocks} addTypename={false}>
      <MessageProvider>
        <VersionHistory 
          ideaId={ideaId} 
          isOpen={isOpen} 
          onClose={() => {}} 
          onVersionRestored={() => {}}
        />
      </MessageProvider>
    </MockedProvider>
  );
};

describe('VersionHistory', () => {
  it('renders nothing when closed', () => {
    const { container } = renderVersionHistory('idea-123', false);
    expect(container.firstChild).toBeNull();
  });

  it('renders modal when open', () => {
    renderVersionHistory();
    expect(screen.getByText('Version History')).toBeInTheDocument();
  });

  it('displays loading state initially', () => {
    renderVersionHistory();
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('displays versions after loading', async () => {
    renderVersionHistory();
    await waitFor(() => {
      expect(screen.getByText('Updated description')).toBeInTheDocument();
    });
    expect(screen.getByText('Initial draft')).toBeInTheDocument();
  });

  it('shows version numbers', async () => {
    renderVersionHistory();
    await waitFor(() => {
      expect(screen.getByText('v3')).toBeInTheDocument();
    });
    expect(screen.getByText('v2')).toBeInTheDocument();
    expect(screen.getByText('v1')).toBeInTheDocument();
  });

  it('shows empty state when no versions', async () => {
    renderVersionHistory('idea-empty', true, emptyMocks);
    await waitFor(() => {
      expect(screen.getByText('No version history yet')).toBeInTheDocument();
    });
  });

  it('has version note input', () => {
    renderVersionHistory();
    expect(screen.getByPlaceholderText('Version note (optional)')).toBeInTheDocument();
  });

  it('has save version button', () => {
    renderVersionHistory();
    expect(screen.getByText('Save Version')).toBeInTheDocument();
  });

  it('shows restore button on hover', async () => {
    renderVersionHistory();
    await waitFor(() => {
      expect(screen.getAllByText('Restore').length).toBeGreaterThan(0);
    });
  });
});
