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
