import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import * as Y from "yjs";
import type { Socket } from "socket.io-client";
import { LiveNoteSession, LiveSnapshot } from "../live/liveNoteSession";
import { applyHtmlChange, caretLabel, changedEnd } from "../live/externalEdits";
import { livePeople } from "../live/LivePresence";

type Handler = (...args: any[]) => void;

/** A Socket.IO stand-in: records emits and lets the test play the server. */
class FakeSocket {
  connected = true;
  handlers = new Map<string, Handler[]>();
  emitted: { event: string; data: any; ack?: Handler }[] = [];
  on(event: string, handler: Handler) {
    this.handlers.set(event, [...(this.handlers.get(event) || []), handler]);
    return this;
  }
  off(event: string, handler: Handler) {
    this.handlers.set(event, (this.handlers.get(event) || []).filter((h) => h !== handler));
    return this;
  }
  emit(event: string, data: any, ack?: Handler) {
    this.emitted.push({ event, data, ack });
    return this;
  }
  connect() {
    return this;
  }
  disconnect() {
    this.connected = false;
    return this;
  }
  serverSends(event: string, data: any) {
    (this.handlers.get(event) || []).forEach((h) => h(data));
  }
  last(event: string) {
    return [...this.emitted].reverse().find((e) => e.event === event);
  }
}

const peer = (userId: string, name: string) => ({
  clientId: 1,
  userId,
  name,
  avatarUrl: null,
  color: "#2563eb",
  role: "editor",
  canEdit: true,
  via: "app" as const,
});

function makeSession() {
  const socket = new FakeSocket();
  const session = new LiveNoteSession("idea-1", () => socket as unknown as Socket);
  return { socket, session };
}

describe("LiveNoteSession", () => {
  it("joins with its client id and seeds an empty room exactly once, from a fresh copy", async () => {
    const { socket, session } = makeSession();
    const join = socket.last("note:join")!;
    expect(join.data.ideaId).toBe("idea-1");
    expect(join.data.clientId).toBe(session.doc.clientID);

    const load = jest.fn(async () => "<p>saved</p>");
    const write = jest.fn(() => {
      session.fragment.insert(0, [new Y.XmlElement("paragraph")]);
    });
    session.setSeeder({ load, write });
    join.ack!({ ok: true, seed: true, canEdit: true, update: new Uint8Array([0, 0]), peers: [], external: [] });
    expect(session.getSnapshot()).toMatchObject({ status: "live", ready: false });
    await Promise.resolve();
    await Promise.resolve();

    expect(load).toHaveBeenCalledTimes(1);
    expect(write).toHaveBeenCalledWith("<p>saved</p>");
    expect(session.getSnapshot().ready).toBe(true);
    const sent = socket.last("note:update")!;
    expect(sent.data.seed).toBe(true);

    // Someone else filled the room first: the hook is told to start over.
    const reset = jest.fn();
    session.onResetRequired(reset);
    sent.ack!({ ok: false, error: "already-seeded" });
    expect(reset).toHaveBeenCalled();
    session.destroy();
  });

  it("skips seeding when the shared copy arrives while the saved note loads", async () => {
    const { socket, session } = makeSession();
    let finish: (html: string) => void = () => undefined;
    const write = jest.fn();
    session.setSeeder({ load: () => new Promise<string>((r) => (finish = r)), write });
    socket.last("note:join")!.ack!({ ok: true, seed: true, canEdit: true, peers: [], external: [] });
    const other = new Y.Doc();
    other.getXmlFragment("default").insert(0, [new Y.XmlText("theirs")]);
    socket.serverSends("note:update", { ideaId: "idea-1", update: Y.encodeStateAsUpdate(other) });
    finish("<p>mine</p>");
    await Promise.resolve();
    await Promise.resolve();
    expect(write).not.toHaveBeenCalled();
    expect(session.getSnapshot().ready).toBe(true);
    session.destroy();
  });

  it("applies remote updates without echoing them back", () => {
    const { socket, session } = makeSession();
    socket.last("note:join")!.ack!({ ok: true, seed: false, canEdit: true, peers: [], external: [] });
    const before = socket.emitted.filter((e) => e.event === "note:update").length;

    const other = new Y.Doc();
    other.getXmlFragment("default").insert(0, [new Y.XmlText("hello")]);
    socket.serverSends("note:update", { ideaId: "idea-1", update: Y.encodeStateAsUpdate(other) });

    expect(session.fragment.toString()).toContain("hello");
    expect(socket.emitted.filter((e) => e.event === "note:update").length).toBe(before);
    session.destroy();
  });

  it("does not send edits from a view-only person and reports denial", () => {
    const { socket, session } = makeSession();
    socket.last("note:join")!.ack!({ ok: true, seed: true, canEdit: false, peers: [], external: [] });
    session.fragment.insert(0, [new Y.XmlText("x")]);
    expect(socket.last("note:update")).toBeUndefined();
    session.destroy();

    const denied = makeSession();
    denied.socket.last("note:join")!.ack!({ ok: false, error: "You don't have access to this note" });
    expect(denied.session.getSnapshot()).toMatchObject({ status: "denied" });
    denied.session.destroy();
  });

  it("passes agent edits and resets to listeners", () => {
    const { socket, session } = makeSession();
    const edits = jest.fn();
    const reset = jest.fn();
    session.onExternalEdit(edits);
    session.onResetRequired(reset);
    const by = { userId: "u", name: "Ana", avatarUrl: null, color: "#000", via: "agent", viaLabel: "AI agent", until: 0 };
    socket.serverSends("note:external", { ideaId: "idea-1", html: "<p>x</p>", apply: true, by });
    socket.serverSends("note:external", { ideaId: "other", html: "<p>y</p>", apply: true, by });
    socket.serverSends("note:reset", { ideaId: "idea-1", html: "<p>z</p>", apply: false, by });
    expect(edits).toHaveBeenCalledTimes(2);
    expect(reset).toHaveBeenCalledWith("<p>z</p>");
    session.destroy();
  });
});

