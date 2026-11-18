import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import IdeasList from '../IdeasList';
import { sidebarVar, userVar } from 'features/core/apollo/localState';
import * as useSafeQueryModule from 'features/common-ui/api/useSafeQuery';
import type {
  ApolloCache,
  DefaultContext,
  MutationUpdaterFunction,
  NormalizedCacheObject,
} from '@apollo/client';

const mockSetMessage = jest.fn();
const mockNavigate = jest.fn();
const mockLocation = { pathname: '/ideas/idea-1/description' };

jest.mock('react-router-dom', () => ({
  ...jest.requireActual('react-router-dom'),
  useNavigate: () => mockNavigate,
  useLocation: () => mockLocation,
}));

jest.mock('features/notifications/context/MessageContext', () => ({
  useMessage: () => ({
    setMessage: mockSetMessage,
    clearMessage: jest.fn(),
    message: { text: null, type: 'info' as const },
  }),
}));

const mockDeleteIdea = jest.fn();
const mockCreateIdea = jest.fn();

jest.mock('@apollo/client/react', () => {
  const actual = jest.requireActual('@apollo/client/react');
  return {
    ...actual,
    useMutation: (query: any, options: any) => {
      const queryStr = query?.loc?.source?.body || '';
      if (queryStr.includes('DeleteIdea') || queryStr.includes('deleteIdea')) {
        return [mockDeleteIdea, { loading: false, error: null }];
      }
      if (queryStr.includes('CreateIdea') || queryStr.includes('createIdea')) {
        return [mockCreateIdea, { loading: false, error: null }];
      }
      return [jest.fn(), { loading: false, error: null }];
    },
  };
});

const mockIdeas = [
  {
    ideaId: 'idea-1',
    title: 'Test Idea 1',
    description: 'Description 1',
    pitchDeck: null,
    productRequirementsDocument: null,
    provisionalPatent: null,
    businessModelCanvas: null,
  },
  {
    ideaId: 'idea-2',
    title: 'Test Idea 2',
    description: 'Description 2',
    pitchDeck: null,
    productRequirementsDocument: null,
    provisionalPatent: null,
    businessModelCanvas: null,
  },
];

const mockUseSafeQuery = jest.spyOn(useSafeQueryModule, 'useSafeQuery');

