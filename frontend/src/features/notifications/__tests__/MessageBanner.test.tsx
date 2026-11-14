import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import MessageBanner from '../components/MessageBanner';
import * as MessageContext from '../context/MessageContext';

const mockClearMessage = jest.fn();

const renderWithMessage = (message: { text: string | null; type: 'error' | 'success' | 'info' }) => {
  jest.spyOn(MessageContext, 'useMessage').mockImplementation(() => ({
    message,
    clearMessage: mockClearMessage,
    setMessage: jest.fn(),
  }));
  return render(<MessageBanner />);
};

describe('MessageBanner', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders nothing if there is no message', () => {
    const { container } = renderWithMessage({ text: null, type: 'info' });
    expect(container.firstChild).toBeNull();
  });

  it('renders error message with correct style', () => {
    renderWithMessage({ text: 'Error occurred', type: 'error' });
    expect(screen.getByText('Error occurred')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveClass('bg-red-100');
    expect(screen.getByRole('button', { name: /dismiss/i })).toBeInTheDocument();
  });

  it('renders success message with correct style', () => {
    renderWithMessage({ text: 'Success!', type: 'success' });
    expect(screen.getByText('Success!')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveClass('bg-green-100');
    expect(screen.getByRole('button', { name: /dismiss/i })).toBeInTheDocument();
  });

  it('renders info message with correct style', () => {
    renderWithMessage({ text: 'Info message', type: 'info' });
    expect(screen.getByText('Info message')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveClass('bg-gray200');
    expect(screen.getByRole('button', { name: /dismiss/i })).toBeInTheDocument();
  });

  it('calls clearMessage when Dismiss is clicked', () => {
    renderWithMessage({ text: 'Dismiss me', type: 'info' });
    fireEvent.click(screen.getByRole('button', { name: /dismiss/i }));
    expect(mockClearMessage).toHaveBeenCalled();
  });
});