describe("external edits", () => {
  it("replaces only the changed range and returns where it ended", () => {
    const editor = new Editor({ extensions: [StarterKit], content: "<p>one</p><p>two</p><p>three</p>" });
    const before = editor.state.doc;
    const pos = applyHtmlChange(editor, "<p>one</p><p>two and more</p><p>three</p>");
    expect(editor.getHTML()).toBe("<p>one</p><p>two and more</p><p>three</p>");
    expect(pos).toBe(changedEnd(before, editor.state.doc));
    expect(editor.state.doc.textBetween(0, pos!)).toContain("two and more");
    expect(applyHtmlChange(editor, editor.getHTML())).toBeNull();
    editor.destroy();
  });

  it("labels carets by where the edit came from", () => {
    expect(caretLabel({ name: "Ana", via: "agent", viaLabel: "AI agent" })).toBe("Ana · via AI agent");
    expect(caretLabel({ name: "Ana", via: "app", viaLabel: "Manifest" })).toBe("Ana");
  });
});

describe("livePeople", () => {
  it("lists everyone else once, plus recent agent and CLI editors", () => {
    const snapshot: LiveSnapshot = {
      status: "live",
      canEdit: true,
      ready: true,
      error: null,
      self: peer("me", "Me"),
      peers: [peer("me", "Me"), peer("b", "Bo"), { ...peer("b", "Bo"), clientId: 2 }],
      external: [
        { userId: "c", name: "Cy", avatarUrl: null, color: "#000", via: "cli", viaLabel: "CLI", until: 1 },
      ],
    };
    const people = livePeople(snapshot);
    expect(people.map((p) => p.name)).toEqual(["Bo", "Cy"]);
    expect(people[1]).toMatchObject({ badge: ">_", detail: "Just edited via CLI" });
  });
});

describe("changedEnd", () => {
  it("puts the caret after an appended paragraph even when the endings match", () => {
    const editor = new Editor({ extensions: [StarterKit], content: "<p>Gabe typed this.</p>" });
    const before = editor.state.doc;
    editor.commands.setContent("<p>Gabe typed this.</p><p>Added by the agent.</p>");
    const after = editor.state.doc;
    const pos = changedEnd(before, after)!;
    expect(after.textBetween(0, pos, "\n")).toBe("Gabe typed this.\nAdded by the agent.");
    editor.destroy();
  });
});
