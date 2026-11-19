import React, { useState } from "react";
import { useApolloClient } from "@apollo/client/react";
import { GET_IDEA, GET_IDEAS } from "features/core/apollo/queries";
import {
  chooseVaultFolder,
  isVaultMode,
  loadVaultHandle,
  setStorageMode,
  switchToCloudStorage,
  vaultSupported,
} from "./mode";

/**
 * Settings → Storage (ADR 0011): keep ideas in a folder on this computer (synced by iCloud
 * Drive or any folder sync) or in the Manifest account, and move between the two.
 */
export const StorageSection: React.FC = () => {
  const client = useApolloClient();
  const vault = isVaultMode();
  const supported = vaultSupported();
  const [folder, setFolder] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  React.useEffect(() => {
    if (vault) void loadVaultHandle().then((h) => setFolder(h?.name ?? null));
  }, [vault]);

  const openFolder = async () => {
    setError(null);
    if (await chooseVaultFolder()) window.location.assign("/ideas");
  };

  /** Copy every idea and document from the account into a folder, then use that folder. */
  const copyToFolder = async () => {
    setError(null);
    // Pick the folder first (it needs this click), but keep reading from the account.
    const picked = await chooseVaultFolder({ activate: false });
    if (!picked) return;
    setBusy("Copying your ideas…");
    try {
      // Read from the account before this tab switches to the folder.
      const { data } = await client.query({ query: GET_IDEAS, fetchPolicy: "network-only" });
      const ideas = data?.ideas ?? [];
      const [{ BrowserVaultFs }, { VaultStore }] = await Promise.all([import("./fs"), import("./store")]);
      const handle = await loadVaultHandle();
      if (!handle) throw new Error("The folder wasn't saved. Try again.");
      const store = new VaultStore(new BrowserVaultFs(handle));
      let copied = 0;
      for (const [index, summary] of ideas.entries()) {
        setBusy(`Copying idea ${index + 1} of ${ideas.length}…`);
        const { data: full } = await client.query({
          query: GET_IDEA,
          variables: { ideaId: summary.ideaId },
          fetchPolicy: "network-only",
        });
        const idea = full?.idea;
        if (!idea) continue;
        const added = await store.importIdea({
          id: idea.ideaId,
          title: idea.title ?? "Untitled idea",
          descriptionHtml: idea.description ?? "",
          skills: idea.requiredSkills ?? [],
          created: summary.createdAt ?? null,
          documents: {
            businessModelCanvas: idea.businessModelCanvas,
            pitchDeck: idea.pitchDeck,
            productRequirementsDocument: idea.productRequirementsDocument,
            provisionalPatent: idea.provisionalPatent,
            similarIdeas: idea.similarIdeas,
          },
        });
        if (added) copied += 1;
      }
      setBusy(`Copied ${copied} idea${copied === 1 ? "" : "s"}. Opening your vault…`);
      setStorageMode("vault");
      window.location.assign("/ideas");
    } catch (failure) {
      setBusy(null); // still on the account: nothing switched
      setError(failure instanceof Error ? failure.message : "Copying didn't finish. Try again.");
    }
  };

  const switchToAccount = () => {
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
          ? "Every idea is a Markdown file in this folder and works offline. Put the folder in iCloud Drive, Dropbox or OneDrive to have it on all your computers; open it in Obsidian or any editor too."
          : supported
            ? "You can keep your ideas as Markdown files in a folder instead, for example in iCloud Drive. They work offline, and the folder syncs like any other."
            : "This browser can't open folders on your computer, so your ideas stay in your Manifest account. To keep them in a folder (for example in iCloud Drive), use Chrome, Edge, Arc or Brave on a computer."}
      </p>

      {vault ? (
        <ul className="manifest-storage-list">
          <li>Sharing, live collaboration, publishing, Pitch Reels and messages need Cloud sync.</li>
          <li>Deleted ideas go to the folder's Manifest/.trash, so nothing is lost.</li>
        </ul>
      ) : null}

      <div className="mt-5 flex flex-wrap gap-3">
        {vault ? (
          <>
            <button type="button" className="manifest-vault-secondary" onClick={openFolder}>
              Choose another folder…
            </button>
            <button type="button" className="manifest-vault-primary" onClick={switchToAccount}>
              Turn on Cloud sync
            </button>
          </>
        ) : supported ? (
          <>
            <button type="button" className="manifest-vault-primary" onClick={copyToFolder} disabled={Boolean(busy)}>
              Copy my ideas to a folder…
            </button>
            <button type="button" className="manifest-vault-secondary" onClick={openFolder} disabled={Boolean(busy)}>
              Open a folder without copying
            </button>
          </>
        ) : null}
      </div>
      {busy ? (
        <p className="mt-3 text-sm text-gray500 dark:text-gray400" role="status">
          {busy}
        </p>
      ) : null}
      {error ? (
        <p className="mt-3 text-sm text-red-600 dark:text-red-400" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
};

/** Settings while the ideas live in a folder: storage only (the rest needs an account). */
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
