/**
 * The vault folder on this computer: the one background sync, agents and voice use
 * (`manifest_vault.py`, saved in ~/.config/manifest/vault.json). A web page can't see or
 * move folders, so the app asks `manifest bridge` on 127.0.0.1, which runs
 * `manifest vault-folder` for it.
 */
import { bridgeUrl } from 'features/voice/localAgent';

export interface ComputerVault {
  folder: string;
  /** flag, env, setting (chosen with move) or default (~/Manifest Vault). */
  source: string;
  exists: boolean;
  icloud: boolean;
  icloud_available: boolean;
  background_sync: boolean;
  /** Named places this computer has: icloud, documents, home → their paths. */
  places: Record<string, string>;
  /** When a note is deleted in Manifest: delete it from this vault too, or keep a copy here. */
  on_delete?: OnDelete;
}

export type OnDelete = 'delete' | 'keep';

export interface MoveResult {
  folder: string;
  moved: boolean;
  warning?: string;
}

/** Chrome asks before a site may reach this computer; don't trigger that prompt unasked. */
export async function localNetworkGranted(): Promise<boolean> {
  try {
    const status = await navigator.permissions?.query({ name: 'local-network-access' as PermissionName });
    return status?.state === 'granted';
  } catch {
    return false; // unknown permission name: other browsers don't gate localhost
  }
}

async function call<T>(init?: RequestInit, timeoutMs = 20000, path = '/vault/folder'): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${bridgeUrl()}${path}`, { ...init, signal: controller.signal });
    const body = (await response.json().catch(() => ({}))) as T & { error?: string };
    if (!response.ok) throw new Error(body.error || "Couldn't reach the vault on this computer.");
    return body;
  } finally {
    clearTimeout(timer);
  }
}

/** This computer's vault, or null when the bridge isn't running (or is too old). */
export async function getComputerVault(): Promise<ComputerVault | null> {
  if (typeof fetch === 'undefined') return null;
  try {
    const vault = await call<ComputerVault>();
    return typeof vault.folder === 'string' ? vault : null;
  } catch {
    return null;
  }
}

/** Move the vault to a named place (icloud, documents, home) or a full path. Throws with a readable message. */
export function moveComputerVault(place: string): Promise<MoveResult> {
  return call<MoveResult>(
    {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ place }),
    },
    150000, // a big vault leaving iCloud can take a while
  );
}

/** Sync this computer's vault with the account now (background sync, through the bridge). */
export function syncComputerVault(): Promise<{ ok: boolean }> {
  return call<{ ok: boolean }>({ method: 'POST' }, 60000, '/vault/sync');
}

/** Choose what a note deleted in Manifest does in this computer's vault. */
export function setComputerVaultOnDelete(onDelete: OnDelete): Promise<ComputerVault> {
  return call<ComputerVault>({
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ on_delete: onDelete }),
  });
}

/** `/Users/me/Library/Mobile Documents/com~apple~CloudDocs/Manifest Vault` → `iCloud Drive › Manifest Vault`. */
export function friendlyPath(folder: string, places: Record<string, string>): string {
  const pairs: Array<[string, string | undefined]> = [
    ['iCloud Drive', places.icloud],
    ['Documents', places.documents],
    ['Home', places.home],
  ];
  for (const [label, base] of pairs) {
    if (base && (folder === base || folder.startsWith(`${base}/`))) {
      const rest = folder.slice(base.length).split('/').filter(Boolean);
      return [label, ...rest].join(' › ');
    }
  }
  return folder;
}
