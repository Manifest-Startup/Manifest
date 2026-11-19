/**
 * Live notes (ADR 0008): one shared Yjs document per idea note, synced through the
 * backend's authenticated Socket.IO server (`app/services/ideas/live_notes.py`).
 *
 * The server stamps every cursor with the sender's verified name, photo and colour,
 * so `peers` and the cursors in the editor always show who is really there.
 */
import { io, Socket } from "socket.io-client";
import * as Y from "yjs";
import {
  Awareness,
  applyAwarenessUpdate,
  encodeAwarenessUpdate,
  removeAwarenessStates,
} from "y-protocols/awareness";

export type LiveVia = "app" | "agent" | "cli";

export interface LivePeer {
  clientId: number;
  userId: string;
  name: string;
  avatarUrl: string | null;
  color: string;
  role: string;
  canEdit: boolean;
  via: LiveVia;
}

export interface LiveExternalEditor {
  userId: string;
  name: string;
  avatarUrl: string | null;
  color: string;
  via: LiveVia;
  viaLabel: string;
  until: number;
}

export interface LiveExternalEdit {
  ideaId: string;
  html: string;
  apply: boolean;
  by: LiveExternalEditor;
}

export type LiveStatus = "connecting" | "live" | "offline" | "denied";

export interface LiveSnapshot {
  status: LiveStatus;
  canEdit: boolean;
  /** The shared note has arrived (or been filled from the saved note); typing is safe. */
  ready: boolean;
  self: LivePeer | null;
  peers: LivePeer[];
  external: LiveExternalEditor[];
  error: string | null;
}

type Listener = (snapshot: LiveSnapshot) => void;

/** How the editor fills an empty room: fetch the saved note, then write it into the document. */
export interface LiveSeeder {
  load: () => Promise<string>;
  write: (html: string) => void;
}

/** If the first editor never fills the room, stop waiting and let people type. */
const READY_FALLBACK_MS = 3000;
type Ack = { ok: boolean; error?: string; [key: string]: unknown };

const SERVER = "server";
export const LIVE_NOTE_FIELD = "default";

const toBytes = (value: unknown): Uint8Array | null => {
  if (value instanceof Uint8Array) return value;
  if (value instanceof ArrayBuffer) return new Uint8Array(value);
  if (Array.isArray(value)) return Uint8Array.from(value as number[]);
  return null;
};

export class LiveNoteSession {
  readonly doc = new Y.Doc();
  readonly awareness = new Awareness(this.doc);
  readonly fragment = this.doc.getXmlFragment(LIVE_NOTE_FIELD);
  /** True while the editor writes the saved note into an empty room. */
  seeding = false;

  private socket: Socket;
  private listeners = new Set<Listener>();
  private externalListeners = new Set<(edit: LiveExternalEdit) => void>();
  private resetListeners = new Set<(html?: string) => void>();
  private seeder: LiveSeeder | null = null;
  private readyTimer: ReturnType<typeof setTimeout> | null = null;
  private seedPending = false;
  private destroyed = false;
  private snapshot: LiveSnapshot = {
    status: "connecting",
    canEdit: false,
    ready: false,
    self: null,
    peers: [],
    external: [],
    error: null,
  };

  constructor(readonly ideaId: string, socketFactory: () => Socket = defaultSocket) {
    this.socket = socketFactory();
    this.doc.on("update", this.onDocUpdate);
    this.awareness.on("update", this.onAwarenessUpdate);
    this.socket.on("connect", this.join);
    this.socket.on("disconnect", this.onDisconnect);
    this.socket.on("connect_error", this.onDisconnect);
    this.socket.on("note:update", this.onRemoteUpdate);
    this.socket.on("note:awareness", this.onRemoteAwareness);
    this.socket.on("note:left", this.onLeft);
    this.socket.on("note:peers", this.onPeers);
    this.socket.on("note:seed", this.onSeedRequest);
    this.socket.on("note:external", this.onExternal);
    this.socket.on("note:reset", this.onReset);
    if (this.socket.connected) this.join();
    else this.socket.connect();
  }

  // ---- subscriptions -----------------------------------------------------

  getSnapshot = (): LiveSnapshot => this.snapshot;

  subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  onExternalEdit(listener: (edit: LiveExternalEdit) => void): () => void {
    this.externalListeners.add(listener);
    return () => this.externalListeners.delete(listener);
  }

  /** The room must start again from the saved note (the hook makes a new session). */
  onResetRequired(listener: (html?: string) => void): () => void {
    this.resetListeners.add(listener);
    return () => this.resetListeners.delete(listener);
  }

  /**
   * The editor registers how to write the saved note into the shared document.
   * It runs once, only if this browser is the first editor in an empty room.
   */
  setSeeder(seeder: LiveSeeder | null): void {
    this.seeder = seeder;
    if (seeder && this.seedPending) void this.runSeed();
  }

  destroy(): void {
    if (this.destroyed) return;
    this.destroyed = true;
    if (this.readyTimer) clearTimeout(this.readyTimer);
    removeAwarenessStates(this.awareness, [this.doc.clientID], "local");
    this.socket.emit("note:leave", { ideaId: this.ideaId });
    this.socket.off("connect", this.join);
    this.socket.disconnect();
    this.awareness.destroy();
    this.doc.destroy();
    this.listeners.clear();
    this.externalListeners.clear();
    this.resetListeners.clear();
  }

  // ---- protocol ----------------------------------------------------------

  private set(patch: Partial<LiveSnapshot>) {
    this.snapshot = { ...this.snapshot, ...patch };
    this.listeners.forEach((listener) => listener(this.snapshot));
  }

