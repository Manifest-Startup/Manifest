import React from "react";
import { useMutation, useQuery } from "@apollo/client/react";

import { GET_MY_COLLABORATION_INVITATIONS, RESPOND_TO_INVITATION } from "features/core/apollo/queries";
import { useMessage } from "features/notifications/context/MessageContext";
import type { CollaborationInvitation as Invitation } from "features/core/apollo/operationTypes";

export const CollaborationInvitations: React.FC = () => {
  const { setMessage } = useMessage();

  const { data, loading, refetch } = useQuery(GET_MY_COLLABORATION_INVITATIONS, {
    pollInterval: 30000,
  });

  const [respondToInvitation] = useMutation(RESPOND_TO_INVITATION);

  const invitations: Invitation[] = data?.myCollaborationInvitations || [];

  const handleRespond = async (ideaId: string, accept: boolean) => {
    try {
      await respondToInvitation({
        variables: { ideaId, accept },
      });
      setMessage(accept ? "Invitation accepted" : "Invitation declined", "success");
      refetch();
    } catch (error: any) {
      setMessage(error.message || "Failed to respond", "error");
    }
  };

  if (loading || invitations.length === 0) {
    return null;
  }

  return (
    <section className="manifest-panel-muted mb-4 p-4 sm:p-5">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">Collaboration</p>
          <h3 className="mt-2 text-lg font-semibold tracking-[-0.02em] text-neutral900 dark:text-white">Collaboration Invitations</h3>
          <p className="mt-1 text-sm text-gray500 dark:text-gray400">Review pending idea access requests and keep your workspace secure.</p>
        </div>
        <span className="manifest-pill">{invitations.length} pending</span>
      </div>

      <div className="mt-4 space-y-3">
        {invitations.map((invitation) => (
          <article className="manifest-card px-4 py-4" key={invitation.collaboratorId}>
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <p className="text-sm font-semibold text-neutral900 dark:text-white">{invitation.ideaTitle || "Untitled Idea"}</p>
                <p className="mt-1 text-sm text-gray500 dark:text-gray400">
                  {invitation.inviterName || "Someone"} invited you as {invitation.role}
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => handleRespond(invitation.ideaId, false)}
                  className="rounded-2xl border border-stone200 bg-white/90 px-4 py-2.5 text-sm font-semibold text-neutral900 shadow-none hover:bg-stone50 dark:hover:bg-neutral800 dark:border-neutral700 dark:bg-neutral900/84 dark:text-white"
                >
                  Decline
                </button>
                <button
                  onClick={() => handleRespond(invitation.ideaId, true)}
                  className="rounded-2xl bg-neutral900 px-4 py-2.5 text-sm font-semibold text-white shadow-none hover:bg-stone50 dark:hover:bg-neutral800 dark:bg-white dark:text-neutral900"
                >
                  Accept
                </button>
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
};

export default CollaborationInvitations;
