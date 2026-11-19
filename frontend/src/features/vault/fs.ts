/**
 * The folder a local vault lives in (ADR 0011). Any folder works, including one inside
 * iCloud Drive, Dropbox or OneDrive: the operating system syncs the files, Manifest only
 * reads and writes Markdown.
 *
 * `VaultFs` is the small surface the vault store needs, so tests use an in-memory folder
 * and the app uses the browser's File System Access API.
 */

export interface VaultFile {
  path: string; // "Manifest/Ideas/My idea.md"
  modified: number; // ms since epoch
}

export interface VaultFs {
  readonly name: string;
  list(dir: string): Promise<VaultFile[]>;
  read(path: string): Promise<string | null>;
  write(path: string, content: string): Promise<void>;
  remove(path: string): Promise<void>;
}

const split = (path: string) => path.split("/").filter(Boolean);

/** A folder the person picked, through the browser's File System Access API. */
export class BrowserVaultFs implements VaultFs {
  constructor(private readonly root: FileSystemDirectoryHandle) {}

  get name() {
    return this.root.name;
  }

  private async dir(parts: string[], create: boolean): Promise<FileSystemDirectoryHandle | null> {
    let dir = this.root;
    for (const part of parts) {
      try {
        dir = await dir.getDirectoryHandle(part, { create });
      } catch {
        return null;
      }
    }
    return dir;
  }

  async list(path: string): Promise<VaultFile[]> {
    const dir = await this.dir(split(path), false);
    if (!dir) return [];
    const files: VaultFile[] = [];
    // `entries()` is part of the File System Access API; TypeScript's DOM lib may lag it.
    const entries = (dir as unknown as { entries(): AsyncIterable<[string, FileSystemHandle]> }).entries();
    for await (const [name, handle] of entries) {
      if (handle.kind !== "file" || !name.toLowerCase().endsWith(".md") || name.startsWith(".")) continue;
      const file = await (handle as FileSystemFileHandle).getFile();
      files.push({ path: `${path}/${name}`, modified: file.lastModified });
    }
    return files;
  }

  async read(path: string): Promise<string | null> {
    const parts = split(path);
    const dir = await this.dir(parts.slice(0, -1), false);
    if (!dir) return null;
    try {
      const handle = await dir.getFileHandle(parts[parts.length - 1]);
      return await (await handle.getFile()).text();
    } catch {
      return null;
    }
  }

  async write(path: string, content: string): Promise<void> {
    const parts = split(path);
    const dir = await this.dir(parts.slice(0, -1), true);
    if (!dir) throw new Error(`Can't create the folder for ${path}`);
    const handle = await dir.getFileHandle(parts[parts.length - 1], { create: true });
    const writable = await handle.createWritable();
    await writable.write(content);
    await writable.close();
  }

  async remove(path: string): Promise<void> {
    const parts = split(path);
    const dir = await this.dir(parts.slice(0, -1), false);
    if (!dir) return;
    try {
      await dir.removeEntry(parts[parts.length - 1]);
    } catch {
      // Already gone (another device deleted it): nothing to do.
    }
  }
}

/** An in-memory folder, for tests and previews. */
export class MemoryVaultFs implements VaultFs {
  readonly files = new Map<string, { content: string; modified: number }>();
  private clock = 1;
  constructor(readonly name = "Test vault") {}

  async list(dir: string): Promise<VaultFile[]> {
    const prefix = `${dir.replace(/\/$/, "")}/`;
    return [...this.files.entries()]
      .filter(([path]) => path.startsWith(prefix) && !path.slice(prefix.length).includes("/"))
      .filter(([path]) => path.toLowerCase().endsWith(".md"))
      .map(([path, f]) => ({ path, modified: f.modified }));
  }

  async read(path: string) {
    return this.files.get(path)?.content ?? null;
  }

  async write(path: string, content: string) {
    this.files.set(path, { content, modified: this.clock++ });
  }

  async remove(path: string) {
    this.files.delete(path);
  }
}
