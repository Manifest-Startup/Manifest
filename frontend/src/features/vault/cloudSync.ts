/**
 * Running vault ↔ account sync in the app (ADR 0012): the account side over GraphQL, the
 * on/off switch, a status people can see, and when to sync (after edits, every minute while
 * the app is open, and when the connection comes back).
 */
import type { ApolloClient } from "@apollo/client";
import {
  CREATE_IDEA,
  DELETE_IDEA,
  GET_PROFILE,
  SAVE_IDEA_DOCUMENT,
  UPDATE_IDEA,
  VAULT_SYNC_IDEA,
  VAULT_SYNC_IDEAS,
} from "features/core/apollo/queries";
import { createCloudClient } from "features/core/apollo/client";
import type { VaultStore } from "./store";
import { VaultSync, type CloudApi, type CloudIdea, type SyncReport } from "./sync";

const FLAG = "manifest.vaultSync.v1";
/** Fired when something changed the account directly (e.g. the voice agent): sync soon. */
export const SYNC_NOW_EVENT = "manifest:vault-sync-now";
const EVERY_MS = 60_000;
const AFTER_EDIT_MS = 4_000;

export function cloudSyncEnabled(): boolean {
  try {
    return window.localStorage.getItem(FLAG) === "on";
  } catch {
    return false;
  }
}

export function setCloudSyncEnabled(on: boolean): void {
  try {
    window.localStorage.setItem(FLAG, on ? "on" : "off");
  } catch {
    // Storage blocked: sync stays off.
  }
  window.dispatchEvent(new Event("manifest:vault-sync-setting"));
}

export interface SyncStatus {
  state: "off" | "signed-out" | "offline" | "syncing" | "synced" | "error";
  account: { userId: string; email: string | null } | null;
  lastSync: string | null;
  report: SyncReport | null;
  message: string | null;
}

let status: SyncStatus = { state: "off", account: null, lastSync: null, report: null, message: null };
const listeners = new Set<(s: SyncStatus) => void>();
const setStatus = (patch: Partial<SyncStatus>) => {
  status = { ...status, ...patch };
  listeners.forEach((l) => l(status));
};
export const syncStatus = () => status;
export function onSyncStatus(listener: (s: SyncStatus) => void): () => void {
  listeners.add(listener);
  listener(status);
  return () => listeners.delete(listener);
}

