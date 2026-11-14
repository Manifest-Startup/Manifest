"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.EXTENSION_SOURCE = void 0;
exports.getWorkspaceRoot = getWorkspaceRoot;
exports.getTaskSpec = getTaskSpec;
exports.createTask = createTask;
exports.openMcpSetup = openMcpSetup;
exports.runTaskById = runTaskById;
exports.activate = activate;
exports.deactivate = deactivate;
const path = __importStar(require("node:path"));
const vscode = __importStar(require("vscode"));
exports.EXTENSION_SOURCE = "Manifest Dev";
function getWorkspaceRoot() {
    return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
}
function getTaskSpec(root, taskId) {
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
function createTask(spec) {
    const definition = {
        type: "shell",
        task: spec.id
    };
    const execution = new vscode.ShellExecution(spec.command, { cwd: spec.cwd });
    return new vscode.Task(definition, vscode.TaskScope.Workspace, spec.label, exports.EXTENSION_SOURCE, execution);
}
async function requireWorkspaceRoot() {
    const root = getWorkspaceRoot();
    if (!root) {
        await vscode.window.showErrorMessage("Open the Manifest repository in a workspace before using Manifest Dev commands.");
        return undefined;
    }
    return root;
}
async function openMcpSetup() {
    const root = await requireWorkspaceRoot();
    if (!root) {
        return;
    }
    const readmePath = path.join(root, "mcp_server", "README.md");
    const document = await vscode.workspace.openTextDocument(vscode.Uri.file(readmePath));
    await vscode.window.showTextDocument(document);
}
async function runTaskById(taskId) {
    const root = await requireWorkspaceRoot();
    if (!root) {
        return;
    }
    const task = createTask(getTaskSpec(root, taskId));
    await vscode.tasks.executeTask(task);
}
function activate(context) {
    const register = (command, callback) => {
        context.subscriptions.push(vscode.commands.registerCommand(command, callback));
    };
    register("manifestDev.openMcpSetup", openMcpSetup);
    register("manifestDev.startBackend", () => runTaskById("startBackend"));
    register("manifestDev.startFrontend", () => runTaskById("startFrontend"));
    register("manifestDev.startFullStack", () => runTaskById("startFullStack"));
}
function deactivate() { }
//# sourceMappingURL=extension.js.map