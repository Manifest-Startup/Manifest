import { MemoryVaultFs } from "../fs";
import { VaultStore } from "../store";
import { VaultSync, type CloudApi, type CloudIdea } from "../sync";

/** An in-memory Manifest account with a clock we control. */
class FakeCloud implements CloudApi {
  ideas = new Map<string, CloudIdea>();
  now = Date.now() - 86_400_000;
  signedIn = true;
  private next = 1;
  tick(ms = 60_000) {
    this.now += ms;
    return this.now;
  }
  async account() {
    return this.signedIn ? { userId: "u1", email: "me@example.com" } : null;
  }
  async list() {
    return [...this.ideas.values()].map((i) => ({ id: i.id, updatedAt: i.updatedAt }));
  }
  async get(id: string) {
    const idea = this.ideas.get(id);
    return idea ? { ...idea, documents: { ...idea.documents } } : null;
  }
  async create(title: string, html: string) {
    const id = `cloud-${this.next++}`;
    this.ideas.set(id, { id, title, html, skills: [], createdAt: new Date(this.now).toISOString(), updatedAt: this.tick(1), documents: {} });
    return id;
  }
  async update(id: string, change: { title: string; html: string; skills: string[] }) {
    Object.assign(this.ideas.get(id)!, change, { updatedAt: this.tick(1) });
  }
  async saveDocument(id: string, type: string, markdown: string) {
    const field = { pitch_deck: "pitchDeck" }[type] ?? type;
    this.ideas.get(id)!.documents[field] = markdown;
    this.ideas.get(id)!.updatedAt = this.tick(1);
  }
  async remove(id: string) {
    this.ideas.delete(id);
  }
  edit(id: string, html: string) {
    Object.assign(this.ideas.get(id)!, { html, updatedAt: this.tick() });
  }
}

async function setup() {
  const fs = new MemoryVaultFs();
  const store = new VaultStore(fs);
  const cloud = new FakeCloud();
  return { fs, store, cloud, sync: new VaultSync(store, cloud) };
}

const text = async (store: VaultStore, id: string) => (await store.get(id))?.description ?? null;

describe("a vault synced with the Manifest account", () => {
  it("combines both sides on the first sync", async () => {
    const { store, cloud, sync } = await setup();
    const local = await store.create("Written offline", "<p>From the vault.</p>");
    await cloud.create("From the account", "<p>From the cloud.</p>");

    const report = await sync.run();
    expect(report).toMatchObject({ created: 1, pulled: 1, errors: [] });
    const titles = (await store.list()).map((i) => i.title).sort();
    expect(titles).toEqual(["From the account", "Written offline"]);
    expect([...cloud.ideas.values()].map((i) => i.title).sort()).toEqual(["From the account", "Written offline"]);
    expect([...cloud.ideas.values()].find((i) => i.title === "Written offline")!.html).toContain("From the vault.");

    // Nothing changed: nothing moves.
    expect(await sync.run()).toMatchObject({ pushed: 0, pulled: 0, created: 0, deleted: 0, conflicts: 0 });
    void local;
  });

  it("sends local edits and receives account edits, keeping the replaced version in history", async () => {
    const { store, cloud, sync } = await setup();
    const idea = await store.create("Bikes", "<p>One.</p>");
    await sync.run();
    const cloudId = [...cloud.ideas.keys()][0];

    await store.update(idea.ideaId, { description: "<p>Two, from this Mac.</p>" });
    expect(await sync.run()).toMatchObject({ pushed: 1, pulled: 0 });
    expect(cloud.ideas.get(cloudId)!.html).toContain("Two, from this Mac.");

    cloud.edit(cloudId, "<p>Three, from the phone.</p>");
    expect(await sync.run()).toMatchObject({ pushed: 0, pulled: 1 });
    expect(await text(store, idea.ideaId)).toContain("Three, from the phone.");
    const history = await store.versions(idea.ideaId);
    expect(history.some((v) => v.versionKind === "sync" && v.description.includes("Two, from this Mac."))).toBe(true);
  });

  it("resolves a conflict to the newest version and keeps the other in history", async () => {
    const { store, cloud, sync } = await setup();
    const idea = await store.create("Lanes", "<p>Base.</p>");
    await sync.run();
    const cloudId = [...cloud.ideas.keys()][0];

    await store.update(idea.ideaId, { description: "<p>Local edit.</p>" });
    // The account edit happens later than the local one: the account wins.
    cloud.now = Date.now() + 3_600_000;
    cloud.edit(cloudId, "<p>Newer account edit.</p>");
    expect(await sync.run()).toMatchObject({ conflicts: 1, pulled: 1 });
    expect(await text(store, idea.ideaId)).toContain("Newer account edit.");
    const kept = await store.versions(idea.ideaId);
    expect(kept.some((v) => v.versionKind === "conflict" && v.description.includes("Local edit."))).toBe(true);

    // Now the local side is newer: it wins, and the account's version is kept.
    cloud.edit(cloudId, "<p>Old account edit.</p>");
    cloud.ideas.get(cloudId)!.updatedAt = Date.now() - 3_600_000;
    const base = cloud.ideas.get(cloudId)!;
    await store.update(idea.ideaId, { description: "<p>Newest, local.</p>" });
    base.updatedAt = Date.now() - 1; // changed since the baseline, but older than the local edit
    // (make the account change visible to the baseline comparison)
    const report = await sync.run();
    expect(report.conflicts + report.pushed).toBeGreaterThan(0);
    expect(cloud.ideas.get(cloudId)!.html).toContain("Newest, local.");
  });

  it("carries deletions both ways without losing the vault copy", async () => {
    const { fs, store, cloud, sync } = await setup();
    const a = await store.create("Delete here", "<p>A.</p>");
    await store.create("Delete there", "<p>B.</p>");
    await sync.run();
    const there = [...cloud.ideas.values()].find((i) => i.title === "Delete there")!;

    await store.remove(a.ideaId);
    await cloud.remove(there.id);
    const result = await sync.run();
    expect(result).toMatchObject({ deleted: 2, errors: [] });
    expect([...cloud.ideas.values()].map((i) => i.title)).toEqual([]);
    expect((await store.list()).map((i) => i.title)).toEqual([]);
    expect([...fs.files.keys()].filter((p) => p.startsWith("Manifest/.trash/") && p.endsWith(".md")).length).toBeGreaterThanOrEqual(2);
  });

  it("does nothing while signed out", async () => {
    const { store, cloud, sync } = await setup();
    cloud.signedIn = false;
    await store.create("Private", "<p>Only here.</p>");
    expect(await sync.run()).toMatchObject({ account: null, created: 0 });
    expect(cloud.ideas.size).toBe(0);
  });
});

describe("vault version history", () => {
  it("saves, lists and restores versions, keeping the replaced one", async () => {
    const { store } = await setup();
    const idea = await store.create("History", "<p>First draft.</p>");
    await store.saveVersion(idea.ideaId, "Before the pivot");
    await store.update(idea.ideaId, { description: "<p>Second draft.</p>" });
    const [manual] = (await store.versions(idea.ideaId)).filter((v) => v.versionKind === "manual");
    expect(manual.changeSummary).toBe("Before the pivot");
    expect(manual.description).toContain("First draft.");

    await store.restoreVersion(idea.ideaId, manual.versionId);
    expect(await text(store, idea.ideaId)).toContain("First draft.");
    expect((await store.versions(idea.ideaId)).some((v) => v.versionKind === "restore" && v.description.includes("Second draft."))).toBe(true);
  });
});
