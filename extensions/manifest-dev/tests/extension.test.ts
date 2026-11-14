import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  executeTask: vi.fn(),
  openTextDocument: vi.fn(),
  showTextDocument: vi.fn(),
  showErrorMessage: vi.fn(),
  registerCommand: vi.fn((_command: string, callback: () => Promise<void>) => ({ callback }))
}));

vi.mock("vscode", () => ({
  workspace: {
    workspaceFolders: [{ uri: { fsPath: "/repo" } }],
    openTextDocument: mocks.openTextDocument
  },
  window: {
    showTextDocument: mocks.showTextDocument,
    showErrorMessage: mocks.showErrorMessage
  },
  tasks: {
    executeTask: mocks.executeTask
  },
  commands: {
    registerCommand: mocks.registerCommand
  },
  ShellExecution: class MockShellExecution {
    commandLine: string;
    options?: { cwd?: string };

    constructor(commandLine: string, options?: { cwd?: string }) {
      this.commandLine = commandLine;
      this.options = options;
    }
  },
  Task: class MockTask {
    definition: Record<string, string>;
    scope: string;
    name: string;
    source: string;
    execution: { commandLine: string; options?: { cwd?: string } };

    constructor(
      definition: Record<string, string>,
      scope: string,
      name: string,
      source: string,
      execution: { commandLine: string; options?: { cwd?: string } }
    ) {
      this.definition = definition;
      this.scope = scope;
      this.name = name;
      this.source = source;
      this.execution = execution;
    }
  },
  TaskScope: {
    Workspace: "workspace"
  },
  Uri: {
    file: (fsPath: string) => ({ fsPath })
  }
}));

import {
  EXTENSION_SOURCE,
  activate,
  createTask,
  getTaskSpec,
  openMcpSetup,
  runTaskById
} from "../src/extension";

describe("Manifest extension", () => {
  beforeEach(() => {
    mocks.executeTask.mockReset();
    mocks.openTextDocument.mockReset();
    mocks.showTextDocument.mockReset();
    mocks.showErrorMessage.mockReset();
    mocks.registerCommand.mockClear();
  });

  it("builds the full-stack task from the workspace root", () => {
    expect(getTaskSpec("/repo", "startFullStack")).toEqual({
      id: "startFullStack",
      label: "Manifest: Start Full Stack",
      command: "manifest-dev start",
      cwd: "/repo"
    });
  });

  it("wraps a task spec into a VS Code shell task", () => {
    const task = createTask(getTaskSpec("/repo", "startFrontend")) as any;

    expect(task.source).toBe(EXTENSION_SOURCE);
    expect(task.name).toBe("Manifest: Start Frontend");
    expect(task.execution.commandLine).toBe("npm start");
    expect(task.execution.options?.cwd).toBe("/repo/frontend");
  });

  it("opens the MCP setup readme from the repo", async () => {
    mocks.openTextDocument.mockResolvedValue({ uri: { fsPath: "/repo/mcp_server/README.md" } });

    await openMcpSetup();

    expect(mocks.openTextDocument).toHaveBeenCalledWith({ fsPath: "/repo/mcp_server/README.md" });
    expect(mocks.showTextDocument).toHaveBeenCalledTimes(1);
  });

  it("executes the selected Manifest task", async () => {
    await runTaskById("startBackend");

    expect(mocks.executeTask).toHaveBeenCalledTimes(1);
    const task = mocks.executeTask.mock.calls[0][0] as any;
    expect(task.name).toBe("Manifest: Start Backend");
    expect(task.execution.commandLine).toContain("uvicorn");
    expect(task.execution.options?.cwd).toBe("/repo/backend");
  });

  it("registers the extension commands on activate", () => {
    const subscriptions: unknown[] = [];

    activate({ subscriptions } as never);

    expect(mocks.registerCommand).toHaveBeenCalledTimes(4);
    expect(subscriptions).toHaveLength(4);
  });
});