describe('IdeasList Component - Delete Functionality', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    localStorage.removeItem('manifest.ideasSort');
    sidebarVar({ currentIdeaId: 'idea-1', allIdeaIds: ['idea-1', 'idea-2'] });
    userVar({ isLoggedIn: true, userData: null });
    mockUseSafeQuery.mockReturnValue({
      data: { ideas: mockIdeas },
      error: undefined,
      loading: false,
      refetch: jest.fn(),
    } as any);
    mockDeleteIdea.mockResolvedValue({ data: { deleteIdea: true } });
    mockCreateIdea.mockResolvedValue({ data: { createIdea: { ideaId: 'new-id' } } });
  });

  afterEach(() => {
    sidebarVar({ currentIdeaId: null, allIdeaIds: [] });
    userVar({ isLoggedIn: false, userData: null });
  });

  const renderComponent = () => {
    return render(
      <BrowserRouter>
        <IdeasList />
      </BrowserRouter>
    );
  };

  it('should render delete button for each idea', async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Test Idea 1')).toBeInTheDocument();
    });

    const deleteButtons = screen.getAllByLabelText(/Delete idea:/);
    expect(deleteButtons.length).toBeGreaterThan(0);
  });

  it('should call delete mutation when delete button is clicked', async () => {
    const user = userEvent.setup();
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Test Idea 1')).toBeInTheDocument();
    });

    const deleteButton = screen.getByLabelText('Delete idea: Test Idea 1');
    await user.click(deleteButton);

    await waitFor(() => {
      expect(mockDeleteIdea).toHaveBeenCalledWith(
        expect.objectContaining({ variables: { ideaId: 'idea-1' } })
      );
    });

    await waitFor(() => {
      expect(mockSetMessage).toHaveBeenCalledWith('Idea deleted successfully', 'info');
    });
  });

  it('should navigate to /ideas when deleting the currently selected idea', async () => {
    const user = userEvent.setup();
    sidebarVar({ currentIdeaId: 'idea-1', allIdeaIds: ['idea-1', 'idea-2'] });
    
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Test Idea 1')).toBeInTheDocument();
    });

    const deleteButton = screen.getByLabelText('Delete idea: Test Idea 1');
    await user.click(deleteButton);

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/ideas');
    });
  });

  it('should not navigate when deleting a non-selected idea', async () => {
    const user = userEvent.setup();
    sidebarVar({ currentIdeaId: 'idea-1', allIdeaIds: ['idea-1', 'idea-2'] });
    
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Test Idea 2')).toBeInTheDocument();
    });

    const deleteButton = screen.getByLabelText('Delete idea: Test Idea 2');
    await user.click(deleteButton);

    await waitFor(() => {
      expect(mockDeleteIdea).toHaveBeenCalledWith(
        expect.objectContaining({ variables: { ideaId: 'idea-2' } })
      );
    });

    await waitFor(() => {
      expect(mockSetMessage).toHaveBeenCalledWith('Idea deleted successfully', 'info');
    });

    expect(mockNavigate).not.toHaveBeenCalledWith('/ideas');
  });

  it('should handle delete error gracefully', async () => {
    const user = userEvent.setup();
    mockDeleteIdea.mockRejectedValueOnce(new Error('Failed to delete idea'));
    
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Test Idea 1')).toBeInTheDocument();
    });

    const deleteButton = screen.getByLabelText('Delete idea: Test Idea 1');
    await user.click(deleteButton);

    await waitFor(() => {
      expect(mockSetMessage).toHaveBeenCalledWith('Failed to delete idea. Please try again.', 'error');
    });
  });

  // Task #48: Apollo v4 mutate() rejects with an ApolloError that carries
  // graphQLErrors[]. The handler must surface that message verbatim so the
  // user sees the real reason ("Idea not found", "permission denied", etc.)
  // instead of always seeing the generic toast.
  it('should surface the underlying GraphQL error message when present', async () => {
    const user = userEvent.setup();
    const apolloLikeError = Object.assign(new Error('GraphQL error'), {
      graphQLErrors: [{ message: 'Idea not found or you do not have permission to delete it' }],
    });
    mockDeleteIdea.mockRejectedValueOnce(apolloLikeError);

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Test Idea 1')).toBeInTheDocument();
    });

    const deleteButton = screen.getByLabelText('Delete idea: Test Idea 1');
    await user.click(deleteButton);

    await waitFor(() => {
      expect(mockSetMessage).toHaveBeenCalledWith(
        'Idea not found or you do not have permission to delete it',
        'error'
      );
    });
  });

  // Task #48: Apollo Client v4 wraps server-side GraphQL errors in a
  // CombinedGraphQLErrors instance whose individual errors live on
  // `.errors` (NOT the legacy v3 `.graphQLErrors`). The handler MUST
  // read v4-shaped errors so resolver-classified messages
  // ("related records prevent…", "Idea not found…") reach the toast
  // verbatim instead of being swallowed by the generic fallback.
  it('should surface v4 CombinedGraphQLErrors-shaped error message', async () => {
    const user = userEvent.setup();
    // Real v4 errors are CombinedGraphQLErrors instances, but the
    // user-facing handler only depends on the duck-typed `.errors[0].message`
    // shape. We construct an Error subclass that mimics the v4 instance
    // (no legacy `graphQLErrors` field) to prove the handler doesn't
    // silently fall back to the generic toast.
    const v4LikeError = Object.assign(new Error('GraphQL error'), {
      errors: [
        {
          message:
            'Failed to delete idea: related records prevented deletion. Please contact support if this persists.',
        },
      ],
    });
    mockDeleteIdea.mockRejectedValueOnce(v4LikeError);

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Test Idea 1')).toBeInTheDocument();
    });

    const deleteButton = screen.getByLabelText('Delete idea: Test Idea 1');
    await user.click(deleteButton);

    await waitFor(() => {
      expect(mockSetMessage).toHaveBeenCalledWith(
        'Failed to delete idea: related records prevented deletion. Please contact support if this persists.',
        'error'
      );
    });
    // Critically: the generic fallback toast must NOT appear, otherwise
    // we've regressed to the v3-only path.
    expect(mockSetMessage).not.toHaveBeenCalledWith(
      'Failed to delete idea. Please try again.',
      'error'
    );
  });

  // Task #48: Guard against the regression where v4 returns
  // { data: { deleteIdea: false } } (server reached but no row deleted).
  // The handler must roll back the optimistic UI removal AND show the
  // generic error toast — never silently flip to "Idea deleted successfully".
  it('should roll back and show error when server returns deleteIdea: false', async () => {
    const user = userEvent.setup();
    mockDeleteIdea.mockResolvedValueOnce({ data: { deleteIdea: false } });

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Test Idea 1')).toBeInTheDocument();
    });

    const deleteButton = screen.getByLabelText('Delete idea: Test Idea 1');
    await user.click(deleteButton);

    await waitFor(() => {
      expect(mockSetMessage).toHaveBeenCalledWith(
        'Failed to delete idea. Please try again.',
        'error'
      );
    });
    // Sidebar must contain the rolled-back set, including idea-1.
    expect(sidebarVar().allIdeaIds).toContain('idea-1');
  });

  // Task #48: The new code passes an `update` callback so cache writes are
  // synchronous (no refetchQueries race). Verify the second argument shape
  // — older code passed only { variables }, newer code passes
  // { variables, update }. This locks in the v4 contract.
  it('should pass an update callback to the delete mutation', async () => {
    const user = userEvent.setup();
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Test Idea 1')).toBeInTheDocument();
    });

    const deleteButton = screen.getByLabelText('Delete idea: Test Idea 1');
    await user.click(deleteButton);

    await waitFor(() => {
      expect(mockDeleteIdea).toHaveBeenCalled();
    });
    const callArg = mockDeleteIdea.mock.calls[0][0];
    expect(callArg.variables).toEqual({ ideaId: 'idea-1' });
    expect(typeof callArg.update).toBe('function');
  });

  it('should have proper aria-label on delete button', async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Test Idea 1')).toBeInTheDocument();
    });

    const deleteButton = screen.getByLabelText('Delete idea: Test Idea 1');
    expect(deleteButton).toBeInTheDocument();
  });

  it('should render trash icon in delete button', async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Test Idea 1')).toBeInTheDocument();
    });

    const deleteButton = screen.getByLabelText('Delete idea: Test Idea 1');
    const svgIcon = deleteButton.querySelector('svg');
    expect(svgIcon).toBeInTheDocument();
  });

  it('should render New Idea button', async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'New Idea' })).toBeInTheDocument();
    });

    expect(screen.getByRole('heading', { name: 'Ideas' })).toBeInTheDocument();
    expect(screen.getByTestId('ideas-count-label')).toHaveTextContent('2');
    expect(screen.getByLabelText('2 ideas')).toBeInTheDocument();
  });

  it('supports arrow-key navigation between ideas', async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Test Idea 1')).toBeInTheDocument();
    });

    const firstIdea = screen.getByLabelText('Open idea Test Idea 1');
    const secondIdea = screen.getByLabelText('Open idea Test Idea 2');

    firstIdea.focus();
    fireEvent.keyDown(firstIdea, { key: 'ArrowDown' });

    expect(secondIdea).toHaveFocus();
  });

  it('renders collapsed library rail when requested', async () => {
    render(
      <BrowserRouter>
        <IdeasList collapsed onToggleCollapse={jest.fn()} />
      </BrowserRouter>
    );

    await waitFor(() => {
      expect(screen.getByLabelText('Expand ideas')).toBeInTheDocument();
    });

    expect(screen.getByLabelText('Open idea 1: Test Idea 1')).toBeInTheDocument();
    expect(screen.getByLabelText('Expand ideas').querySelector('svg')).toBeInTheDocument();
    expect(screen.getByLabelText('Create new idea').querySelector('svg')).toBeInTheDocument();
    expect(screen.getByLabelText('Expand ideas')).toHaveClass('manifest-control-secondary');
  });

  it('uses a quiet icon button for the expanded collapse control', async () => {
    render(
      <BrowserRouter>
        <IdeasList onToggleCollapse={jest.fn()} />
      </BrowserRouter>
    );

    await waitFor(() => {
      expect(screen.getByLabelText('Collapse ideas')).toBeInTheDocument();
    });

    expect(screen.getByLabelText('Collapse ideas')).toHaveClass('manifest-sidebar-icon');
    expect(screen.getByLabelText('Collapse ideas')).toHaveAttribute('aria-expanded', 'true');
  });

  // Task #48: Lock in that the Apollo cache update REALLY removes the
  // deleted idea so it cannot reappear after a refetch / re-read of
  // GET_IDEAS. We exercise the actual `update` callback against a real
  // InMemoryCache configured with the same keyFields the app uses, then
  // re-read the ideas query and assert the deleted entity is gone.
  it("update callback evicts the deleted idea from a real Apollo cache", async () => {
    const { InMemoryCache, gql } = await import("@apollo/client");

    const IDEAS_QUERY = gql`
      query Ideas {
        ideas {
          ideaId
          title
        }
      }
    `;

    const cache = new InMemoryCache({
      typePolicies: {
        Idea: { keyFields: ["ideaId"] },
        IdeaSummary: { keyFields: ["ideaId"] },
      },
    });

    cache.writeQuery({
      query: IDEAS_QUERY,
      data: {
        ideas: [
          { __typename: "Idea", ideaId: "idea-1", title: "Test Idea 1" },
          { __typename: "Idea", ideaId: "idea-2", title: "Test Idea 2" },
        ],
      },
    });

    // Trigger handleDeleteIdea so we capture the real update callback the
    // component passes to mutate(), instead of redefining it in the test.
    const user = userEvent.setup();
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText("Test Idea 1")).toBeInTheDocument();
    });
    await user.click(screen.getByLabelText("Delete idea: Test Idea 1"));
    await waitFor(() => {
      expect(mockDeleteIdea).toHaveBeenCalled();
    });

    const update = mockDeleteIdea.mock.calls[0][0].update as MutationUpdaterFunction<
      { deleteIdea: boolean },
      { ideaId: string },
      DefaultContext,
      ApolloCache<NormalizedCacheObject>
    >;

    // Success path: delete confirmed by server. Cache must drop idea-1.
    update(cache, { data: { deleteIdea: true } }, { context: {} });

    const after = cache.readQuery<{ ideas: Array<{ ideaId: string; title: string }> }>({
      query: IDEAS_QUERY,
    });
    expect(after?.ideas.map((i) => i.ideaId)).toEqual(["idea-2"]);
    // cache.identify() just builds a cache key string; to confirm the
    // entity is gone we have to look at the actual normalized store.
    const extracted = cache.extract();
    expect(extracted["Idea:{\"ideaId\":\"idea-1\"}"]).toBeUndefined();
    expect(extracted["Idea:{\"ideaId\":\"idea-2\"}"]).toBeDefined();
  });

  it("update callback is a no-op when the server returns deleteIdea: false", async () => {
    const { InMemoryCache, gql } = await import("@apollo/client");

    const IDEAS_QUERY = gql`
      query Ideas {
        ideas {
          ideaId
          title
        }
      }
    `;

    const cache = new InMemoryCache({
      typePolicies: {
        Idea: { keyFields: ["ideaId"] },
        IdeaSummary: { keyFields: ["ideaId"] },
      },
    });
    cache.writeQuery({
      query: IDEAS_QUERY,
      data: {
        ideas: [
          { __typename: "Idea", ideaId: "idea-1", title: "Test Idea 1" },
          { __typename: "Idea", ideaId: "idea-2", title: "Test Idea 2" },
        ],
      },
    });

    const user = userEvent.setup();
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText("Test Idea 1")).toBeInTheDocument();
    });
    await user.click(screen.getByLabelText("Delete idea: Test Idea 1"));
    await waitFor(() => {
      expect(mockDeleteIdea).toHaveBeenCalled();
    });

    const update = mockDeleteIdea.mock.calls[0][0].update as MutationUpdaterFunction<
      { deleteIdea: boolean },
      { ideaId: string },
      DefaultContext,
      ApolloCache<NormalizedCacheObject>
    >;

    update(cache, { data: { deleteIdea: false } }, { context: {} });

    // Both ideas must still be present and addressable in the cache.
    const after = cache.readQuery<{ ideas: Array<{ ideaId: string; title: string }> }>({
      query: IDEAS_QUERY,
    });
    expect(after?.ideas.map((i) => i.ideaId).sort()).toEqual(["idea-1", "idea-2"]);
    expect(cache.identify({ __typename: "Idea", ideaId: "idea-1" })).toBeDefined();
  });

  it('renders large idea libraries incrementally', async () => {
    const manyIdeas = Array.from({ length: 120 }, (_, index) => ({
      ideaId: `idea-${index + 1}`,
      title: `Idea ${index + 1}`,
      hasDescription: index % 2 === 0,
      generatedAssetCount: 0,
    }));

    sidebarVar({ currentIdeaId: 'idea-1', allIdeaIds: [] });
    mockUseSafeQuery.mockReturnValue({
      data: { ideas: manyIdeas },
      error: undefined,
      loading: false,
      refetch: jest.fn(),
    } as any);

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Idea 1')).toBeInTheDocument();
      expect(screen.getByText('Idea 80')).toBeInTheDocument();
    });

    expect(screen.queryByText('Idea 81')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /load more ideas/i })).toBeInTheDocument();
  });

  it('renders simplified expanded rows without index, asset count, or drafted badges', async () => {
    mockUseSafeQuery.mockReturnValue({
      data: {
        ideas: [
          {
            ideaId: 'idea-1',
            title: 'Blockchain Startup',
            createdAt: '2024-01-01T00:00:00.000Z',
            hasDescription: true,
            generatedAssetCount: 4,
            isPublished: true,
          },
          {
            ideaId: 'idea-2',
            title: 'Second Idea',
            createdAt: '2024-01-02T00:00:00.000Z',
            hasDescription: false,
            generatedAssetCount: 0,
            isPublished: false,
          },
        ],
      },
      error: undefined,
      loading: false,
      refetch: jest.fn(),
    } as any);

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Blockchain Startup')).toBeInTheDocument();
    });

    expect(screen.queryByText(/assets ready/i)).not.toBeInTheDocument();
    expect(screen.queryByText('Drafted')).not.toBeInTheDocument();
    expect(screen.queryByText('01')).not.toBeInTheDocument();
    expect(screen.getAllByTestId('idea-publish-badge')).toHaveLength(2);
    expect(screen.getAllByLabelText(/Delete idea:/)).toHaveLength(2);
  });

  it('renders a sort control and reorders ideas alphabetically', async () => {
    const user = userEvent.setup();
    const sortableIdeas = [
      {
        ideaId: 'idea-z',
        title: 'Zebra Startup',
        createdAt: '2024-03-01T00:00:00.000Z',
      },
      {
        ideaId: 'idea-a',
        title: 'Alpha Startup',
        createdAt: '2024-01-01T00:00:00.000Z',
      },
    ];

    sidebarVar({ currentIdeaId: 'idea-z', allIdeaIds: ['idea-z', 'idea-a'] });
    mockUseSafeQuery.mockReturnValue({
      data: { ideas: sortableIdeas },
      error: undefined,
      loading: false,
      refetch: jest.fn(),
    } as any);

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Zebra Startup')).toBeInTheDocument();
    });

    const getOpenIdeaLabels = () =>
      screen.getAllByLabelText(/^Open idea /).map((node) => node.getAttribute('aria-label'));

    expect(getOpenIdeaLabels()[0]).toBe('Open idea Zebra Startup');

    await user.selectOptions(screen.getByTestId('ideas-sort-select'), 'alpha');

    expect(getOpenIdeaLabels()[0]).toBe('Open idea Alpha Startup');
    expect(getOpenIdeaLabels()[1]).toBe('Open idea Zebra Startup');
  });

  it('persists the selected sort option in localStorage', async () => {
    const user = userEvent.setup();
    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('ideas-sort-select')).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByTestId('ideas-sort-select'), 'oldest');

    expect(localStorage.getItem('manifest.ideasSort')).toBe('oldest');
  });
});
