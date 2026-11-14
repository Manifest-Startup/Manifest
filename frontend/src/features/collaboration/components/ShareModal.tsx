import React, { useState } from "react";
import { useMutation, useQuery } from "@apollo/client/react";

import Button from "features/common-ui/Button";
import Input from "features/common-ui/Input";
import {
  GET_IDEA_COLLABORATORS,
  INVITE_COLLABORATOR,
  REMOVE_COLLABORATOR,
  UPDATE_COLLABORATOR_ROLE,
} from "features/core/apollo/queries";
import { resolveBackendAssetUrl } from "features/core/network/urls";
import { useMessage } from "features/notifications/context/MessageContext";
import type { Collaborator } from "features/core/apollo/operationTypes";

interface ShareModalProps {
  ideaId: string;
  isOpen: boolean;
  onClose: () => void;
}

const ROLE_OPTIONS = [
  { value: "viewer", label: "Viewer", description: "Can view only" },
  { value: "commenter", label: "Commenter", description: "Can view and comment" },
  { value: "editor", label: "Editor", description: "Can view and edit" },
];

export const ShareModal: React.FC<ShareModalProps> = ({ ideaId, isOpen, onClose }) => {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("viewer");
  const { setMessage } = useMessage();

  const { data, loading, refetch } = useQuery(GET_IDEA_COLLABORATORS, {
    variables: { ideaId },
    skip: !isOpen,
  });

  const [inviteCollaborator, { loading: inviting }] = useMutation(INVITE_COLLABORATOR);
  const [updateRole] = useMutation(UPDATE_COLLABORATOR_ROLE);
  const [removeCollaborator] = useMutation(REMOVE_COLLABORATOR);

  const collaborators: Collaborator[] = data?.ideaCollaborators || [];

  const handleInvite = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!email.trim()) {
      return;
    }

    try {
      const result = await inviteCollaborator({
        variables: {
          input: { ideaId, email: email.trim(), role },
        },
      });

      if (result.data?.inviteCollaborator?.success) {
        setMessage(result.data.inviteCollaborator.message, "success");
        setEmail("");
        refetch();
      } else {
        setMessage(result.data?.inviteCollaborator?.message || "Failed to invite", "error");
      }
    } catch (error: any) {
      setMessage(error.message || "Failed to invite collaborator", "error");
    }
  };

  const handleRoleChange = async (userId: string, newRole: string) => {
    try {
      await updateRole({
        variables: { ideaId, targetUserId: userId, newRole },
      });
      setMessage("Role updated", "success");
      refetch();
    } catch (error: any) {
      setMessage(error.message || "Failed to update role", "error");
    }
  };

  const handleRemove = async (userId: string, userName: string) => {
    if (!window.confirm(`Remove ${userName || "this collaborator"} from this idea?`)) {
      return;
    }

    try {
      await removeCollaborator({
        variables: { ideaId, targetUserId: userId },
      });
      setMessage("Collaborator removed", "success");
      refetch();
    } catch (error: any) {
      setMessage(error.message || "Failed to remove collaborator", "error");
    }
  };

  if (!isOpen) {
    return null;
  }

  return (
    <div className="manifest-modal-backdrop">
      <div className="manifest-modal" role="dialog" aria-modal="true" aria-labelledby="share-idea-modal-title">
        <div className="manifest-modal-header">
          <div>
            <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">Collaboration</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-neutral900 dark:text-white" id="share-idea-modal-title">
              Share Idea
            </h2>
          </div>
          <button
            onClick={onClose}
            data-testid="close-modal"
            aria-label="Close"
            className="rounded-2xl p-2 text-gray500 hover:bg-white/70 hover:text-neutral900 dark:hover:bg-neutral800 dark:hover:text-white"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="manifest-modal-body space-y-5">
          <form onSubmit={handleInvite} className="manifest-panel-muted space-y-4 p-4">
            <div className="flex flex-col gap-3 md:flex-row">
              <Input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="Enter email address"
                className="flex-1"
              />
              <select
                value={role}
                onChange={(event) => setRole(event.target.value)}
                className="h-12 rounded-2xl border border-stone200 bg-white/90 px-4 text-sm font-semibold text-neutral900 outline-none focus:border-accent-400 focus:ring-4 focus:ring-accent-100 dark:border-neutral700 dark:bg-neutral900/90 dark:text-white dark:focus:border-accent-300 dark:focus:ring-accent-900/30"
              >
                {ROLE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="manifest-card px-4 py-4">
              <p className="text-sm font-semibold text-neutral900 dark:text-white">
                {ROLE_OPTIONS.find((option) => option.value === role)?.label}
              </p>
              <p className="mt-1 text-sm text-gray500 dark:text-gray400">
                {ROLE_OPTIONS.find((option) => option.value === role)?.description}
              </p>
            </div>

            <Button type="submit" variant="primary" className="w-full" disabled={inviting || !email.trim()}>
              {inviting ? "Sending..." : "Send Invite"}
            </Button>
          </form>

          <section>
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-gray500 dark:text-gray400">People with access</h3>
              </div>
            </div>

            {loading ? (
              <div className="manifest-empty px-5 py-8 text-center text-sm">Loading...</div>
            ) : (
              <div className="space-y-3">
                {collaborators.map((collaborator) => (
                  <article className="manifest-card px-4 py-4" key={collaborator.userId}>
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                      <div className="flex items-center gap-3">
                        {collaborator.userAvatar ? (
                          <img
                            src={resolveBackendAssetUrl(collaborator.userAvatar)}
                            alt={collaborator.userName || ""}
                            className="h-11 w-11 rounded-lg object-cover shadow-none"
                          />
                        ) : (
                          <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-neutral900 text-sm font-bold text-white shadow-none">
                            {(collaborator.userName || collaborator.userEmail || "U")[0].toUpperCase()}
                          </div>
                        )}

                        <div>
                          <p className="text-sm font-semibold text-neutral900 dark:text-white">
                            {collaborator.userName || collaborator.userEmail || "Unknown"}
                          </p>
                          <div className="mt-1 flex flex-wrap gap-2">
                            <span className="manifest-pill">
                              {collaborator.status === "pending" ? "Pending invite" : collaborator.role}
                            </span>
                            {collaborator.role === "owner" ? <span className="manifest-pill">Owner</span> : null}
                          </div>
                        </div>
                      </div>

                      {collaborator.role !== "owner" ? (
                        <div className="flex flex-col gap-2 sm:flex-row">
                          <select
                            value={collaborator.role}
                            onChange={(event) => handleRoleChange(collaborator.userId, event.target.value)}
                            className="h-11 rounded-2xl border border-stone200 bg-white/90 px-4 text-sm font-semibold text-neutral900 outline-none focus:border-accent-400 focus:ring-4 focus:ring-accent-100 dark:border-neutral700 dark:bg-neutral900/90 dark:text-white dark:focus:border-accent-300 dark:focus:ring-accent-900/30"
                          >
                            {ROLE_OPTIONS.map((option) => (
                              <option key={option.value} value={option.value}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                          <Button variant="ghost" onClick={() => handleRemove(collaborator.userId, collaborator.userName || "")}>
                            Remove
                          </Button>
                        </div>
                      ) : null}
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
};

export default ShareModal;
