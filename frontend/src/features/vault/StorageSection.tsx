import React, { useEffect, useState } from "react";
import { useApolloClient } from "@apollo/client/react";
import { openMediaSignInUrl } from "features/auth/openMediaSignIn";
import {
  chooseVaultFolder,
  isVaultMode,
  loadVaultHandle,
  switchToCloudStorage,
  vaultSupported,
} from "./mode";
import type { SyncStatus } from "./cloudSync";
import {
  friendlyPath,
  getComputerVault,
  localNetworkGranted,
  moveComputerVault,
  setComputerVaultOnDelete,
  type ComputerVault,
  type OnDelete,
} from "./computerFolder";
import { BRIDGE_INSTALL_COMMAND } from "features/voice/localAgent";

/**
 * Settings → Storage (ADR 0011, 0012): keep ideas in a folder on this computer (synced by
 * iCloud Drive or any folder sync), in the Manifest account, or both: a vault that also
 * syncs with the account.
 */

const when = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "never";

const SYNC_LABELS: Record<SyncStatus["state"], string> = {
  off: "Sync is off",
  "signed-out": "Not signed in",
  offline: "Offline: syncs when you're back online",
  syncing: "Syncing…",
  synced: "In sync",
  error: "Last sync had a problem",
};

/** Vault + account sync controls (vault mode only). */
const CloudSyncPanel: React.FC = () => {
  const app = useApolloClient();
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [account, setAccount] = useState<{ userId: string; email: string | null } | null | undefined>(undefined);
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    let stop = () => undefined as void;
    void import("./cloudSync").then(({ onSyncStatus, cloudSyncEnabled, graphqlCloud }) => {
      setEnabled(cloudSyncEnabled());
      stop = onSyncStatus(setStatus);
      void graphqlCloud().account().then(setAccount);
    });
    return () => stop();
  }, []);

  const run = async () => {
    const [{ syncNow }, { vaultStore }] = await Promise.all([import("./cloudSync"), import("./runtime")]);
    await syncNow(await vaultStore(), app);
  };
  const turn = async (on: boolean) => {
    const { setCloudSyncEnabled } = await import("./cloudSync");
    setCloudSyncEnabled(on);
    setEnabled(on);
    if (on) await run();
  };
  const signIn = async () => {
    const { setCloudSyncEnabled } = await import("./cloudSync");
    setCloudSyncEnabled(true); // start syncing as soon as they're back
    window.location.assign(openMediaSignInUrl("/account#storage"));
  };

  const report = status?.report;
  return (
    <div className="manifest-sync-panel" aria-labelledby="sync-title">
      <h3 id="sync-title">Sync with your Manifest account</h3>
      {account === undefined ? (
        <p>Checking your account…</p>
      ) : !account ? (
        <>
          <p>
            Sign in to keep this vault and your account in step: ideas from both are combined, and
            edits go both ways. Sharing and collaboration use the account copy.
          </p>
          <button type="button" className="manifest-vault-primary" onClick={signIn}>
            Sign in to sync
          </button>
        </>
      ) : !enabled ? (
        <>
          <p>
            Signed in as <strong>{account.email ?? "your account"}</strong>. Turning sync on combines the
            ideas in this folder with the ones in your account. If the same idea changed in both
            places, the newest version wins and the other is kept in its version history.
          </p>
          <button type="button" className="manifest-vault-primary" onClick={() => void turn(true)}>
            Turn on sync
          </button>
        </>
      ) : (
        <>
          <p className="manifest-sync-state" role="status">
            <span data-state={status?.state ?? "synced"} aria-hidden="true" />
            {SYNC_LABELS[status?.state ?? "synced"]} · {account.email ?? "your account"} · last synced{" "}
            {when(status?.lastSync ?? null)}
          </p>
          {report && (report.pushed || report.pulled || report.created || report.deleted || report.conflicts) ? (
            <p className="manifest-sync-report">
              Last time: {report.pushed} sent, {report.pulled} received, {report.created} new in your account,{" "}
              {report.deleted} removed, {report.conflicts} resolved by keeping the newer version.
            </p>
          ) : null}
          {status?.message ? (
            <p className="manifest-sync-error" role="alert">
              {status.message}
            </p>
          ) : null}
          <div className="mt-4 flex flex-wrap gap-3">
            <button type="button" className="manifest-vault-primary" onClick={() => void run()}>
              Sync now
            </button>
            <button type="button" className="manifest-vault-secondary" onClick={() => void turn(false)}>
              Turn off sync
            </button>
          </div>
        </>
      )}
    </div>
  );
};

