import React from "react";
import { useMutation, useQuery } from "@apollo/client/react";

import Button from "features/common-ui/Button";
import Input from "features/common-ui/Input";
import {
  BEGIN_TOTP_SETUP,
  DISABLE_TOTP,
  ENABLE_TOTP,
  GET_MFA_STATUS,
  GET_MY_SESSIONS,
  REVOKE_ACCOUNT_SESSION,
  REVOKE_OTHER_ACCOUNT_SESSIONS,
} from "features/core/apollo/queries";
import { useMessage } from "features/notifications/context/MessageContext";
import type { TotpSetup, SessionInfo } from "features/core/apollo/operationTypes";

const formatSessionDate = (value?: string | null) => {
  if (!value) {
    return "Unavailable";
  }
  return new Date(value).toLocaleString();
};

const SecuritySettingsPanel: React.FC = () => {
  const { setMessage } = useMessage();
  const { data: mfaData, loading: mfaLoading, refetch: refetchMfa } = useQuery(GET_MFA_STATUS);
  const { data: sessionsData, loading: sessionsLoading, refetch: refetchSessions } = useQuery(GET_MY_SESSIONS);
  const [beginTotpSetup, { loading: setupLoading }] = useMutation(BEGIN_TOTP_SETUP);
  const [enableTotp, { loading: enableLoading }] = useMutation(ENABLE_TOTP);
  const [disableTotp, { loading: disableLoading }] = useMutation(DISABLE_TOTP);
  const [revokeSession, { loading: revokeLoading }] = useMutation(REVOKE_ACCOUNT_SESSION);
  const [revokeOtherSessions, { loading: revokeOthersLoading }] = useMutation(REVOKE_OTHER_ACCOUNT_SESSIONS);

  const [setupPassword, setSetupPassword] = React.useState("");
  const [verificationCode, setVerificationCode] = React.useState("");
  const [disableCode, setDisableCode] = React.useState("");
  const [disablePassword, setDisablePassword] = React.useState("");
  const [totpSetup, setTotpSetup] = React.useState<TotpSetup | null>(null);

  const mfaStatus = mfaData?.mfaStatus;
  const sessions: SessionInfo[] = sessionsData?.mySessions || [];

  const handleBeginSetup = async () => {
    try {
      const { data } = await beginTotpSetup({ variables: { password: setupPassword || null } });
      setTotpSetup(data?.beginTotpSetup ?? null);
      setVerificationCode("");
      setMessage("Authenticator setup started. Add the secret to your authenticator app, then verify with a code.", "success");
    } catch (error: any) {
      setMessage(error?.message || "Could not start MFA setup.", "error");
    }
  };

  const handleEnable = async () => {
    if (!totpSetup) {
      return;
    }
    try {
      await enableTotp({
        variables: {
          secret: totpSetup.secret,
          code: verificationCode,
          recoveryCodes: totpSetup.recoveryCodes,
        },
      });
      setTotpSetup(null);
      setSetupPassword("");
      setVerificationCode("");
      await refetchMfa();
      setMessage("Multi-factor authentication is now enabled.", "success");
    } catch (error: any) {
      setMessage(error?.message || "Could not enable MFA.", "error");
    }
  };

  const handleDisable = async () => {
    try {
      await disableTotp({ variables: { code: disableCode, password: disablePassword || null } });
      setDisableCode("");
      setDisablePassword("");
      await refetchMfa();
      setMessage("Multi-factor authentication has been disabled.", "success");
    } catch (error: any) {
      setMessage(error?.message || "Could not disable MFA.", "error");
    }
  };

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
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-sm font-semibold text-neutral900 dark:text-white">Authenticator app</p>
            <p className="mt-1 text-sm leading-6 text-gray500 dark:text-gray400">
              Protect your account with a 6-digit code from Google Authenticator, 1Password, or another TOTP app.
            </p>
            {mfaStatus?.enabled ? (
              <p className="mt-3 text-sm font-medium text-green-600 dark:text-green-400">
                Enabled {mfaStatus.enabledAt ? `on ${new Date(mfaStatus.enabledAt).toLocaleDateString()}` : ""}
                {typeof mfaStatus.recoveryCodesRemaining === "number"
                  ? ` · ${mfaStatus.recoveryCodesRemaining} recovery codes left`
                  : ""}
              </p>
            ) : (
              <p className="mt-3 text-sm font-medium text-amber-600 dark:text-amber-400">Not enabled yet</p>
            )}
          </div>
          {!mfaStatus?.enabled ? (
            <div className="w-full max-w-sm space-y-3">
              <Input
                type="password"
                label="Current password"
                placeholder="Required for password accounts"
                value={setupPassword}
                onChange={(event) => setSetupPassword(event.target.value)}
              />
              <Button type="button" variant="primary" onClick={handleBeginSetup} disabled={setupLoading || mfaLoading}>
                {setupLoading ? "Preparing..." : "Set up MFA"}
              </Button>
            </div>
          ) : (
            <div className="w-full max-w-sm space-y-3">
              <Input
                type="text"
                label="Current MFA code or recovery code"
                placeholder="123456"
                value={disableCode}
                onChange={(event) => setDisableCode(event.target.value)}
              />
              <Input
                type="password"
                label="Current password"
                placeholder="Required for password accounts"
                value={disablePassword}
                onChange={(event) => setDisablePassword(event.target.value)}
              />
              <Button type="button" variant="secondary" onClick={handleDisable} disabled={disableLoading}>
                {disableLoading ? "Disabling..." : "Disable MFA"}
              </Button>
            </div>
          )}
        </div>
        {totpSetup ? (
          <div className="mt-5 grid gap-4 rounded-lg border border-stone200 bg-stone50 px-4 py-4 dark:border-neutral700 dark:bg-neutral900/40">
            <div>
              <p className="text-sm font-semibold text-neutral900 dark:text-white">Step 1: Add this secret to your authenticator app</p>
              <code className="mt-2 block break-all rounded-xl bg-neutral900 px-4 py-3 text-xs text-white">{totpSetup.secret}</code>
              <p className="mt-2 text-xs leading-6 text-gray500 dark:text-gray400">Manual setup URI: {totpSetup.otpAuthUrl}</p>
            </div>
            <div>
              <p className="text-sm font-semibold text-neutral900 dark:text-white">Step 2: Save your recovery codes</p>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {totpSetup.recoveryCodes.map((code) => (
                  <code key={code} className="rounded-xl bg-white px-3 py-2 text-xs text-neutral900 dark:bg-neutral800 dark:text-white">
                    {code}
                  </code>
                ))}
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
              <Input
                type="text"
                label="Step 3: Verify with a 6-digit code"
                placeholder="123456"
                value={verificationCode}
                onChange={(event) => setVerificationCode(event.target.value)}
              />
              <Button type="button" variant="primary" onClick={handleEnable} disabled={enableLoading || verificationCode.trim().length < 6}>
                {enableLoading ? "Verifying..." : "Enable MFA"}
              </Button>
            </div>
          </div>
        ) : null}
      </div>

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
                      {session.current ? "Current session" : "Browser session"}
                    </p>
                    {session.current ? <span className="manifest-pill">Current</span> : null}
                  </div>
                  <p className="mt-1 text-xs leading-5 text-gray500 dark:text-gray400">{session.userAgent || "User agent unavailable"}</p>
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