const time = (value: unknown) => (value ? Date.parse(String(value)) || 0 : 0);
const cursor = (createdAt: string, id: string) =>
  btoa(JSON.stringify({ c: createdAt, i: id })).replace(/\+/g, "-").replace(/\//g, "_");

/** The Manifest account over GraphQL. */
export function graphqlCloud(cloud: ApolloClient = createCloudClient()): CloudApi {
  return {
    async account() {
      try {
        const { data } = await cloud.query({ query: GET_PROFILE });
        const profile = (data as { profile?: { userId?: string; id?: string; email?: string; isGuest?: boolean } })?.profile;
        const userId = profile?.userId ?? profile?.id;
        return userId && !profile?.isGuest ? { userId, email: profile?.email ?? null } : null;
      } catch {
        return null;
      }
    },
    async list() {
      const out: { id: string; updatedAt: number }[] = [];
      let after: string | undefined;
      for (;;) {
        const { data } = await cloud.query({ query: VAULT_SYNC_IDEAS, variables: { first: 200, after } });
        const page = ((data as { ideas?: { ideaId: string; createdAt: string; updatedAt?: string }[] })?.ideas) ?? [];
        out.push(...page.map((i) => ({ id: i.ideaId, updatedAt: time(i.updatedAt ?? i.createdAt) })));
        if (page.length < 200) return out;
        const last = page[page.length - 1];
        after = cursor(last.createdAt, last.ideaId);
      }
    },
    async get(id) {
      try {
        const { data } = await cloud.query({ query: VAULT_SYNC_IDEA, variables: { ideaId: id } });
        const idea = (data as { idea?: Record<string, unknown> })?.idea;
        if (!idea) return null;
        const result: CloudIdea = {
          id,
          title: String(idea.title ?? ""),
          html: String(idea.description ?? ""),
          skills: (idea.requiredSkills as string[]) ?? [],
          createdAt: (idea.createdAt as string) ?? null,
          updatedAt: time(idea.updatedAt ?? idea.createdAt),
          documents: {
            businessModelCanvas: (idea.businessModelCanvas as string) ?? null,
            pitchDeck: (idea.pitchDeck as string) ?? null,
            productRequirementsDocument: (idea.productRequirementsDocument as string) ?? null,
            provisionalPatent: (idea.provisionalPatent as string) ?? null,
            similarIdeas: (idea.similarIdeas as string) ?? null,
          },
        };
        return result;
      } catch {
        return null;
      }
    },
    async create(title, html) {
      const { data } = await cloud.mutate({ mutation: CREATE_IDEA, variables: { title, description: html || null } });
      const id = data?.createIdea?.ideaId;
      if (!id) throw new Error("The account didn't create the idea.");
      return id;
    },
    async update(id, change) {
      await cloud.mutate({
        mutation: UPDATE_IDEA,
        variables: { ideaId: id, title: change.title, description: change.html || null, requiredSkills: change.skills },
      });
    },
    async saveDocument(id, documentType, markdown) {
      await cloud.mutate({ mutation: SAVE_IDEA_DOCUMENT, variables: { ideaId: id, documentType, content: markdown } });
    },
    async remove(id) {
      await cloud.mutate({ mutation: DELETE_IDEA, variables: { ideaId: id } });
    },
  };
}

let engine: VaultSync | null = null;
let running: Promise<void> | null = null;
let again = false;

/** Sync now (or right after the sync that's already running). */
export function syncNow(store: VaultStore, app: ApolloClient): Promise<void> {
  if (!cloudSyncEnabled()) {
    setStatus({ state: "off" });
    return Promise.resolve();
  }
  if (!navigator.onLine) {
    setStatus({ state: "offline" });
    return Promise.resolve();
  }
  if (running) {
    again = true;
    return running;
  }
  engine = engine ?? new VaultSync(store, graphqlCloud());
  running = (async () => {
    setStatus({ state: "syncing", message: null });
    try {
      const result = await engine!.run();
      if (!result.account) {
        setStatus({ state: "signed-out", account: null, report: null });
        return;
      }
      const { account, ...report } = result;
      setStatus({
        state: report.errors.length ? "error" : "synced",
        account,
        report,
        lastSync: new Date().toISOString(),
        message: report.errors[0] ?? null,
      });
      if (report.pulled || report.created || report.deleted || report.conflicts) {
        await app.refetchQueries({ include: "active" });
      }
    } catch (error) {
      setStatus({ state: "error", message: error instanceof Error ? error.message : String(error) });
    } finally {
      running = null;
      if (again) {
        again = false;
        void syncNow(store, app);
      }
    }
  })();
  return running;
}

/** Keep the vault and the account in step while this tab is open. */
export function startCloudSync(store: VaultStore, app: ApolloClient): () => void {
  let editTimer = 0;
  const tick = () => {
    if (document.visibilityState === "visible") void syncNow(store, app);
  };
  const afterEdit = () => {
    window.clearTimeout(editTimer);
    editTimer = window.setTimeout(tick, AFTER_EDIT_MS);
  };
  const stopEdits = store.onLocalChange(afterEdit);
  const timer = window.setInterval(tick, EVERY_MS);
  window.addEventListener("online", tick);
  window.addEventListener("manifest:vault-sync-setting", tick);
  window.addEventListener(SYNC_NOW_EVENT, tick);
  tick();
  return () => {
    stopEdits();
    window.clearInterval(timer);
    window.clearTimeout(editTimer);
    window.removeEventListener("online", tick);
    window.removeEventListener("manifest:vault-sync-setting", tick);
    window.removeEventListener(SYNC_NOW_EVENT, tick);
  };
}
