/**
 * Cloud sync for a local vault (ADR 0012): one set of ideas in the folder and in the
 * Manifest account, merged both ways.
 *
 * - The folder stays the working copy; the account is kept in step whenever the person is
 *   signed in and online.
 * - What changed since the last sync is known from a baseline per idea (content hash on
 *   this side, `updatedAt` on the account's), kept in `Manifest/.sync/<account>.json`.
 * - Changed on one side: that side's version goes to the other. Changed on both: the newer
 *   one wins and the other is saved in the vault's history, so nothing is lost.
 * - Deleted on one side and untouched on the other: deleted there too (the folder's copy
 *   goes to `Manifest/.trash`). Edited after the deletion: the edit wins and comes back.
 */
import { ROOT, serializeIdeaFile, type IdeaFile } from "./format";
import { htmlToMarkdown } from "./convert";
import type { VaultStore } from "./store";

export const SYNC_DIR = `${ROOT}/.sync`;

/** Document fields, as the vault names them and as the account saves them. */
export const DOCUMENT_TYPES: Record<string, string> = {
  businessModelCanvas: "business_model_canvas",
  pitchDeck: "pitch_deck",
  productRequirementsDocument: "product_requirements_document",
  provisionalPatent: "provisional_patent",
  similarIdeas: "similar_ideas",
};

export interface CloudIdea {
  id: string;
  title: string;
  html: string;
  skills: string[];
  createdAt: string | null;
  updatedAt: number; // ms
  documents: Record<string, string | null>;
}

/** The account, as sync needs it (GraphQL in the app, an in-memory fake in tests). */
export interface CloudApi {
  account(): Promise<{ userId: string; email: string | null } | null>;
  list(): Promise<{ id: string; updatedAt: number }[]>;
  get(id: string): Promise<CloudIdea | null>;
  create(title: string, html: string): Promise<string>;
  update(id: string, change: { title: string; html: string; skills: string[] }): Promise<void>;
  saveDocument(id: string, documentType: string, markdown: string): Promise<void>;
  remove(id: string): Promise<void>;
}

interface Baseline {
  cloudId: string;
  cloudUpdatedAt: number;
  hash: string;
}

interface SyncState {
  version: 1;
  account: { userId: string; email: string | null };
  lastSync: string | null;
  ideas: Record<string, Baseline>; // by the vault's manifest_id
}

export interface SyncReport {
  pushed: number;
  pulled: number;
  created: number;
  deleted: number;
  conflicts: number;
  errors: string[];
}

type Local = Awaited<ReturnType<VaultStore["snapshot"]>>[number];

/** FNV-1a: a short, stable fingerprint of an idea's content. */
function fingerprint(text: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(16).padStart(8, "0");
}

export function localHash(idea: Pick<Local, "title" | "body" | "skills" | "documents">): string {
  const docs = Object.keys(DOCUMENT_TYPES)
    .map((k) => `${k}:${(idea.documents[k] ?? "").trim()}`)
    .join("\n");
  return fingerprint([idea.title.trim(), idea.skills.join(","), idea.body.trim(), docs].join("\n\u0000"));
}

const stateFile = (userId: string) => `${SYNC_DIR}/${userId.replace(/[^\w-]/g, "_")}.json`;

export class VaultSync {
  constructor(
    private readonly store: VaultStore,
    private readonly cloud: CloudApi,
  ) {}

  private async loadState(account: SyncState["account"]): Promise<SyncState> {
    const text = await this.store.fs.read(stateFile(account.userId));
    try {
      const state = text ? (JSON.parse(text) as SyncState) : null;
      if (state?.version === 1) return { ...state, account };
    } catch {
      // A damaged state file: start over (a full merge, newest wins; nothing is lost).
    }
    return { version: 1, account, lastSync: null, ideas: {} };
  }

  private async saveState(state: SyncState) {
    await this.store.fs.write(stateFile(state.account.userId), `${JSON.stringify(state, null, 2)}\n`);
  }

  /** The account's copy, or a clear error when the account can't return it. */
  private async must(id: string, title: string): Promise<CloudIdea> {
    const cloud = await this.cloud.get(id);
    if (!cloud) throw new Error(`Couldn't read “${title}” from your account`);
    return cloud;
  }

  private async push(local: Local, cloudId: string, cloud: CloudIdea | null) {
    await this.cloud.update(cloudId, { title: local.title, html: local.html, skills: local.skills });
    for (const [field, type] of Object.entries(DOCUMENT_TYPES)) {
      const mine = local.documents[field]?.trim();
      if (mine && mine !== (cloud?.documents[field] ?? "").trim()) {
        await this.cloud.saveDocument(cloudId, type, local.documents[field]!);
      }
    }
  }

  private async pull(localId: string, cloud: CloudIdea, keep: "sync" | "conflict") {
    await this.store.writeIdea(
      localId,
      { title: cloud.title, html: cloud.html, skills: cloud.skills, documents: cloud.documents },
      keep,
    );
  }

  /** Keep the account's version in the vault's history before the vault's version replaces it. */
  private async keepCloudVersion(localId: string, cloud: CloudIdea) {
    const file: IdeaFile = {
      id: localId,
      title: cloud.title,
      created: cloud.createdAt,
      updated: new Date(cloud.updatedAt).toISOString(),
      published: false,
      skills: cloud.skills,
      body: htmlToMarkdown(cloud.html),
      extra: [],
      tail: "",
    };
    await this.store.history.save(localId, serializeIdeaFile(file), "conflict", "The account's older version");
  }

