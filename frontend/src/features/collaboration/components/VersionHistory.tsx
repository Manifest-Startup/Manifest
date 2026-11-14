import React, { useState } from "react";
import { useMutation, useQuery } from "@apollo/client/react";

import Button from "features/common-ui/Button";
import Input from "features/common-ui/Input";
import { CREATE_IDEA_VERSION, GET_IDEA_VERSIONS, RESTORE_IDEA_VERSION } from "features/core/apollo/queries";
import { useMessage } from "features/notifications/context/MessageContext";
import type { IdeaVersion as Version } from "features/core/apollo/operationTypes";

function versionKindLabel(kind: string | null | undefined): string | null {
  const k = (kind || "manual").toLowerCase();
  if (k === "auto") return "Auto";
  if (k === "system") return "System";
  if (k === "manual") return "Named";
  return null;
}

interface VersionHistoryProps {
  ideaId: string;
  isOpen: boolean;
  onClose: () => void;
  onVersionRestored?: () => void;
}

export const VersionHistory: React.FC<VersionHistoryProps> = ({ ideaId, isOpen, onClose, onVersionRestored }) => {
  const [changeSummary, setChangeSummary] = useState("");
  const { setMessage } = useMessage();

  const { data, loading, refetch } = useQuery(GET_IDEA_VERSIONS, {
    variables: { ideaId },
    skip: !isOpen,
  });

  const [createVersion, { loading: creating }] = useMutation(CREATE_IDEA_VERSION);
  const [restoreVersion, { loading: restoring }] = useMutation(RESTORE_IDEA_VERSION);

  const versions: Version[] = data?.ideaVersions || [];

  const handleCreateVersion = async () => {
    try {
      await createVersion({
        variables: { ideaId, changeSummary: changeSummary || undefined },
      });
      setMessage("Version saved", "success");
      setChangeSummary("");
      refetch();
    } catch (error: any) {
      setMessage(error.message || "Failed to create version", "error");
    }
  };

  const handleRestore = async (version: Version) => {
    if (!confirm(`Restore to version ${version.versionNumber}? This will create a backup of the current version first.`)) {
      return;
    }

    try {
      await restoreVersion({
        variables: { ideaId, versionId: version.versionId },
      });
      setMessage(`Restored to version ${version.versionNumber}`, "success");
      refetch();
      onVersionRestored?.();
    } catch (error: any) {
      setMessage(error.message || "Failed to restore version", "error");
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);

    if (minutes < 1) return "Just now";
    if (minutes < 60) return `${minutes}m ago`;
    if (hours < 24) return `${hours}h ago`;
    if (days < 7) return `${days}d ago`;

    return date.toLocaleDateString();
  };

  if (!isOpen) {
    return null;
  }

  return (
    <div className="manifest-modal-backdrop">
      <div className="manifest-modal" role="dialog" aria-modal="true" aria-labelledby="version-history-modal-title">
        <div className="manifest-modal-header">
          <div>
            <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">Version Control</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-neutral900 dark:text-white" id="version-history-modal-title">
              Version History
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
          <div className="manifest-panel-muted p-4 space-y-3">
            <p className="text-sm text-gray500 dark:text-gray400">
              Versions are saved automatically while you edit (checkpoints about every minute and a half). Add a named
              milestone with the button below when you want an easy-to-find checkpoint.
            </p>
            <div className="flex flex-col gap-3 md:flex-row">
              <Input
                type="text"
                value={changeSummary}
                onChange={(event) => setChangeSummary(event.target.value)}
                placeholder="Version note (optional)"
                className="flex-1"
              />
              <Button variant="primary" onClick={handleCreateVersion} disabled={creating} className="md:h-12 md:self-end">
                {creating ? "Saving..." : "Save Version"}
              </Button>
            </div>
          </div>

          <section>
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-[0.14em] text-gray500 dark:text-gray400">Saved Versions</h3>

            {loading ? (
              <div className="manifest-empty px-5 py-8 text-center text-sm">Loading...</div>
            ) : versions.length === 0 ? (
              <div className="manifest-empty px-5 py-8 text-center">
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-lg bg-white/85 shadow-none dark:bg-neutral800">
                  <svg className="h-6 w-6 text-accent-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <p className="mt-4 text-sm font-semibold text-neutral900 dark:text-white">No version history yet</p>
                <p className="mt-1 text-sm text-gray500 dark:text-gray400">
                  Keep editing—automatic checkpoints appear here after you change content. Or use Save Version for a named
                  milestone.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {versions.map((version) => (
                  <article className="manifest-card px-4 py-4" key={version.versionId}>
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                      <div className="flex items-center gap-3">
                        <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-accent-50 text-sm font-bold text-accent-600 shadow-none dark:bg-accent-900/40 dark:text-accent-300">
                          v{version.versionNumber}
                        </div>
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="text-sm font-semibold text-neutral900 dark:text-white">
                              {version.changeSummary || `Version ${version.versionNumber}`}
                            </p>
                            {versionKindLabel(version.versionKind) ? (
                              <span className="rounded-full bg-white/90 px-2 py-0.5 text-[0.65rem] font-semibold uppercase tracking-wide text-gray600 shadow-sm dark:bg-neutral800 dark:text-gray300">
                                {versionKindLabel(version.versionKind)}
                              </span>
                            ) : null}
                          </div>
                          <p className="mt-1 text-sm text-gray500 dark:text-gray400">
                            {version.creatorName || "Unknown"} • {formatDate(version.createdAt)}
                          </p>
                        </div>
                      </div>

                      <Button variant="secondary" onClick={() => handleRestore(version)} disabled={restoring}>
                        Restore
                      </Button>
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

export default VersionHistory;
