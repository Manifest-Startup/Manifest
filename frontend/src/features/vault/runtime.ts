/**
 * The vault in this tab (ADR 0011): one store over the chosen folder, the Apollo link that
 * answers GraphQL from it, and a light watch that notices files changed elsewhere (another
 * computer through iCloud Drive, Obsidian, a text editor) and refreshes what's on screen.
 *
 * Loaded lazily, only in vault mode.
 */
import type { ApolloClient, ApolloLink } from "@apollo/client";
import { BrowserVaultFs } from "./fs";
import { executeOnVault } from "./execute";
import { loadVaultHandle, vaultPermission } from "./mode";
import { VaultStore } from "./store";

let store: Promise<VaultStore> | null = null;

export class VaultLockedError extends Error {
  constructor() {
    super("Allow Manifest to open your vault folder again.");
  }
}

export function vaultStore(): Promise<VaultStore> {
  if (!store) {
    store = (async () => {
      const handle = await loadVaultHandle();
      if (!handle || (await vaultPermission(handle)) !== "granted") {
        store = null;
        throw new VaultLockedError();
      }
      return new VaultStore(new BrowserVaultFs(handle));
    })();
  }
  return store;
}

export async function runOperation(operation: ApolloLink.Operation) {
  const vault = await vaultStore();
  return executeOnVault(vault, operation.query, operation.variables ?? {}, operation.operationName);
}

const WATCH_MS = 4000;
let watching = false;

/** Re-read the folder every few seconds while the tab is visible; refetch on changes. */
export function watchVault(client: ApolloClient): () => void {
  if (watching) return () => undefined;
  watching = true;
  let busy = false;
  const tick = async () => {
    if (busy || document.visibilityState !== "visible") return;
    busy = true;
    try {
      const vault = await vaultStore();
      if (await vault.refresh()) await client.refetchQueries({ include: "active" });
    } catch {
      // Locked or unavailable for a moment (e.g. iCloud still downloading): try again later.
    } finally {
      busy = false;
    }
  };
  const timer = window.setInterval(tick, WATCH_MS);
  document.addEventListener("visibilitychange", tick);
  return () => {
    watching = false;
    window.clearInterval(timer);
    document.removeEventListener("visibilitychange", tick);
  };
}
