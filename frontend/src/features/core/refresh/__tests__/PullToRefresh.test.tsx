import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';

const mockRefetch = jest.fn().mockResolvedValue([]);
jest.mock('@apollo/client/react', () => ({ useApolloClient: () => ({ refetchQueries: mockRefetch }) }));
const mockSync = jest.fn().mockResolvedValue({ ok: true });
let mockGranted = true;
jest.mock('features/vault/computerFolder', () => ({
  localNetworkGranted: async () => mockGranted,
  syncComputerVault: () => mockSync(),
}));
jest.mock('features/vault/cloudSync', () => ({ SYNC_NOW_EVENT: 'manifest:vault-sync-now' }));

import { PullToRefresh, atTop, refreshEverything } from '../PullToRefresh';

const touch = (type: string, y: number) =>
  fireEvent[type as 'touchStart'](document.body, { touches: [{ clientY: y }] });

describe('pull to refresh', () => {
  beforeEach(() => {
    mockRefetch.mockClear();
    mockSync.mockClear();
    mockGranted = true;
  });

  it('syncs the vault, this computer and every query on screen', async () => {
    const synced = jest.fn();
    window.addEventListener('manifest:vault-sync-now', synced);
    await refreshEverything({ refetchQueries: mockRefetch } as never);
    expect(synced).toHaveBeenCalled();
    expect(mockSync).toHaveBeenCalled();
    expect(mockRefetch).toHaveBeenCalledWith({ include: 'active' });
  });

  it('never asks to reach this computer when the browser has not allowed it', async () => {
    mockGranted = false;
    await refreshEverything({ refetchQueries: mockRefetch } as never);
    expect(mockSync).not.toHaveBeenCalled();
    expect(mockRefetch).toHaveBeenCalled();
  });

  it('a long pull from the top syncs; a short one does nothing', async () => {
    render(<PullToRefresh />);
    touch('touchStart', 100);
    touch('touchMove', 140);
    expect(screen.getByRole('status')).toHaveTextContent('Pull to sync');
    await act(async () => {
      fireEvent.touchEnd(document.body);
    });
    expect(mockRefetch).not.toHaveBeenCalled();

    touch('touchStart', 100);
    touch('touchMove', 260);
    expect(screen.getByRole('status')).toHaveTextContent('Release to sync');
    await act(async () => {
      fireEvent.touchEnd(document.body);
    });
    await waitFor(() => expect(mockRefetch).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Up to date'));
  });

  it('only counts as a pull when nothing is scrolled down', () => {
    const list = document.createElement('div');
    list.style.overflowY = 'auto';
    const item = document.createElement('p');
    list.appendChild(item);
    document.body.appendChild(list);
    expect(atTop(item)).toBe(true);
    list.scrollTop = 40;
    Object.defineProperty(list, 'scrollTop', { value: 40, configurable: true });
    expect(atTop(item)).toBe(false);
  });
});
