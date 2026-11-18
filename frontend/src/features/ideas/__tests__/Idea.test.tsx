import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Idea } from '../components/Idea';

// Mock dependencies
const mockSetMessage = jest.fn();
const mockPatchIdea = jest.fn();
const mockRefetch = jest.fn();
const mockNavigate = jest.fn();

// Mock reactive variables
let mockSidebarVar = { currentIdeaId: 'idea-1' };
let mockEditorStatusVar = 'idle';
let mockSimilarIdeasVar = { ideaId: 'idea-1', data: '', loading: false, error: null, byIdeaId: {} };

// Mock useParams
const mockUseParams = jest.fn(() => ({ ideaAspect: 'description' }));

jest.mock('react-router-dom', () => ({
  ...jest.requireActual('react-router-dom'),
  useParams: () => mockUseParams(),
  useNavigate: () => mockNavigate,
}));

jest.mock('features/notifications/context/MessageContext', () => ({
  useMessage: () => ({
    setMessage: mockSetMessage,
    clearMessage: jest.fn(),
    message: { text: null, type: 'info' as const },
  }),
}));

// Define mock before jest.mock calls to avoid hoisting issues
const mockUseMutation = jest.fn();

// Store reference to actual local state for setting reactive variables in tests
const actualLocalState = jest.requireActual('features/core/apollo/localState');

jest.mock('features/core/apollo/localState', () => {
  const actual = jest.requireActual('features/core/apollo/localState');
  return {
    ...actual,
    sidebarVar: actual.sidebarVar,
    editorStatusVar: actual.editorStatusVar,
    similarIdeasVar: actual.similarIdeasVar,
  };
});

jest.mock('@apollo/client/react', () => {
  const actual = jest.requireActual('@apollo/client/react');
  return {
    ...actual,
    useReactiveVar: (varFn: any) => {
      return varFn ? varFn() : null;
    },
    useMutation: (...args: any[]) => mockUseMutation(...args),
    client: {
      query: jest.fn().mockResolvedValue({ data: { findSimilarIdeas: { similarIdeas: [] } } }),
      refetchQueries: jest.fn().mockResolvedValue(undefined),
    },
  };
});

// Import useSafeQuery mock for setting up in beforeEach
import { useSafeQuery } from 'features/common-ui/api/useSafeQuery';
jest.mock('features/common-ui/api/useSafeQuery', () => ({
  useSafeQuery: jest.fn(),
}));
const mockUseSafeQuery = useSafeQuery as jest.Mock;

// Mock TextArea component
jest.mock('features/common-ui/TextArea', () => ({
  __esModule: true,
  default: ({ value, onChange, editable, className }: any) => (
    <textarea
      data-testid="idea-textarea"
      className={className}
      value={value}
      onChange={(e) => onChange?.(e.target.value)}
      disabled={!editable}
    />
  ),
}));

// Mock other components
jest.mock('features/common-ui/PatentPdfViewer', () => ({
  __esModule: true,
  default: () => <div>Patent PDF Viewer</div>,
}));

jest.mock('react-markdown', () => ({
  __esModule: true,
  default: ({ children }: { children: any }) => <div>{children}</div>,
}));

// Collaboration components are integration-heavy and not under test here.
jest.mock('features/collaboration', () => ({
  ShareButton: () => null,
  VersionButton: () => null,
}));

