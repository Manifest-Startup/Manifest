import React from "react";
import { useMutation, useQuery } from "@apollo/client/react";

import Button from "features/common-ui/Button";
import {
  GET_MY_SESSIONS,
  REVOKE_ACCOUNT_SESSION,
  REVOKE_OTHER_ACCOUNT_SESSIONS,
} from "features/core/apollo/queries";
import { useMessage } from "features/notifications/context/MessageContext";
import type { SessionInfo } from "features/core/apollo/operationTypes";

const formatSessionDate = (value?: string | null) => {
  if (!value) {
    return "Unavailable";
  }
  return new Date(value).toLocaleString();
};

/** Active Manifest sessions. Passkeys, passwords and second factors live in Open Media. */
const SecuritySettingsPanel: React.FC = () => {
  const { setMessage } = useMessage();
  const { data: sessionsData, loading: sessionsLoading, refetch: refetchSessions } = useQuery(GET_MY_SESSIONS);
  const [revokeSession, { loading: revokeLoading }] = useMutation(REVOKE_ACCOUNT_SESSION);
  const [revokeOtherSessions, { loading: revokeOthersLoading }] = useMutation(REVOKE_OTHER_ACCOUNT_SESSIONS);

  const sessions: SessionInfo[] = sessionsData?.mySessions || [];

  const handleRevokeSession = async (sessionId: string) => {
    try {
      await revokeSession({ variables: { sessionId } });
      await refetchSessions();
      setMessage("Session revoked.", "success");
    } catch (error: any) {
      setMessage(error?.message || "Could not revoke that session.", "error");
    }
  };

  const handleRevokeOtherSessions = async () => {
    try {
      const { data } = await revokeOtherSessions();
      await refetchSessions();
      setMessage(`Revoked ${data?.revokeOtherAccountSessions ?? 0} other session(s).`, "success");
    } catch (error: any) {
      setMessage(error?.message || "Could not revoke other sessions.", "error");
    }
  };

  return (
    <div className="space-y-6">
      <div className="manifest-card px-5 py-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-sm font-semibold text-neutral900 dark:text-white">Active sessions</p>
            <p className="mt-1 text-sm leading-6 text-gray500 dark:text-gray400">
              Review where you are signed in and revoke old browsers or devices.
            </p>
          </div>
          <Button type="button" variant="secondary" onClick={handleRevokeOtherSessions} disabled={revokeOthersLoading || sessionsLoading}>
            {revokeOthersLoading ? "Revoking..." : "Revoke other sessions"}
          </Button>
        </div>
        <div className="mt-4 space-y-3">
          {sessions.map((session) => (
            <div
              key={session.sessionId}
              className="rounded-lg border border-stone200 bg-white/90 px-4 py-4 dark:border-neutral700 dark:bg-neutral900/80"
            >
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-semibold text-neutral900 dark:text-white">
                      {session.kind === "cli" || session.kind === "agent"
                        ? session.userAgent || (session.kind === "cli" ? "Manifest CLI" : "AI agent")
                        : session.current
                          ? "Current session"
                          : "Browser session"}
                    </p>
                    {session.current ? <span className="manifest-pill">Current</span> : null}
                  </div>
                  <p className="mt-1 text-xs leading-5 text-gray500 dark:text-gray400">
                    {session.kind === "cli"
                      ? "Command-line access approved in this browser"
                      : session.kind === "agent"
                        ? "AI agent access approved in this browser (MCP). Revoke to disconnect it."
                        : session.userAgent || "User agent unavailable"}
                  </p>
                  <p className="mt-2 text-xs leading-5 text-gray500 dark:text-gray400">
                    Last seen {formatSessionDate(session.lastSeenAt)} · Created {formatSessionDate(session.createdAt)}
                    {session.requestIp ? ` · IP ${session.requestIp}` : ""}
                  </p>
                </div>
                {!session.current ? (
                  <Button type="button" variant="ghost" onClick={() => handleRevokeSession(session.sessionId)} disabled={revokeLoading}>
                    Revoke
                  </Button>
                ) : null}
              </div>
            </div>
          ))}
          {!sessions.length ? (
            <p className="text-sm text-gray500 dark:text-gray400">No active sessions found.</p>
          ) : null}
        </div>
      </div>
    </div>
  );
};

export default SecuritySettingsPanel;
