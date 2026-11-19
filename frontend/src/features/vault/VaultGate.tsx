import React, { useCallback, useEffect, useState } from "react";
import {
  chooseVaultFolder,
  isVaultMode,
  loadVaultHandle,
  switchToCloudStorage,
  vaultPermission,
} from "./mode";
import type { ApolloClient } from "@apollo/client";

type State = { kind: "checking" } | { kind: "ready" } | { kind: "allow"; name: string } | { kind: "missing" };

/**
 * In vault mode, the app waits until the browser may read the vault folder again: after a
 * restart, Chrome asks for one click before a site can reopen a folder. Cloud mode renders
 * straight through.
 */
export const VaultGate: React.FC<{ client: ApolloClient; children: React.ReactNode }> = ({ client, children }) => {
  const vault = isVaultMode();
  const [state, setState] = useState<State>(vault ? { kind: "checking" } : { kind: "ready" });

  const start = useCallback(() => {
    setState({ kind: "ready" });
    void import("./runtime").then(({ watchVault }) => watchVault(client));
    // Opens without a connection next time (app files only; the ideas are in the folder).
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/vault-sw.js").catch(() => undefined);
    }
  }, [client]);

  useEffect(() => {
    if (!vault) return;
    let alive = true;
    void (async () => {
      const handle = await loadVaultHandle();
      if (!alive) return;
      if (!handle) return setState({ kind: "missing" });
      const permission = await vaultPermission(handle);
      if (!alive) return;
      if (permission === "granted") start();
      else setState({ kind: "allow", name: handle.name });
    })();
    return () => {
      alive = false;
    };
  }, [vault, start]);

  if (state.kind === "ready") return <>{children}</>;
  if (state.kind === "checking") return null;

  const allow = async () => {
    const handle = await loadVaultHandle();
    if (handle && (await vaultPermission(handle, true)) === "granted") start();
  };
  const choose = async () => {
    if (await chooseVaultFolder()) window.location.reload();
  };
  const cloud = () => {
    switchToCloudStorage();
    window.location.reload();
  };

  return (
    <main className="manifest-vault-gate" aria-labelledby="vault-gate-title">
      <div>
        <p className="manifest-vault-gate__eyebrow">Your vault</p>
        <h1 id="vault-gate-title">
          {state.kind === "allow" ? `Open “${state.name}”` : "Choose your vault folder"}
        </h1>
        <p>
          {state.kind === "allow"
            ? "Your ideas are Markdown files in this folder. Allow Manifest to open it again in this browser."
            : "This browser no longer remembers your vault folder. Pick it again; nothing in it has changed."}
        </p>
        <div className="manifest-vault-gate__actions">
          <button type="button" className="manifest-vault-primary" onClick={state.kind === "allow" ? allow : choose}>
            {state.kind === "allow" ? "Open vault" : "Choose folder…"}
          </button>
          <button type="button" className="manifest-vault-link" onClick={cloud}>
            Use my Manifest account instead
          </button>
        </div>
      </div>
    </main>
  );
};

export default VaultGate;