describe('Idea Component - Title Editing', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockSidebarVar = { currentIdeaId: 'idea-1', currentIdeaAspect: 'description', allIdeaIds: [] };
    mockEditorStatusVar = 'idle';
    mockSimilarIdeasVar = { ideaId: 'idea-1', data: '', loading: false, error: null, byIdeaId: {} };
    mockUseParams.mockReturnValue({ ideaAspect: 'description' });
    mockPatchIdea.mockResolvedValue({
      data: {
        updateIdea: {
          ideaId: 'idea-1',
          title: 'Updated Title',
        },
      },
    });
    // Setup useSafeQuery mock after clearAllMocks
    mockUseSafeQuery.mockImplementation((query: any, options?: any) => ({
      data: {
        idea: {
          ideaId: options?.variables?.ideaId || 'idea-1',
          title: 'Brand New Idea',
          description: 'Initial description',
        },
      },
      loading: false,
      refetch: mockRefetch,
    }));
    // Set the reactive variables to the mock values
    actualLocalState.sidebarVar(mockSidebarVar);
    actualLocalState.editorStatusVar(mockEditorStatusVar);
    actualLocalState.similarIdeasVar(mockSimilarIdeasVar);
    mockUseMutation.mockImplementation(() => [mockPatchIdea, { loading: false, error: null }]);
  });

  it('shows cached note content on mount and when switching ideas without saving it', async () => {
    const cached = {
      'idea-1': { data: { idea: { ideaId: 'idea-1', title: 'First', description: 'First saved words' } }, loading: false },
      'idea-2': { data: { idea: { ideaId: 'idea-2', title: 'Second', description: 'Second saved words' } }, loading: false },
    };
    const skipped = { data: undefined, loading: false };
    mockUseSafeQuery.mockImplementation((_query: any, options?: any) =>
      options?.skip ? skipped : cached[options?.variables?.ideaId as keyof typeof cached] || skipped
    );
    const { rerender } = render(<Idea />);
    expect(await screen.findByTestId('idea-textarea')).toHaveValue('First saved words');
    actualLocalState.sidebarVar({ ...mockSidebarVar, currentIdeaId: 'idea-2' });
    rerender(<Idea />);
    expect(screen.getByTestId('idea-textarea')).toHaveValue('Second saved words');
    expect(mockPatchIdea).not.toHaveBeenCalled();
  });

  it('should not revert title when user edits and blurs before save completes', async () => {
    const user = userEvent.setup({ delay: null });
    
    render(<Idea />);

    // Find the title input
    const titleInput = screen.getByLabelText('Idea title') as HTMLInputElement;
    expect(titleInput).toBeInTheDocument();

    // Clear and type new title
    await user.clear(titleInput);
    await user.type(titleInput, 'My New Title');

    // Verify title is updated locally
    expect(titleInput.value).toBe('My New Title');

    // Blur the input (simulating Tab key)
    fireEvent.blur(titleInput);

    // Verify title is still the new value immediately after blur
    expect(titleInput.value).toBe('My New Title');

    // Wait a bit to ensure the sync useEffect doesn't revert it
    await waitFor(() => {
      expect(titleInput.value).toBe('My New Title');
    }, { timeout: 1000 });

    // Verify that patchIdea was called
    await waitFor(() => {
      expect(mockPatchIdea).toHaveBeenCalledWith({
        variables: {
          ideaId: 'idea-1',
          title: 'My New Title',
        },
      });
    });
  });

  it('should save title when user edits and blurs', async () => {
    const user = userEvent.setup({ delay: null });
    
    render(<Idea />);

    const titleInput = screen.getByLabelText('Idea title') as HTMLInputElement;

    // Change the title
    await user.clear(titleInput);
    await user.type(titleInput, 'Updated Title');

    // Blur to trigger save
    fireEvent.blur(titleInput);

    // Wait for the save to be triggered (throttled save is flushed on blur)
    await waitFor(() => {
      expect(mockPatchIdea).toHaveBeenCalledWith({
        variables: {
          ideaId: 'idea-1',
          title: 'Updated Title',
        },
      });
    });
  });

  it('should not overwrite title while save is in progress', async () => {
    const user = userEvent.setup({ delay: null });
    
    // Mock a slow save
    let resolveSave: (value: any) => void;
    const savePromise = new Promise((resolve) => {
      resolveSave = resolve;
    });
    mockPatchIdea.mockReturnValue(savePromise);

    render(<Idea />);

    const titleInput = screen.getByLabelText('Idea title') as HTMLInputElement;

    // Change the title
    await user.clear(titleInput);
    await user.type(titleInput, 'New Title');

    // Blur to trigger save
    fireEvent.blur(titleInput);

    // The save is now in progress (but not completed)
    // Simulate a refetch/update from backend with old title
    // This should NOT overwrite the current title
    await waitFor(() => {
      expect(titleInput.value).toBe('New Title');
    });

    // Resolve the save
    resolveSave!({
      data: {
        updateIdea: {
          ideaId: 'idea-1',
          title: 'New Title',
        },
      },
    });

    await waitFor(() => {
      expect(titleInput.value).toBe('New Title');
    });
  });

  it('shows an inline edit cue and lets users cancel with Escape', async () => {
    const user = userEvent.setup({ delay: null });

    render(<Idea />);

    const titleInput = screen.getByLabelText('Idea title') as HTMLInputElement;
    expect(screen.getByText('Click the title to rename this idea.')).toBeInTheDocument();

    await user.clear(titleInput);
    await user.type(titleInput, 'Temporary Rename');

    expect(screen.getByText('Press Enter to save, or Esc to cancel.')).toBeInTheDocument();

    fireEvent.keyDown(titleInput, { key: 'Escape', code: 'Escape' });

    await waitFor(() => {
      expect(titleInput.value).toBe('Brand New Idea');
    });

    expect(mockPatchIdea).not.toHaveBeenCalled();
  });

  it('should sync title from backend when not editing', async () => {
    const useSafeQueryModule = require('features/common-ui/api/useSafeQuery');
    const mockUseSafeQuery = useSafeQueryModule.useSafeQuery as jest.Mock;
    
    // Start with one title
    mockUseSafeQuery.mockImplementation((query: any) => {
      const queryDef = query?.definitions?.[0];
      const operationName = queryDef?.name?.value;
      if (operationName === 'GetIdeaCore') {
        return {
          data: {
            idea: {
              ideaId: 'idea-1',
              title: 'Initial Title',
              description: 'Description',
            },
          },
          loading: false,
          refetch: mockRefetch,
        };
      }
      return { data: null, loading: false };
    });

    const { rerender } = render(<Idea />);

    const titleInput = screen.getByLabelText('Idea title') as HTMLInputElement;
    expect(titleInput).toBeInTheDocument();

    // Simulate backend update with new title (user is NOT editing)
    mockUseSafeQuery.mockImplementation((query: any) => {
      const queryDef = query?.definitions?.[0];
      const operationName = queryDef?.name?.value;
      if (operationName === 'GetIdeaCore') {
        return {
          data: {
            idea: {
              ideaId: 'idea-1',
              title: 'Updated From Backend',
              description: 'Description',
            },
          },
          loading: false,
          refetch: mockRefetch,
        };
      }
      return { data: null, loading: false };
    });

    rerender(<Idea />);

    // Title should sync from backend since user is not editing
    await waitFor(() => {
      const updatedInput = screen.getByDisplayValue('Updated From Backend') as HTMLInputElement;
      expect(updatedInput).toBeInTheDocument();
    });
  });

  it('uses a growable note editor shell for long imported notes', async () => {
    render(<Idea />);

    expect(await screen.findByTestId('idea-textarea')).toHaveClass('min-h-[16rem]');
    expect(screen.getByTestId('idea-textarea')).not.toHaveClass('h-full');
  });

  it('does not refetch the whole idea payload when only the aspect route changes', async () => {
    const { rerender } = render(<Idea />);

    await waitFor(() => {
      expect(screen.getByLabelText('Idea title')).toBeInTheDocument();
    });

    mockRefetch.mockClear();
    mockUseParams.mockReturnValue({ ideaAspect: 'pitch-deck' });

    rerender(<Idea />);

    await waitFor(() => {
      expect(screen.getByLabelText('Idea title')).toBeInTheDocument();
    });

    expect(mockRefetch).not.toHaveBeenCalled();
  });
});