/**
 * The vault folder on this computer (background sync, agents, voice), through `manifest
 * bridge`. Moving it keeps every file; voice can do the same ("move my vault to iCloud").
 */
export const ComputerVaultPanel: React.FC = () => {
  const [vault, setVault] = useState<ComputerVault | null | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  const [custom, setCustom] = useState("");

  const look = async () => {
    setVault(undefined);
    setVault(await getComputerVault());
  };

  useEffect(() => {
    // Look only when Chrome already lets Manifest reach this computer (voice asked before);
    // otherwise wait for a click, so opening Settings never raises a permission prompt.
    void localNetworkGranted().then((granted) => (granted ? look() : setVault(null)));
  }, []);

  const move = async (place: string) => {
    setBusy(true);
    setMessage(null);
    try {
      const result = await moveComputerVault(place);
      const next = await getComputerVault();
      setVault(next);
      const where = next ? friendlyPath(result.folder, next.places) : result.folder;
      setMessage({
        tone: "ok",
        text: `${result.moved ? "Moved your vault to" : "Your vault is in"} ${where}.${result.warning ? ` ${result.warning}` : ""}`,
      });
      setCustom("");
    } catch (error) {
      setMessage({ tone: "error", text: error instanceof Error ? error.message : "Couldn't move the vault." });
    } finally {
      setBusy(false);
    }
  };

  const chooseOnDelete = async (onDelete: OnDelete) => {
    setBusy(true);
    setMessage(null);
    try {
      setVault(await setComputerVaultOnDelete(onDelete));
      setMessage({
        tone: "ok",
        text:
          onDelete === "delete"
            ? "Notes you delete in Manifest are deleted from this vault too."
            : "Notes you delete in Manifest stay in this vault as your copies.",
      });
    } catch (error) {
      setMessage({ tone: "error", text: error instanceof Error ? error.message : "Couldn't change that." });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="manifest-sync-panel" aria-labelledby="computer-vault-title">
      <h3 id="computer-vault-title">Vault folder on this computer</h3>
      {vault === undefined ? (
        <p>Looking for your vault…</p>
      ) : vault === null ? (
        <>
          <p>
            Your agents, voice and background sync keep a vault folder on this computer. To see or move it from
            here, run <code>{BRIDGE_INSTALL_COMMAND}</code> once, then look again. You can also just ask voice:
            “move my vault to iCloud Drive”.
          </p>
          <button type="button" className="manifest-vault-secondary" onClick={() => void look()}>
            Find my vault folder
          </button>
        </>
      ) : (
        <>
          <p className="manifest-sync-state">
            <strong>{friendlyPath(vault.folder, vault.places)}</strong>
            {vault.icloud ? " · in iCloud Drive, on all your Apple devices" : ""}
            {vault.background_sync ? " · syncing in the background" : ""}
          </p>
          <div className="mt-4 flex flex-wrap gap-3">
            {!vault.icloud && vault.icloud_available ? (
              <button
                type="button"
                className="manifest-vault-primary"
                disabled={busy}
                onClick={() => void move("icloud")}
              >
                Move to iCloud Drive
              </button>
            ) : null}
            {vault.places.documents && !vault.folder.startsWith(`${vault.places.documents}/`) ? (
              <button
                type="button"
                className="manifest-vault-secondary"
                disabled={busy}
                onClick={() => void move("documents")}
              >
                Move to Documents
              </button>
            ) : null}
          </div>
          {vault.on_delete ? (
            <fieldset className="mt-4" disabled={busy}>
              <legend className="text-sm font-medium">When you delete a note in Manifest</legend>
              <label className="mt-2 flex items-start gap-2 text-sm">
                <input
                  type="radio"
                  name="vault-on-delete"
                  checked={vault.on_delete === "delete"}
                  onChange={() => void chooseOnDelete("delete")}
                />
                <span>
                  Delete it from this vault too <span className="text-gray500">(anything you wrote in it goes to the vault's .trash)</span>
                </span>
              </label>
              <label className="mt-1 flex items-start gap-2 text-sm">
                <input
                  type="radio"
                  name="vault-on-delete"
                  checked={vault.on_delete === "keep"}
                  onChange={() => void chooseOnDelete("keep")}
                />
                <span>Keep my copy in this vault</span>
              </label>
            </fieldset>
          ) : null}
          <form
            className="mt-4 flex flex-wrap gap-3"
            onSubmit={(event) => {
              event.preventDefault();
              if (custom.trim()) void move(custom.trim());
            }}
          >
            <label className="sr-only" htmlFor="vault-folder-path">
              Another folder
            </label>
            <input
              id="vault-folder-path"
              className="manifest-field min-w-0 flex-1"
              placeholder="Or another folder, e.g. ~/Dropbox/Notes"
              value={custom}
              disabled={busy}
              onChange={(event) => setCustom(event.target.value)}
            />
            <button type="submit" className="manifest-vault-secondary" disabled={busy || !custom.trim()}>
              {busy ? "Moving…" : "Move"}
            </button>
          </form>
          {message ? (
            <p
              className={message.tone === "error" ? "manifest-sync-error" : "manifest-sync-report"}
              role={message.tone === "error" ? "alert" : "status"}
            >
              {message.text}
            </p>
          ) : null}
        </>
      )}
    </div>
  );
};

export const StorageSection: React.FC = () => {
  const vault = isVaultMode();
  const supported = vaultSupported();
  const [folder, setFolder] = useState<string | null>(null);

  useEffect(() => {
    if (vault) void loadVaultHandle().then((h) => setFolder(h?.name ?? null));
  }, [vault]);

  const openFolder = async () => {
    if (await chooseVaultFolder()) window.location.assign("/ideas");
  };

  /** From the account: use a folder and keep it in sync with the account. */
  const openVaultWithSync = async () => {
    if (!(await chooseVaultFolder())) return;
    const { setCloudSyncEnabled } = await import("./cloudSync");
    setCloudSyncEnabled(true);
    window.location.assign("/ideas");
  };

  const accountOnly = async () => {
    const { setCloudSyncEnabled } = await import("./cloudSync");
    setCloudSyncEnabled(false);
    switchToCloudStorage();
    window.location.assign("/ideas");
  };

  return (
    <section id="storage" className="manifest-panel manifest-storage p-4 sm:p-5" aria-labelledby="storage-title">
      <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">Storage</p>
      <h2 id="storage-title" className="mt-3 text-[1.35rem] font-semibold tracking-[-0.03em] text-neutral900 dark:text-white">
        {vault ? `Your vault: ${folder ?? "a folder on this computer"}` : "Your ideas are in your Manifest account"}
      </h2>
      <p className="mt-2 text-sm leading-6 text-gray500 dark:text-gray400">
        {vault
          ? "Every idea is a Markdown file in this folder and works offline. Put the folder in iCloud Drive, Dropbox or OneDrive to have it on all your computers; open it in Obsidian or any editor too. Every idea keeps a version history in the folder."
          : supported
            ? "You can also keep your ideas as Markdown files in a folder, for example in iCloud Drive. They work offline, and the folder keeps syncing with your account."
            : "This browser can't open folders on your computer, so your ideas stay in your Manifest account. To keep them in a folder (for example in iCloud Drive), use Chrome, Edge, Arc or Brave on a computer."}
      </p>

      {vault ? <CloudSyncPanel /> : null}
      <ComputerVaultPanel />

      <div className="mt-5 flex flex-wrap gap-3">
        {vault ? (
          <>
            <button type="button" className="manifest-vault-secondary" onClick={openFolder}>
              Choose another folder…
            </button>
            <button type="button" className="manifest-vault-link" onClick={() => void accountOnly()}>
              Use only my account (no folder)
            </button>
          </>
        ) : supported ? (
          <button type="button" className="manifest-vault-primary" onClick={() => void openVaultWithSync()}>
            Use a vault folder…
          </button>
        ) : null}
      </div>
    </section>
  );
};

/** Settings while the ideas live in a folder: storage and sync. */
export const VaultSettingsPage: React.FC = () => (
  <div className="manifest-page">
    <div className="mx-auto w-full max-w-3xl px-4 py-8">
      <h1 className="manifest-page-title">Settings</h1>
      <div className="mt-6 space-y-6">
        <StorageSection />
      </div>
    </div>
  </div>
);

export default VaultSettingsPage;