  private async baseline(localId: string, cloudId: string): Promise<Baseline> {
    const [local] = (await this.store.snapshot()).filter((i) => i.id === localId);
    const cloud = await this.cloud.get(cloudId);
    return { cloudId, cloudUpdatedAt: cloud?.updatedAt ?? Date.now(), hash: local ? localHash(local) : "" };
  }

  /** One full sync. Returns what happened; never throws for a single idea's failure. */
  async run(): Promise<SyncReport & { account: SyncState["account"] | null }> {
    const report: SyncReport = { pushed: 0, pulled: 0, created: 0, deleted: 0, conflicts: 0, errors: [] };
    const account = await this.cloud.account();
    if (!account) return { ...report, account: null };
    const state = await this.loadState(account);
    const cloudIndex = new Map((await this.cloud.list()).map((c) => [c.id, c.updatedAt]));
    const locals = await this.store.snapshot();
    const localIds = new Set(locals.map((l) => l.id));
    const claimed = new Set(Object.values(state.ideas).map((b) => b.cloudId));

    const attempt = async (what: string, step: () => Promise<void>) => {
      try {
        await step();
      } catch (error) {
        report.errors.push(`${what}: ${error instanceof Error ? error.message : String(error)}`);
      }
    };

    // 1. Ideas in the folder.
    for (const local of locals) {
      const base = state.ideas[local.id];
      const hash = localHash(local);
      await attempt(local.title, async () => {
        if (!base) {
          if (cloudIndex.has(local.id) && !claimed.has(local.id)) {
            // The same idea on both sides (copied earlier): newest wins.
            const cloud = await this.must(local.id, local.title);
            if (local.changedAt >= cloud.updatedAt) await this.push(local, local.id, cloud);
            else await this.pull(local.id, cloud, "sync");
            claimed.add(local.id);
            state.ideas[local.id] = await this.baseline(local.id, local.id);
            return;
          }
          const cloudId = await this.cloud.create(local.title, local.html);
          await this.push(local, cloudId, null);
          claimed.add(cloudId);
          report.created += 1;
          state.ideas[local.id] = await this.baseline(local.id, cloudId);
          return;
        }
        const cloudUpdated = cloudIndex.get(base.cloudId);
        const localChanged = hash !== base.hash;
        if (cloudUpdated === undefined) {
          // Deleted in the account.
          if (!localChanged) {
            await this.store.remove(local.id);
            delete state.ideas[local.id];
            report.deleted += 1;
          } else {
            const cloudId = await this.cloud.create(local.title, local.html);
            await this.push(local, cloudId, null);
            claimed.add(cloudId);
            state.ideas[local.id] = await this.baseline(local.id, cloudId);
            report.created += 1;
          }
          return;
        }
        const cloudChanged = cloudUpdated > base.cloudUpdatedAt;
        if (!localChanged && !cloudChanged) return;
        const cloud = await this.must(base.cloudId, local.title);
        if (localChanged && cloudChanged) {
          report.conflicts += 1;
          if (local.changedAt >= cloud.updatedAt) {
            await this.keepCloudVersion(local.id, cloud);
            await this.push(local, base.cloudId, cloud);
            report.pushed += 1;
          } else {
            await this.pull(local.id, cloud, "conflict");
            report.pulled += 1;
          }
        } else if (localChanged) {
          await this.push(local, base.cloudId, cloud);
          report.pushed += 1;
        } else {
          await this.pull(local.id, cloud, "sync");
          report.pulled += 1;
        }
        state.ideas[local.id] = await this.baseline(local.id, base.cloudId);
      });
    }

    // 2. Ideas synced before but gone from the folder: deleted here.
    for (const [localId, base] of Object.entries(state.ideas)) {
      if (localIds.has(localId)) continue;
      await attempt(localId, async () => {
        const cloudUpdated = cloudIndex.get(base.cloudId);
        if (cloudUpdated !== undefined && cloudUpdated > base.cloudUpdatedAt) {
          // Edited in the account after it was deleted here: the edit wins.
          const cloud = await this.must(base.cloudId, localId);
          await this.store.importIdea({
            id: localId,
            title: cloud.title,
            descriptionHtml: cloud.html,
            skills: cloud.skills,
            created: cloud.createdAt,
            documents: cloud.documents,
          });
          state.ideas[localId] = await this.baseline(localId, base.cloudId);
          report.pulled += 1;
          return;
        }
        if (cloudUpdated !== undefined) {
          await this.cloud.remove(base.cloudId);
          report.deleted += 1;
        }
        delete state.ideas[localId];
      });
    }

    // 3. Ideas only in the account: bring them into the folder.
    for (const id of cloudIndex.keys()) {
      if (claimed.has(id) || localIds.has(id)) continue;
      await attempt(id, async () => {
        const cloud = await this.cloud.get(id);
        if (!cloud) return;
        await this.store.importIdea({
          id,
          title: cloud.title,
          descriptionHtml: cloud.html,
          skills: cloud.skills,
          created: cloud.createdAt,
          documents: cloud.documents,
        });
        state.ideas[id] = await this.baseline(id, id);
        report.pulled += 1;
      });
    }

    state.lastSync = new Date().toISOString();
    await this.saveState(state);
    return { ...report, account };
  }

  async lastSync(userId: string): Promise<string | null> {
    const text = await this.store.fs.read(stateFile(userId));
    try {
      return text ? (JSON.parse(text) as SyncState).lastSync : null;
    } catch {
      return null;
    }
  }
}
