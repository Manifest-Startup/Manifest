/**
 * Ideas kept as Markdown files in a folder the person picked (ADR 0011).
 *
 * The folder is the source of truth: the store re-reads it whenever files change, so edits
 * from Obsidian, another editor or another computer (through iCloud Drive, Dropbox…) show
 * up in Manifest. Deleting an idea moves its files to `Manifest/.trash`, never erases them.
 */
import type { VaultFs } from "./fs";
import { AUTO_SNAPSHOT_MS, VaultHistory, type Snapshot } from "./history";
import { htmlToMarkdown, markdownToHtml } from "./convert";
import {
  DOCUMENTS_DIR,
  DOCUMENT_FILES,
  IDEAS_DIR,
  TRASH_DIR,
  newIdeaId,
  parseIdeaFile,
  safeName,
  serializeIdeaFile,
  type IdeaFile,
} from "./format";

export const LOCAL_USER_ID = "local";

interface Entry {
  path: string;
  name: string; // file name without .md, also the documents folder name
  modified: number;
  file: IdeaFile;
}

export interface IdeaRecord {
  ideaId: string;
  userId: string;
  title: string;
  description: string; // HTML for the editor
  isPublished: boolean;
  requiredSkills: string[];
  createdAt: string | null;
  updatedAt: string | null;
  hasDescription: boolean;
  generatedAssetCount: number;
  [document: string]: unknown;
}

const nameOf = (path: string) => path.split("/").pop()!.replace(/\.md$/i, "");
const now = () => new Date().toISOString();

/**
 * Files in the Ideas folder that are not ideas: its README, and the copies Manifest's
 * background sync makes beside a note (`… (Manifest)`, conflicted copies).
 */
