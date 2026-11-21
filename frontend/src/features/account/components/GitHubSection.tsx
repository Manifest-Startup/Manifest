import React, { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@apollo/client/react";
import { useSearchParams } from "react-router-dom";

import Button from "features/common-ui/Button";
import Input from "features/common-ui/Input";
import {
  CONNECT_GITHUB,
  DISCONNECT_GITHUB,
  GET_GITHUB_ACCOUNT,
  GET_GITHUB_RECENT_REPOS,
  GET_INTEGRATIONS,
} from "features/core/apollo/queries";

export type GithubAccount = {
  connected: boolean;
  oauthAvailable: boolean;
  login?: string | null;
  name?: string | null;
  avatarUrl?: string | null;
  htmlUrl?: string | null;
  scopes: string[];
  method?: string | null;
  connectedAt?: string | null;
  message?: string | null;
};

type GithubRepo = {
  fullName: string;
  htmlUrl: string;
  private: boolean;
  description?: string | null;
  updatedAt?: string | null;
};

/** Opens GitHub's token page with full-control scopes filled in (Manifest still asks before anything destructive). */
export const GITHUB_TOKEN_URL =
  "https://github.com/settings/tokens/new?scopes=repo,workflow,read:org,delete_repo&description=Manifest";

const accountQueries = [{ query: GET_GITHUB_ACCOUNT }, { query: GET_INTEGRATIONS }];

/**
 * The one GitHub connection. It powers this page, repos created from ideas,
 * the `manifest` CLI, the agent plugin and voice. "Connect GitHub" uses Sign
 * in with GitHub when the deployment has it; otherwise its next step is a
 * token, verified with GitHub and stored encrypted (never shown again).
 * `manifest github connect` writes the same connection from a computer that
 * already has the GitHub CLI signed in.
 */
const GitHubSection: React.FC = () => {
  const [searchParams] = useSearchParams();
  const sectionRef = useRef<HTMLDivElement | null>(null);
  const focused = searchParams.get("focusIntegration")?.trim().toLowerCase() === "github";

  const { data, loading, refetch } = useQuery<{ githubAccount: GithubAccount }>(GET_GITHUB_ACCOUNT, {
    fetchPolicy: "cache-and-network",
  });
  const account = data?.githubAccount;
  const connected = Boolean(account?.connected);
  const { data: reposData } = useQuery<{ githubRepos: GithubRepo[] }>(GET_GITHUB_RECENT_REPOS, {
    variables: { limit: 5 },
    skip: !connected,
    errorPolicy: "all",
  });

  const options = { refetchQueries: accountQueries, errorPolicy: "all" as const };
  const [connectGithub, { loading: saving }] = useMutation<{ connectGithub: GithubAccount }>(CONNECT_GITHUB, options);
  const [disconnectGithub, { loading: removing }] = useMutation<{ disconnectGithub: GithubAccount }>(
    DISCONNECT_GITHUB,
    options,
  );

  const [tokenStep, setTokenStep] = useState(false);
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [waiting, setWaiting] = useState(false);

  useEffect(() => {
    if (focused) sectionRef.current?.scrollIntoView?.({ behavior: "smooth", block: "center" });
  }, [focused]);

  useEffect(() => {
    if (searchParams.get("provider") !== "github") return;
    const outcome = searchParams.get("oauth");
    if (outcome === "success") setNotice("GitHub is connected.");
    if (outcome === "error") setError("GitHub sign-in didn't finish. Try again.");
  }, [searchParams]);

  useEffect(() => {
    if (tokenStep) document.getElementById("github-token")?.focus();
  }, [tokenStep]);

  const clearMessages = () => {
    setError(null);
    setNotice(null);
  };

  const signInWithGitHub = async (): Promise<boolean> => {
    const response = await fetch("/auth/github/start", { credentials: "include" });
    const started = await response.json().catch(() => ({}));
    if (!response.ok || !started.auth_url) return false;
    const width = 600;
    const height = 760;
    const popup = window.open(
      started.auth_url,
      "oauth_github",
      `width=${width},height=${height},left=${window.screenX + (window.outerWidth - width) / 2},top=${window.screenY + (window.outerHeight - height) / 2}`,
    );
    if (!popup) {
      window.location.assign(started.auth_url);
      return true;
    }
    setWaiting(true);
    const finish = () => {
      window.removeEventListener("message", onMessage);
      window.clearInterval(watch);
      setWaiting(false);
      void refetch();
    };
    const onMessage = (event: MessageEvent) => {
      if (event.origin !== window.location.origin || event.data?.type !== "oauth_callback") return;
      if (event.data.status === "success") setNotice("GitHub is connected.");
      else setError(event.data.message || "GitHub sign-in didn't finish.");
      finish();
    };
    window.addEventListener("message", onMessage);
    const watch = window.setInterval(() => {
      if (popup.closed) finish();
    }, 500);
    return true;
  };

  /** The single connect action: Sign in with GitHub when available, else the token step. */
  const onConnect = async () => {
    clearMessages();
    if (account?.oauthAvailable) {
      try {
        if (await signInWithGitHub()) return;
      } catch {
        // fall through to the token step
      }
    }
    setTokenStep(true);
  };

  const onSaveToken = async (event: React.FormEvent) => {
    event.preventDefault();
    clearMessages();
    try {
      const result = await connectGithub({ variables: { token: token.trim() } });
      const saved = result?.data?.connectGithub;
      if (result?.error || !saved?.connected) {
        setError(result?.error?.message || "Could not connect GitHub. Try again.");
        return;
      }
      setToken("");
      setTokenStep(false);
      setNotice(`Connected as ${saved.login}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not connect GitHub. Try again.");
    }
  };

  const onDisconnect = async () => {
    clearMessages();
    const result = await disconnectGithub();
    if (result?.error) {
      setError(result.error.message);
      return;
    }
    setNotice("GitHub is disconnected everywhere in Manifest. Revoke the token on GitHub too if you no longer use it.");
  };

  const repos = reposData?.githubRepos ?? [];
  const missingScopes =
    connected && account?.scopes.length ? ["repo", "workflow"].filter((scope) => !account.scopes.includes(scope)) : [];

  return (
    <div ref={sectionRef} className="space-y-4" data-testid="github-section">
      <div className="flex items-center gap-3" aria-live="polite">
        {connected && account?.avatarUrl ? (
          <img src={account.avatarUrl} alt="" className="h-8 w-8 rounded-full" />
        ) : null}
        <p className="text-sm text-gray500 dark:text-gray400">
          {loading && !account
            ? "Checking GitHub…"
            : connected
              ? `Connected as @${account?.login}.`
              : "Not connected."}
        </p>
      </div>

      {connected ? (
        <>
          {missingScopes.length ? (
            <p className="text-xs text-amber-700 dark:text-amber-400">
              This connection can't use {missingScopes.join(" or ")}. Reconnect to give Manifest full access.
            </p>
          ) : null}
          {repos.length ? (
            <ul className="space-y-1 text-sm" aria-label="Recent repositories">
              {repos.map((repo) => (
                <li key={repo.fullName} className="flex items-center justify-between gap-3">
                  <a className="truncate underline" href={repo.htmlUrl} target="_blank" rel="noreferrer">
                    {repo.fullName}
                  </a>
                  <span className="shrink-0 text-xs text-gray500 dark:text-gray400">
                    {repo.private ? "Private" : "Public"}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
          <div className="flex flex-wrap items-center gap-3">
            {missingScopes.length ? (
              <Button type="button" onClick={onConnect} disabled={waiting}>
                Reconnect GitHub
              </Button>
            ) : null}
            {account?.htmlUrl ? (
              <a className="text-sm underline" href={account.htmlUrl} target="_blank" rel="noreferrer">
                Open GitHub
              </a>
            ) : null}
            <Button type="button" variant="secondary" onClick={onDisconnect} disabled={removing}>
              {removing ? "Disconnecting…" : "Disconnect"}
            </Button>
          </div>
        </>
      ) : !tokenStep ? (
        <Button type="button" onClick={onConnect} disabled={waiting || (loading && !account)}>
          {waiting ? "Waiting for GitHub…" : "Connect GitHub"}
        </Button>
      ) : null}

      {tokenStep ? (
        <form onSubmit={onSaveToken} className="space-y-3" aria-label="Connect GitHub">
          <p className="text-sm">
            <a className="underline" href={GITHUB_TOKEN_URL} target="_blank" rel="noreferrer">
              Create a token on GitHub
            </a>{" "}
            (the access Manifest needs is already filled in), then paste it here.
          </p>
          <Input
            id="github-token"
            name="githubToken"
            label="GitHub token"
            type="password"
            autoComplete="off"
            placeholder="ghp_... or github_pat_..."
            value={token}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setToken(e.target.value)}
          />
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" disabled={!token.trim() || saving}>
              {saving ? "Verifying…" : "Connect"}
            </Button>
            <Button type="button" variant="secondary" onClick={() => setTokenStep(false)}>
              Cancel
            </Button>
          </div>
        </form>
      ) : null}

      {!connected ? (
        <p className="text-xs text-gray500 dark:text-gray400">
          Signed in to GitHub on your computer already? <code>manifest github connect</code> links that login in one step.
        </p>
      ) : null}

      {error ? (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      ) : null}
      {notice ? <p className="text-sm text-green-700 dark:text-green-400">{notice}</p> : null}
    </div>
  );
};

export default GitHubSection;
