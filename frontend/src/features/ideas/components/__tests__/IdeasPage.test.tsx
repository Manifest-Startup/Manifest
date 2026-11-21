import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import IdeasPage from '../IdeasPage';

jest.mock('react-router-dom', () => ({ useParams: () => ({ idea_id: 'idea-1' }) }));
const mockCreateAndOpen = jest.fn(async () => "new-idea");
jest.mock('../../hooks/useCreateIdea', () => ({ useCreateIdea: () => ({ createAndOpen: mockCreateAndOpen }) }));
jest.mock('@apollo/client/react', () => ({ useReactiveVar: (variable: () => unknown) => variable() }));
jest.mock('../IdeasList', () => ({ __esModule: true, default: ({ onToggleCollapse }: any) => <div>Library content<button onClick={onToggleCollapse}>Collapse ideas</button></div> }));
jest.mock('features/messaging/components', () => ({ IdeaOwnerPanel: ({ onToggleCollapse }: any) => <div>Related content<button onClick={onToggleCollapse}>Collapse similar ideas</button></div> }));
jest.mock('../Idea', () => ({
  Idea: ({ panelActions }: any) => (
    <>{panelActions}<input aria-label="Draft" defaultValue="Keep my words" /></>
  ),
}));

describe('Workspace panels', () => {
  beforeEach(() => {
    localStorage.clear();
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1280 });
  });

  it('gives the library a visible default and restores it without remounting the draft', async () => {
    render(<IdeasPage />);
    await screen.findByLabelText('Draft');
    const draft = screen.getByLabelText('Draft');
    fireEvent.change(draft, { target: { value: 'Unsaved words' } });
    expect(screen.getByText('Library content')).toBeVisible();
    expect(screen.queryByLabelText('Workspace panels')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Collapse ideas', exact: true }));
    expect(screen.getByText('Library content')).not.toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Show ideas', exact: true }));
    expect(screen.getByText('Library content')).toBeVisible();
    expect(screen.getByLabelText('Draft')).toBe(draft);
    expect(draft).toHaveValue('Unsaved words');
  });

  it('opens related ideas on demand and restores panels after leaving focus mode', async () => {
    render(<IdeasPage />);
    await screen.findByLabelText('Draft');
    expect(screen.queryByText('Related content')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Show similar ideas' }));
    expect(screen.getByText('Related content')).toBeVisible();
    fireEvent.keyDown(window, { key: 'f', ctrlKey: true, shiftKey: true });
    expect(screen.getByText('Library content')).not.toBeVisible();
    expect(screen.queryByText('Related content')).not.toBeInTheDocument();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.getByText('Library content')).toBeVisible();
    expect(screen.getByText('Related content')).toBeVisible();
  });

  it('starts narrow screens with the note visible and the library closed', async () => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 390 });
    render(<IdeasPage />);
    await screen.findByLabelText('Draft');
    expect(screen.getByText('Library content')).not.toBeVisible();
    expect(screen.getByLabelText('Draft')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Show ideas', exact: true })).toHaveAttribute('aria-expanded', 'false');
  });

  it('honors a previously saved panel preference', async () => {
    localStorage.setItem('manifest:workspace-layout', JSON.stringify({ libraryCollapsed: true, contextCollapsed: false, focusMode: false }));
    render(<IdeasPage />);
    await screen.findByLabelText('Draft');
    expect(screen.getByText('Library content')).not.toBeVisible();
    expect(screen.getByText('Related content')).toBeVisible();
  });

  it('makes a new idea with ⌥⌘N', () => {
    render(<IdeasPage />);
    fireEvent.keyDown(window, { key: 'n', code: 'KeyN', altKey: true, ctrlKey: true });
    fireEvent.keyDown(window, { key: 'n', code: 'KeyN', altKey: true, metaKey: true });
    expect(mockCreateAndOpen).toHaveBeenCalledWith('keyboard_shortcut');
  });
});
