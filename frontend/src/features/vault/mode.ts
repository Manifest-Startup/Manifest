/**
 * Where this browser keeps the person's ideas (ADR 0011): in a Manifest account ("cloud",
 * the default and the only choice in Safari and Firefox) or in a folder on this computer
 * ("vault"; Chrome, Edge, Arc and Brave on desktop, which can open folders).
 *
 * Small on purpose: it's in the boot path. The vault itself loads only in vault mode.
 */

export type StorageMode = "cloud" | "vault";

const MODE_KEY = "manifest.storage.v1";
const DB_NAME = "manifest-vault";
const STORE = "handles";
const ROOT_KEY = "root";

type DirectoryPicker = (options?: { id?: string; mode?: "read" | "readwrite"; startIn?: string }) => Promise<FileSystemDirectoryHandle>;
type PermissionHandle = FileSystemDirectoryHandle & {
  queryPermission?: (d: { mode: "readwrite" }) => Promise<PermissionState>;
  requestPermission?: (d: { mode: "readwrite" }) => Promise<PermissionState>;
};

/** This browser can open a folder on the computer (File System Access API). */
export function vaultSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    window.isSecureContext &&
    typeof (window as unknown as { showDirectoryPicker?: unknown }).showDirectoryPicker === "function"
  );
}

export function storageMode(): StorageMode {
  try {
    return vaultSupported() && window.localStorage.getItem(MODE_KEY) === "vault" ? "vault" : "cloud";
  } catch {
    return "cloud";
  }
}

export const isVaultMode = () => storageMode() === "vault";

export function setStorageMode(mode: StorageMode): void {
  try {
    window.localStorage.setItem(MODE_KEY, mode);
  } catch {
    // Without storage the app stays in cloud mode.
  }
}

// -- the folder handle, kept in IndexedDB (handles can't go in localStorage) ------------

function db(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function tx<T>(mode: IDBTransactionMode, run: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const database = await db();
  return new Promise((resolve, reject) => {
    const request = run(database.transaction(STORE, mode).objectStore(STORE));
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export async function loadVaultHandle(): Promise<FileSystemDirectoryHandle | null> {
  try {
    return ((await tx("readonly", (s) => s.get(ROOT_KEY))) as FileSystemDirectoryHandle | undefined) ?? null;
  } catch {
    return null;
  }
}

async function saveVaultHandle(handle: FileSystemDirectoryHandle): Promise<void> {
  await tx("readwrite", (s) => s.put(handle, ROOT_KEY));
}

/** "granted", "prompt" (needs a click to allow again) or "denied". */
export async function vaultPermission(
  handle: FileSystemDirectoryHandle,
  ask = false,
): Promise<PermissionState> {
  const h = handle as PermissionHandle;
  const query = ask ? h.requestPermission : h.queryPermission;
  return query ? query.call(h, { mode: "readwrite" }) : "granted";
}

/**
 * Ask the person to pick a vault folder (a click must start this), remember it and switch
 * this browser to vault mode (unless `activate: false`, e.g. while copying an account into
 * it). Returns the folder's name, or null if they cancelled.
 */
export async function chooseVaultFolder({ activate = true } = {}): Promise<string | null> {
  const picker = (window as unknown as { showDirectoryPicker?: DirectoryPicker }).showDirectoryPicker;
  if (!picker) return null;
  try {
    const handle = await picker({ id: "manifest-vault", mode: "readwrite", startIn: "documents" });
    await saveVaultHandle(handle);
    if (activate) setStorageMode("vault");
    return handle.name;
  } catch {
    return null; // cancelled
  }
}

/** Back to the Manifest account (the folder and its files stay as they are). */
export function switchToCloudStorage(): void {
  setStorageMode("cloud");
  // The account needs the network anyway: drop the vault's offline shell.
  void navigator.serviceWorker?.getRegistrations?.().then((registrations) =>
    registrations
      .filter((r) => r.active?.scriptURL.endsWith("/vault-sw.js"))
      .forEach((r) => void r.unregister()),
  );
}
