/**
 * Version history for a local vault (ADR 0012): plain snapshots, not a git repository.
 *
 *   Manifest/.history/<manifest_id>/<2026-11-19T10-05-00-000Z> <kind>.md
 *
 * Each snapshot is the whole idea file as it was, so it opens in any editor. Snapshots are
 * taken while you write (at most every few minutes), when you save a version yourself,
 * before a restore, and for whichever side lost a sync conflict, so nothing is ever lost.
 * Git isn't used because a .git folder inside iCloud Drive gets corrupted by sync, and it
 * would need a heavy library in the browser.
 */
import type { VaultFs } from "./fs";
import { ROOT, parseIdeaFile } from "./format";
import { markdownToHtml } from "./convert";

export const HISTORY_DIR = `${ROOT}/.history`;
export const AUTO_SNAPSHOT_MS = 90 * 1000; // like the account's checkpoints

export type SnapshotKind = "auto" | "manual" | "restore" | "sync" | "conflict";

const KIND_LABELS: Record<SnapshotKind, string> = {
  auto: "Saved while writing",
  manual: "Saved version",
  restore: "Before restoring an older version",
  sync: "Before taking the account's newer version",
  conflict: "The older side of a sync conflict",
};

const stamp = (date = new Date()) => date.toISOString().replace(/[:.]/g, "-");
const fromStamp = (text: string) => text.replace(/T(\d\d)-(\d\d)-(\d\d)-(\d{3})Z$/, "T$1:$2:$3.$4Z");

export interface Snapshot {
  versionId: string; // the snapshot's path
  ideaId: string;
  versionNumber: number;
  title: string;
  description: string; // HTML, for the versions panel preview
  createdAt: string;
  changeSummary: string | null;
  versionKind: SnapshotKind;
  createdBy: string;
  creatorName: string;
  creatorAvatar: null;
}

export class VaultHistory {
  constructor(private readonly fs: VaultFs) {}

  private dir(ideaId: string) {
    return `${HISTORY_DIR}/${ideaId}`;
  }

  async save(ideaId: string, content: string, kind: SnapshotKind, note?: string): Promise<string> {
    const body = note ? content.replace(/^---\n/, `---\nversion_note: ${JSON.stringify(note)}\n`) : content;
    const path = `${this.dir(ideaId)}/${stamp()} ${kind}.md`;
    await this.fs.write(path, body);
    return path;
  }

  /** The newest snapshot's time, to space automatic snapshots out. */
  async latestAt(ideaId: string): Promise<number> {
    const files = await this.fs.list(this.dir(ideaId));
    const times = files.map((f) => Date.parse(fromStamp(f.path.split("/").pop()!.split(" ")[0])));
    return times.length ? Math.max(...times.filter(Number.isFinite)) : 0;
  }

  async list(ideaId: string): Promise<Snapshot[]> {
    const files = (await this.fs.list(this.dir(ideaId))).map((f) => f.path).sort();
    const snapshots: Snapshot[] = [];
    for (const [index, path] of files.entries()) {
      const name = path.split("/").pop()!.replace(/\.md$/, "");
      const [when, kind = "auto"] = name.split(" ");
      const text = (await this.fs.read(path)) ?? "";
      const file = parseIdeaFile(text, "Untitled idea");
      const note = file.extra.find((line) => line.startsWith("version_note:"));
      snapshots.push({
        versionId: path,
        ideaId,
        versionNumber: index + 1,
        title: file.title,
        description: markdownToHtml(file.body),
        createdAt: fromStamp(when),
        changeSummary: note ? JSON.parse(note.slice("version_note:".length).trim()) : KIND_LABELS[kind as SnapshotKind] ?? null,
        versionKind: (kind in KIND_LABELS ? kind : "auto") as SnapshotKind,
        createdBy: "local",
        creatorName: "You",
        creatorAvatar: null,
      });
    }
    return snapshots.reverse(); // newest first, like the account's history
  }

  async read(versionId: string): Promise<string | null> {
    if (!versionId.startsWith(`${HISTORY_DIR}/`)) return null;
    return this.fs.read(versionId);
  }
}