  private join = () => {
    if (this.destroyed) return;
    this.set({ status: "connecting" });
    this.socket.emit(
      "note:join",
      {
        ideaId: this.ideaId,
        clientId: this.doc.clientID,
        stateVector: Y.encodeStateVector(this.doc),
      },
      (ack: Ack) => {
        if (this.destroyed) return;
        if (!ack?.ok) {
          this.set({ status: "denied", error: ack?.error || "Live editing is unavailable" });
          return;
        }
        const update = toBytes(ack.update);
        if (update && update.length > 2) Y.applyUpdate(this.doc, update, SERVER);
        this.set({
          status: "live",
          error: null,
          canEdit: Boolean(ack.canEdit),
          self: (ack.self as LivePeer) || null,
          peers: (ack.peers as LivePeer[]) || [],
          external: (ack.external as LiveExternalEditor[]) || [],
        });
        if (ack.seed && this.fragment.length === 0) {
          this.seedPending = true;
          if (this.seeder) void this.runSeed();
        } else {
          if (ack.seeded || this.fragment.length > 0) this.markReady();
          else this.readyTimer = setTimeout(() => this.markReady(), READY_FALLBACK_MS);
          // Send what the server is missing (e.g. after the server restarted).
          const serverState = toBytes(ack.stateVector);
          const diff = Y.encodeStateAsUpdate(this.doc, serverState || undefined);
          if (diff.length > 2 && this.snapshot.canEdit) this.sendUpdate(diff, false);
        }
        this.awareness.setLocalState(this.awareness.getLocalState() || {});
      }
    );
  };

  private markReady() {
    if (this.readyTimer) clearTimeout(this.readyTimer);
    this.readyTimer = null;
    if (!this.snapshot.ready && !this.destroyed) this.set({ ready: true });
  }

  private async runSeed() {
    const seeder = this.seeder;
    if (!seeder || !this.seedPending) return;
    this.seedPending = false;
    let html = "";
    try {
      html = await seeder.load(); // the saved note, fresh from the server
    } catch {
      html = "";
    }
    // Someone else's copy may have arrived while we were loading.
    if (!this.destroyed && this.fragment.length === 0 && html) {
      this.seeding = true;
      try {
        seeder.write(html);
      } finally {
        this.seeding = false;
      }
    }
    this.markReady();
  }

  private sendUpdate(update: Uint8Array, seed: boolean) {
    this.socket.emit("note:update", { ideaId: this.ideaId, update, seed }, (ack: Ack) => {
      if (!ack?.ok && ack?.error === "already-seeded") this.resetListeners.forEach((l) => l());
    });
  }

  private onDocUpdate = (update: Uint8Array, origin: unknown) => {
    if (origin === SERVER || this.destroyed || !this.snapshot.canEdit) return;
    if (this.snapshot.status !== "live") return; // sent on reconnect via the state diff
    this.sendUpdate(update, this.seeding);
  };

  private onAwarenessUpdate = (
    { added, updated, removed }: { added: number[]; updated: number[]; removed: number[] },
    origin: unknown
  ) => {
    if (origin === SERVER || this.snapshot.status !== "live") return;
    const mine = [...added, ...updated, ...removed].filter((id) => id === this.doc.clientID);
    if (!mine.length) return;
    this.socket.emit("note:awareness", {
      ideaId: this.ideaId,
      update: encodeAwarenessUpdate(this.awareness, mine),
    });
  };

  private onRemoteUpdate = (data: { ideaId: string; update: unknown }) => {
    const update = toBytes(data?.update);
    if (data?.ideaId === this.ideaId && update) {
      Y.applyUpdate(this.doc, update, SERVER);
      this.markReady();
    }
  };

  private onRemoteAwareness = (data: { ideaId: string; update: unknown }) => {
    const update = toBytes(data?.update);
    if (data?.ideaId === this.ideaId && update) applyAwarenessUpdate(this.awareness, update, SERVER);
  };

  private onLeft = (data: { ideaId: string; clientId: number }) => {
    if (data?.ideaId === this.ideaId) removeAwarenessStates(this.awareness, [data.clientId], SERVER);
  };

  private onPeers = (data: { ideaId: string; peers: LivePeer[]; external: LiveExternalEditor[] }) => {
    if (data?.ideaId !== this.ideaId) return;
    const joined = data.peers.length > this.snapshot.peers.length;
    this.set({ peers: data.peers, external: data.external || [] });
    // Show our cursor to whoever just arrived.
    if (joined) this.awareness.setLocalState(this.awareness.getLocalState() || {});
  };

  private onSeedRequest = (data: { ideaId: string }) => {
    if (data?.ideaId !== this.ideaId || this.fragment.length > 0) return;
    this.seedPending = true;
    void this.runSeed();
  };

  private onExternal = (data: LiveExternalEdit) => {
    if (data?.ideaId === this.ideaId) this.externalListeners.forEach((listener) => listener(data));
  };

  private onReset = (data: LiveExternalEdit) => {
    if (data?.ideaId !== this.ideaId) return;
    this.externalListeners.forEach((listener) => listener({ ...data, apply: false }));
    this.resetListeners.forEach((listener) => listener(data.html));
  };

  private onDisconnect = () => {
    if (!this.destroyed) this.set({ status: "offline" });
  };
}

function defaultSocket(): Socket {
  return io({
    path: "/socket.io",
    transports: ["websocket", "polling"],
    withCredentials: true,
    autoConnect: false,
    reconnectionDelayMax: 10000,
  });
}