export function isSyncCopy(name: string): boolean {
  return (
    /^readme$/i.test(name) || /\s\(Manifest\)$/.test(name) || /\(conflicted copy\b/.test(name)
  );
}

export class VaultStore {
  private entries = new Map<string, Entry>();
  /** The folder as last read; null forces a re-read (an empty folder reads as ""). */
  private signature: string | null = null;
  /** The editor's own HTML for the Markdown it last saved, so a save never reflows the note. */
  private htmlFor = new Map<string, { markdown: string; html: string }>();

  readonly history: VaultHistory;
  private listeners = new Set<() => void>();

  constructor(readonly fs: VaultFs) {
    this.history = new VaultHistory(fs);
  }

  /** Called after Manifest itself changes the folder (the sync engine listens). */
  onLocalChange(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private changed() {
    this.listeners.forEach((listener) => listener());
  }

  get name() {
    return this.fs.name;
  }

  /** Re-read the folder. Returns true when something changed since the last look. */
  async refresh(): Promise<boolean> {
    const files = await this.fs.list(IDEAS_DIR);
    const signature = files
      .map((f) => `${f.path}:${f.modified}`)
      .sort()
      .join("|");
    if (signature === this.signature) return false;
    const byPath = new Map([...this.entries.values()].map((e) => [e.path, e]));
    const next = new Map<string, Entry>();
    // Plain names first, so a sync tool's copy of a note never displaces the note itself.
    const ordered = files
      .filter(({ path }) => !isSyncCopy(nameOf(path)))
      .sort((a, b) => nameOf(a.path).length - nameOf(b.path).length || a.path.localeCompare(b.path));
    for (const { path, modified } of ordered) {
      const known = byPath.get(path);
      if (known && known.modified === modified && !next.has(known.file.id!)) {
        next.set(known.file.id!, known);
        continue;
      }
      const text = await this.fs.read(path);
      if (text === null) continue;
      const file = parseIdeaFile(text, nameOf(path));
      if (file.id && next.has(file.id)) {
        // A second file with the same idea's id is a copy (a sync tool, Finder, iCloud),
        // not a new idea: turning it into one would create a duplicate in the account.
        continue;
      }
      if (!file.id) {
        // A note written outside Manifest: give it its own id.
        file.id = newIdeaId();
        file.created = file.created ?? new Date(modified || Date.now()).toISOString();
        await this.fs.write(path, serializeIdeaFile(file));
      }
      next.set(file.id, { path, name: nameOf(path), modified, file });
    }
    this.entries = next;
    this.signature = signature;
    return true;
  }

  private entry(id: string): Entry {
    const entry = this.entries.get(id);
    if (!entry) throw new Error("This idea isn't in the vault folder anymore.");
    return entry;
  }

  private uniqueName(title: string, id: string): string {
    const base = safeName(title);
    const taken = new Set(
      [...this.entries.values()].filter((e) => e.file.id !== id).map((e) => e.name.toLowerCase()),
    );
    return taken.has(base.toLowerCase()) ? `${base} (${id.slice(0, 8)})` : base;
  }

  private descriptionHtml(id: string, markdown: string): string {
    const known = this.htmlFor.get(id);
    return known && known.markdown === markdown ? known.html : markdownToHtml(markdown);
  }

  async documents(id: string): Promise<Record<string, string | null>> {
    const { name } = this.entry(id);
    const docs: Record<string, string | null> = {};
    for (const [field, file] of Object.entries(DOCUMENT_FILES)) {
      docs[field] = await this.fs.read(`${DOCUMENTS_DIR}/${name}/${file}.md`);
    }
    return docs;
  }

  async list(): Promise<IdeaRecord[]> {
    await this.refresh();
    const ideas = [...this.entries.values()].map((e) => this.record(e, {}));
    return ideas.sort((a, b) => String(b.createdAt ?? "").localeCompare(String(a.createdAt ?? "")));
  }

  async get(id: string, withDocuments = false): Promise<IdeaRecord | null> {
    await this.refresh();
    const entry = this.entries.get(id);
    if (!entry) return null;
    return this.record(entry, withDocuments ? await this.documents(id) : {});
  }

  private record(entry: Entry, documents: Record<string, string | null>): IdeaRecord {
    const { file } = entry;
    const description = this.descriptionHtml(file.id!, file.body);
    return {
      ideaId: file.id!,
      userId: LOCAL_USER_ID,
      title: file.title,
      description,
      isPublished: false,
      requiredSkills: file.skills,
      createdAt: file.created,
      updatedAt: file.updated,
      hasDescription: Boolean(file.body.trim()),
      generatedAssetCount: Object.values(documents).filter(Boolean).length,
      ...Object.fromEntries(Object.keys(DOCUMENT_FILES).map((k) => [k, documents[k] ?? null])),
    };
  }

  async create(title: string, descriptionHtml = ""): Promise<IdeaRecord> {
    await this.refresh();
    const id = newIdeaId();
    const stamp = now();
    const markdown = htmlToMarkdown(descriptionHtml);
    const file: IdeaFile = {
      id,
      title: title.trim() || "Untitled idea",
      created: stamp,
      updated: stamp,
      published: false,
      skills: [],
      body: markdown,
      extra: [],
      tail: "",
    };
    const name = this.uniqueName(file.title, id);
    const path = `${IDEAS_DIR}/${name}.md`;
    await this.fs.write(path, serializeIdeaFile(file));
    if (descriptionHtml) this.htmlFor.set(id, { markdown, html: descriptionHtml });
    this.signature = null; // re-read on next look
    await this.refresh();
    this.changed();
    return (await this.get(id))!;
  }

  async update(
    id: string,
    changes: { title?: string | null; description?: string | null; requiredSkills?: string[] | null },
  ): Promise<IdeaRecord> {
    await this.refresh();
    const entry = this.entry(id);
    // History while writing: keep how the note looked, at most every few minutes.
    if (Date.now() - (await this.history.latestAt(id)) > AUTO_SNAPSHOT_MS) {
      const before = await this.fs.read(entry.path);
      if (before !== null) await this.history.save(id, before, "auto");
    }
    const file = { ...entry.file };
    if (changes.description != null) {
      file.body = htmlToMarkdown(changes.description);
      this.htmlFor.set(id, { markdown: file.body, html: changes.description });
    }
    if (changes.requiredSkills != null) file.skills = changes.requiredSkills;
    let name = entry.name;
    if (changes.title != null && changes.title.trim() && changes.title.trim() !== file.title) {
      file.title = changes.title.trim();
      name = this.uniqueName(file.title, id);
    }
    file.updated = now();
    const path = `${IDEAS_DIR}/${name}.md`;
    await this.fs.write(path, serializeIdeaFile(file));
    if (path !== entry.path) {
      await this.moveDocuments(entry.name, `${DOCUMENTS_DIR}/${name}`);
      await this.fs.remove(entry.path);
    }
    this.signature = null;
    await this.refresh();
    this.changed();
    return (await this.get(id, true))!;
  }

  // -- version history (ADR 0012) -----------------------------------------------------

  async versions(id: string): Promise<Snapshot[]> {
    return this.history.list(id);
  }

  async saveVersion(id: string, note?: string | null): Promise<Snapshot> {
    await this.refresh();
    const text = await this.fs.read(this.entry(id).path);
    const path = await this.history.save(id, text ?? "", "manual", note?.trim() || undefined);
    return (await this.history.list(id)).find((v) => v.versionId === path)!;
  }

  /** Bring an older version back (the current one is kept in history first). */
  async restoreVersion(id: string, versionId: string): Promise<void> {
    await this.refresh();
    const entry = this.entry(id);
    const old = await this.history.read(versionId);
    if (old === null) throw new Error("That version isn't in the vault's history anymore.");
    const current = await this.fs.read(entry.path);
    if (current !== null) await this.history.save(id, current, "restore");
    const file = parseIdeaFile(old, entry.file.title);
    await this.writeIdea(id, { title: file.title, body: file.body, skills: file.skills });
  }

  // -- for the sync engine (ADR 0012) -------------------------------------------------

  /** Every idea with the time it last changed (Manifest's own stamp or the file's). */
  async snapshot(): Promise<
    {
      id: string;
      title: string;
      body: string;
      html: string;
      skills: string[];
      created: string | null;
      changedAt: number;
      documents: Record<string, string | null>;
    }[]
  > {
    await this.refresh();
    const out = [];
    for (const entry of this.entries.values()) {
      const id = entry.file.id!;
      out.push({
        id,
        title: entry.file.title,
        body: entry.file.body,
        html: this.descriptionHtml(id, entry.file.body),
        skills: entry.file.skills,
        created: entry.file.created,
        changedAt: Math.max(Date.parse(entry.file.updated ?? "") || 0, entry.modified || 0),
        documents: await this.documents(id),
      });
    }
    return out;
  }

  /**
   * Write an idea's content as given (from the account during sync), keeping its id and
   * file. The version it replaces goes to history first when `keep` is set.
   */
  async writeIdea(
    id: string,
    content: { title: string; body?: string; html?: string; skills: string[]; documents?: Record<string, string | null | undefined> },
    keep?: "sync" | "conflict",
  ): Promise<void> {
    await this.refresh();
    const entry = this.entry(id);
    if (keep) {
      const before = await this.fs.read(entry.path);
      if (before !== null) await this.history.save(id, before, keep);
    }
    const body = content.body ?? htmlToMarkdown(content.html ?? "");
    if (content.html) this.htmlFor.set(id, { markdown: body, html: content.html });
    const file: IdeaFile = { ...entry.file, title: content.title.trim() || entry.file.title, body, skills: content.skills, updated: now() };
    const name = file.title === entry.file.title ? entry.name : this.uniqueName(file.title, id);
    const path = `${IDEAS_DIR}/${name}.md`;
    await this.fs.write(path, serializeIdeaFile(file));
    if (path !== entry.path) {
      await this.moveDocuments(entry.name, `${DOCUMENTS_DIR}/${name}`);
      await this.fs.remove(entry.path);
    }
    for (const [field, markdown] of Object.entries(content.documents ?? {})) {
      if (markdown && DOCUMENT_FILES[field]) {
        await this.fs.write(`${DOCUMENTS_DIR}/${name}/${DOCUMENT_FILES[field]}.md`, markdown);
      }
    }
    this.signature = null;
    await this.refresh();
  }

  async writeDocument(id: string, field: string, markdown: string): Promise<void> {
    const file = DOCUMENT_FILES[field];
    if (!file) throw new Error(`Unknown document: ${field}`);
    await this.fs.write(`${DOCUMENTS_DIR}/${this.entry(id).name}/${file}.md`, markdown);
  }

  private async moveDocuments(fromName: string, toDir: string) {
    for (const file of Object.values(DOCUMENT_FILES)) {
      const from = `${DOCUMENTS_DIR}/${fromName}/${file}.md`;
      const text = await this.fs.read(from);
      if (text === null) continue;
      await this.fs.write(`${toDir}/${file}.md`, text);
      await this.fs.remove(from);
    }
    // Don't leave an empty folder behind (only its generated README): the README goes along
    // and the folder is removed. A folder with anything else in it stays (and removing a
    // folder that isn't empty never happens: the file system refuses it).
    const folder = `${DOCUMENTS_DIR}/${fromName}`;
    const left = await this.fs.list(folder);
    if (left.every((f) => f.path === `${folder}/README.md`)) {
      const readme = left.length ? await this.fs.read(`${folder}/README.md`) : null;
      if (readme !== null) {
        // Into the trash with the documents; on a rename, the new folder keeps its own.
        const keep = toDir.startsWith(TRASH_DIR)
          ? `${toDir}/README.md`
          : `${TRASH_DIR}/${fromName} README ${now().replace(/[:.]/g, "-")}.md`;
        await this.fs.write(keep, readme);
        await this.fs.remove(`${folder}/README.md`);
      }
      await this.fs.remove(folder);
    }
  }

  /**
   * Copy an idea from a Manifest account into the folder, keeping its id. Ideas already in
   * the folder are left alone, so copying twice never overwrites local edits.
   * Returns false when it was already there.
   */
  async importIdea(idea: {
    id: string;
    title: string;
    descriptionHtml: string;
    skills: string[];
    created: string | null;
    documents: Record<string, string | null | undefined>;
  }): Promise<boolean> {
    await this.refresh();
    if (this.entries.has(idea.id)) return false;
    const file: IdeaFile = {
      id: idea.id,
      title: idea.title.trim() || "Untitled idea",
      created: idea.created ?? now(),
      updated: now(),
      published: false,
      skills: idea.skills,
      body: htmlToMarkdown(idea.descriptionHtml),
      extra: [],
      tail: "",
    };
    const name = this.uniqueName(file.title, idea.id);
    await this.fs.write(`${IDEAS_DIR}/${name}.md`, serializeIdeaFile(file));
    this.entries.set(idea.id, { path: `${IDEAS_DIR}/${name}.md`, name, modified: 0, file });
    for (const [field, markdown] of Object.entries(idea.documents)) {
      if (markdown && DOCUMENT_FILES[field]) {
        await this.fs.write(`${DOCUMENTS_DIR}/${name}/${DOCUMENT_FILES[field]}.md`, markdown);
      }
    }
    this.signature = null;
    return true;
  }

  /** Move the idea and its documents to `Manifest/.trash`, so nothing is lost. */
  async remove(id: string): Promise<void> {
    await this.refresh();
    const entry = this.entry(id);
    const stamp = now().replace(/[:.]/g, "-");
    const text = await this.fs.read(entry.path);
    if (text !== null) await this.fs.write(`${TRASH_DIR}/${entry.name} ${stamp}.md`, text);
    await this.moveDocuments(entry.name, `${TRASH_DIR}/${entry.name} ${stamp}`);
    await this.fs.remove(entry.path);
    this.signature = null;
    await this.refresh();
    this.changed();
  }
}
