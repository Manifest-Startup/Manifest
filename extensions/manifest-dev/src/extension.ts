import * as path from "node:path";
import * as vscode from "vscode";

export const EXTENSION_SOURCE = "Manifest Dev";

export type ManifestTaskId = "startBackend" | "startFrontend" | "startFullStack";

export interface ManifestTaskSpec {
  id: ManifestTaskId;
  label: string;
  command: string;
  cwd: string;
}

export function getWorkspaceRoot(): string | undefined {
  return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
}

export function getTaskSpec(root: string, taskId: ManifestTaskId): ManifestTaskSpec {
  const backendRoot = path.join(root, "backend");
  const frontendRoot = path.join(root, "frontend");

  switch (taskId) {
    case "startBackend":
      return {
        id: taskId,
        label: "Manifest: Start Backend",
        command: `${path.join(root, "backend", ".venv", "bin", "python")} -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`,
        cwd: backendRoot
      };
    case "startFrontend":
      return {
        id: taskId,
        label: "Manifest: Start Frontend",
        command: "npm start",
        cwd: frontendRoot
      };
    case "startFullStack":
      return {
        id: taskId,
        label: "Manifest: Start Full Stack",
        command: "manifest-dev start",
        cwd: root
      };
  }
}

export function createTask(spec: ManifestTaskSpec): vscode.Task {
  const definition: vscode.TaskDefinition = {
    type: "shell",
    task: spec.id
  };
  const execution = new vscode.ShellExecution(spec.command, { cwd: spec.cwd });

  return new vscode.Task(definition, vscode.TaskScope.Workspace, spec.label, EXTENSION_SOURCE, execution);
}

async function requireWorkspaceRoot(): Promise<string | undefined> {
  const root = getWorkspaceRoot();
  if (!root) {
    await vscode.window.showErrorMessage("Open the Manifest repository in a workspace before using Manifest Dev commands.");
    return undefined;
  }
  return root;
}

export async function openMcpSetup(): Promise<void> {
  const root = await requireWorkspaceRoot();
  if (!root) {
    return;
  }

  const readmePath = path.join(root, "mcp_server", "README.md");
  const document = await vscode.workspace.openTextDocument(vscode.Uri.file(readmePath));
  await vscode.window.showTextDocument(document);
}

export async function runTaskById(taskId: ManifestTaskId): Promise<void> {
  const root = await requireWorkspaceRoot();
  if (!root) {
    return;
  }

  const task = createTask(getTaskSpec(root, taskId));
  await vscode.tasks.executeTask(task);
}

export function activate(context: vscode.ExtensionContext): void {
  const register = (command: string, callback: () => Promise<void>) => {
    context.subscriptions.push(vscode.commands.registerCommand(command, callback));
  };

  register("manifestDev.openMcpSetup", openMcpSetup);
  register("manifestDev.startBackend", () => runTaskById("startBackend"));
  register("manifestDev.startFrontend", () => runTaskById("startFrontend"));
  register("manifestDev.startFullStack", () => runTaskById("startFullStack"));
}

export function deactivate(): void {}
