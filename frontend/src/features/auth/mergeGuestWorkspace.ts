import type { ApolloClient } from "@apollo/client";

import { MERGE_GUEST_WORKSPACE } from "features/core/apollo/queries";
import { clearGuestMergeCredentials, readGuestMergeCredentials } from "./guestSessionStorage";

/**
 * After signup/login, move guest-owned ideas to the authenticated account if credentials exist.
 */
export async function mergePendingGuestWorkspace(client: ApolloClient): Promise<number> {
  const creds = readGuestMergeCredentials();
  if (!creds) {
    return 0;
  }

  const { data } = await client.mutate({
    mutation: MERGE_GUEST_WORKSPACE,
    variables: {
      guestUserId: creds.guestUserId,
      mergeSecret: creds.mergeSecret,
    },
  });

  clearGuestMergeCredentials();

  const count = data?.mergeGuestWorkspace?.mergedIdeaCount ?? 0;
  return typeof count === "number" ? count : 0;
}
