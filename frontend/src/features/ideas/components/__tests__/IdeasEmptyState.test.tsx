import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import IdeasEmptyState from '../IdeasEmptyState';

const mockCreateAndOpen = jest.fn();
jest.mock('features/ideas/hooks/useCreateIdea', () => ({
  useCreateIdea: () => ({ createIdea: jest.fn(), createAndOpen: mockCreateAndOpen }),
}));

describe('IdeasEmptyState', () => {
  it('invites the user to pick an idea or start a new one', async () => {
    mockCreateAndOpen.mockResolvedValue('new-id');
    render(<IdeasEmptyState />);
    expect(screen.getByRole('heading', { name: 'Select an idea' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /new idea/i }));
    await waitFor(() => expect(mockCreateAndOpen).toHaveBeenCalledWith('empty_workspace'));
  });
});
