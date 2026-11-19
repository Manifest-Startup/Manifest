/**
 * Answers the app's GraphQL operations from the local vault (ADR 0011), so every screen
 * works unchanged on top of a folder of Markdown files.
 *
 * Root fields the vault understands are resolved by the store; the selection set is then
 * walked so each answer has exactly the shape the query asked for (aliases, fragments,
 * `__typename`). Queries the vault doesn't serve come back empty; mutations that need a
 * Manifest account fail with a clear "turn on Cloud sync" message.
 */
import type {
  DocumentNode,
  FieldNode,
  FragmentDefinitionNode,
  OperationDefinitionNode,
  SelectionSetNode,
} from "graphql";
import { valueFromASTUntyped } from "graphql";
import { LOCAL_USER_ID, type VaultStore } from "./store";

export const CLOUD_SYNC_OFF = "CLOUD_SYNC_OFF";
export const cloudOnlyMessage = (what: string) =>
  `${what} needs Cloud sync. Your ideas are in a local folder; turn on Cloud sync in Settings to share, collaborate and publish.`;

type Args = Record<string, unknown>;
type Resolver = (args: Args) => unknown | Promise<unknown>;

const typed = (typename: string, value: unknown) =>
  value && typeof value === "object" ? { __typename: typename, ...(value as object) } : value;

/** Lists the UI maps over: answer with [] instead of null. */
const EMPTY_LISTS = new Set([
  "ideaVersions",
  "ideaCollaborators",
  "myCollaborationInvitations",
  "mySharedIdeas",
  "integrations",
  "myConversations",
  "partnerCandidates",
  "patents",
  "myIdeaQualificationSessions",
  "ideaInvestments",
  "pitchReelsFeed",
]);

export function rootResolvers(store: VaultStore): { query: Record<string, Resolver>; mutation: Record<string, Resolver> } {
  return {
    query: {
      profile: () => ({ __typename: "Profile", userId: LOCAL_USER_ID, id: LOCAL_USER_ID, email: null, isGuest: false }),
      ideas: async () => (await store.list()).map((idea) => typed("IdeaSummary", idea)),
      idea: async ({ ideaId }) => typed("Idea", await store.get(String(ideaId), true)),
      ideaKnowledgeGraph: () => null,
      ideaVersions: async ({ ideaId }) =>
        (await store.versions(String(ideaId))).map((v) => typed("IdeaVersion", v)),
      unreadMessageCount: () => 0,
    },
    mutation: {
      createIdea: async ({ title, description }) =>
        typed("Idea", await store.create(String(title ?? ""), description ? String(description) : "")),
      updateIdea: async ({ ideaId, title, description, requiredSkills }) =>
        typed(
          "Idea",
          await store.update(String(ideaId), {
            title: title as string | null,
            description: description as string | null,
            requiredSkills: requiredSkills as string[] | null,
          }),
        ),
      createIdeaVersion: async ({ ideaId, changeSummary }) =>
        typed("IdeaVersion", await store.saveVersion(String(ideaId), changeSummary as string | null)),
      restoreIdeaVersion: async ({ ideaId, versionId }) => {
        await store.restoreVersion(String(ideaId), String(versionId));
        return true;
      },
      deleteIdea: async ({ ideaId }) => {
        await store.remove(String(ideaId));
        return true;
      },
    },
  };
}

function project(
  value: unknown,
  selection: SelectionSetNode | undefined,
  fragments: Map<string, FragmentDefinitionNode>,
): unknown {
  if (value === undefined || value === null) return null;
  if (Array.isArray(value)) return value.map((item) => project(item, selection, fragments));
  if (!selection || typeof value !== "object") return value;
  const source = value as Record<string, unknown>;
  const out: Record<string, unknown> = {};
  for (const node of selection.selections) {
    if (node.kind === "Field") {
      const key = node.alias?.value ?? node.name.value;
      const raw = node.name.value === "__typename" ? source.__typename ?? null : source[node.name.value];
      out[key] = project(raw, node.selectionSet, fragments);
    } else if (node.kind === "FragmentSpread") {
      const fragment = fragments.get(node.name.value);
      if (fragment) Object.assign(out, project(source, fragment.selectionSet, fragments));
    } else {
      Object.assign(out, project(source, node.selectionSet, fragments));
    }
  }
  return out;
}

function argsOf(field: FieldNode, variables: Args): Args {
  const args: Args = {};
  for (const arg of field.arguments ?? []) args[arg.name.value] = valueFromASTUntyped(arg.value, variables);
  return args;
}

export interface ExecutionResult {
  data: Record<string, unknown> | null;
  errors?: { message: string; path?: string[]; extensions?: Record<string, unknown> }[];
}

export async function executeOnVault(
  store: VaultStore,
  document: DocumentNode,
  variables: Args = {},
  operationName?: string,
): Promise<ExecutionResult> {
  const operations = document.definitions.filter(
    (d): d is OperationDefinitionNode => d.kind === "OperationDefinition",
  );
  const operation = operations.find((op) => !operationName || op.name?.value === operationName) ?? operations[0];
  const fragments = new Map(
    document.definitions
      .filter((d): d is FragmentDefinitionNode => d.kind === "FragmentDefinition")
      .map((d) => [d.name.value, d]),
  );
  if (!operation) return { data: null, errors: [{ message: "No operation to run" }] };
  const resolvers = rootResolvers(store);
  const table = operation.operation === "mutation" ? resolvers.mutation : resolvers.query;
  const data: Record<string, unknown> = {};
  const errors: ExecutionResult["errors"] = [];
  for (const node of operation.selectionSet.selections) {
    if (node.kind !== "Field") continue;
    const name = node.name.value;
    const key = node.alias?.value ?? name;
    if (name === "__typename") {
      data[key] = operation.operation === "mutation" ? "Mutation" : "Query";
      continue;
    }
    const resolver = table[name];
    if (!resolver) {
      if (operation.operation === "mutation") {
        errors.push({ message: cloudOnlyMessage("This"), path: [key], extensions: { code: CLOUD_SYNC_OFF } });
        data[key] = null;
      } else {
        data[key] = EMPTY_LISTS.has(name) ? [] : null;
      }
      continue;
    }
    try {
      data[key] = project(await resolver(argsOf(node, variables)), node.selectionSet, fragments);
    } catch (error) {
      errors.push({ message: error instanceof Error ? error.message : String(error), path: [key] });
      data[key] = null;
    }
  }
  return errors.length ? { data, errors } : { data };
}
