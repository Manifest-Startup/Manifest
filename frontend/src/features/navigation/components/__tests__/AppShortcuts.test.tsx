import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import AppShortcuts from '../AppShortcuts';

const renderAt = (signedIn = true) =>
  render(
    <MemoryRouter initialEntries={['/pitch-reels']}>
      <AppShortcuts signedIn={signedIn} />
      <Routes>
        <Route path="/pitch-reels" element={<p>Reels</p>} />
        <Route path="/account" element={<p>Account page</p>} />
      </Routes>
    </MemoryRouter>,
  );

describe('AppShortcuts', () => {
  it('opens the shortcuts sheet with ⌘/ or ? on any page, and Esc closes it', async () => {
    renderAt();
    fireEvent.keyDown(window, { key: '/', ctrlKey: true, metaKey: true }); // ⌘ and Ctrl both held: ignored
    fireEvent.keyDown(window, { key: '?' });
    expect(await screen.findByRole('dialog', { name: 'Keyboard shortcuts' }, { timeout: 10000 })).toBeInTheDocument();
    expect(screen.getByText('Talk to Manifest (voice)')).toBeInTheDocument();
    expect(screen.getByText('Dictate into the note (Esc stops)')).toBeInTheDocument();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: 'Keyboard shortcuts' })).toBeNull();
  });

  it('opens account settings with the platform settings shortcut when signed in', () => {
    renderAt();
    fireEvent.keyDown(window, { key: ',', ctrlKey: true });
    fireEvent.keyDown(window, { key: ',', metaKey: true });
    expect(screen.getByText('Account page')).toBeInTheDocument();
  });

  it('leaves the settings shortcut alone when signed out', () => {
    renderAt(false);
    fireEvent.keyDown(window, { key: ',', ctrlKey: true });
    fireEvent.keyDown(window, { key: ',', metaKey: true });
    expect(screen.getByText('Reels')).toBeInTheDocument();
  });
});
