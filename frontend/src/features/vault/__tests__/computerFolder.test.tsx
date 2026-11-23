import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { friendlyPath, getComputerVault, moveComputerVault } from '../computerFolder';
import { ComputerVaultPanel } from '../StorageSection';

const places = {
  icloud: '/Users/me/Library/Mobile Documents/com~apple~CloudDocs',
  documents: '/Users/me/Documents',
  home: '/Users/me',
};
const vault = (folder: string, icloud = false) => ({
  folder,
  source: 'setting',
  exists: true,
  icloud,
  icloud_available: true,
  background_sync: true,
  places,
});
const json = (body: unknown, ok = true) => ({ ok, json: async () => body });

describe("this computer's vault folder", () => {
  afterEach(() => jest.restoreAllMocks());

  it('names folders the way Finder does', () => {
    expect(friendlyPath(`${places.icloud}/Manifest Vault`, places)).toBe('iCloud Drive › Manifest Vault');
    expect(friendlyPath('/Users/me/Manifest Vault', places)).toBe('Home › Manifest Vault');
    expect(friendlyPath('/Volumes/x', places)).toBe('/Volumes/x');
  });

  it('asks the bridge, and passes its error through when a move fails', async () => {
    global.fetch = jest
      .fn()
      .mockResolvedValueOnce(json(vault('/Users/me/Manifest Vault')))
      .mockResolvedValueOnce(json({ error: "isn't empty" }, false)) as unknown as typeof fetch;
    expect((await getComputerVault())?.folder).toBe('/Users/me/Manifest Vault');
    await expect(moveComputerVault('icloud')).rejects.toThrow("isn't empty");
    global.fetch = jest.fn().mockRejectedValue(new TypeError('refused')) as unknown as typeof fetch;
    expect(await getComputerVault()).toBeNull();
  });

  it('moves the vault to iCloud Drive from Settings', async () => {
    Object.defineProperty(navigator, 'permissions', {
      configurable: true,
      value: { query: async () => ({ state: 'granted' }) },
    });
    const fetchMock = jest
      .fn()
      .mockResolvedValueOnce(json(vault('/Users/me/Manifest Vault')))
      .mockResolvedValueOnce(json({ folder: `${places.icloud}/Manifest Vault`, moved: true }))
      .mockResolvedValueOnce(json(vault(`${places.icloud}/Manifest Vault`, true)));
    global.fetch = fetchMock as unknown as typeof fetch;
    render(<ComputerVaultPanel />);
    const button = await screen.findByRole('button', { name: 'Move to iCloud Drive' });
    await act(async () => {
      fireEvent.click(button);
    });
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Moved your vault to iCloud Drive › Manifest Vault.'));
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ place: 'icloud' });
    expect(screen.queryByRole('button', { name: 'Move to iCloud Drive' })).toBeNull();
  });

  it('lets people choose whether notes deleted in Manifest leave this vault', async () => {
    Object.defineProperty(navigator, 'permissions', {
      configurable: true,
      value: { query: async () => ({ state: 'granted' }) },
    });
    const here = `${places.icloud}/Manifest Vault`;
    const fetchMock = jest
      .fn()
      .mockResolvedValueOnce(json({ ...vault(here, true), on_delete: 'delete' }))
      .mockResolvedValueOnce(json({ ...vault(here, true), on_delete: 'keep' }));
    global.fetch = fetchMock as unknown as typeof fetch;
    render(<ComputerVaultPanel />);
    const remove = await screen.findByRole('radio', { name: /Delete it from this vault too/ });
    expect(remove).toBeChecked();
    await act(async () => {
      fireEvent.click(screen.getByRole('radio', { name: 'Keep my copy in this vault' }));
    });
    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent('stay in this vault as your copies'),
    );
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ on_delete: 'keep' });
    expect(screen.getByRole('radio', { name: 'Keep my copy in this vault' })).toBeChecked();
  });
});
