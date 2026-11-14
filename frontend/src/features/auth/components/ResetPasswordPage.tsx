import React from "react";
import { useApolloClient, useMutation } from "@apollo/client/react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { userVar } from "features/core/apollo/localState";
import { RESET_PASSWORD } from "features/core/apollo/queries";
import { createLogger } from "features/core/logError";
import { useMessage } from "features/notifications/context/MessageContext";
import Button from "features/common-ui/Button";
import Input from "features/common-ui/Input";
import { useFormState } from "features/common-ui/hooks/formHooks";
import { safeNavigate } from "utils/safeNavigate";

const logger = createLogger("ResetPasswordPage");

const MIN_PASSWORD_LENGTH = 8;

function passwordStrengthLabel(password: string): { label: string; tone: string } {
  if (!password) return { label: "Enter a password", tone: "text-gray500" };
  if (password.length < MIN_PASSWORD_LENGTH) return { label: "Too short", tone: "text-red500" };
  const hasLower = /[a-z]/.test(password);
  const hasUpper = /[A-Z]/.test(password);
  const hasDigit = /\d/.test(password);
  const hasSymbol = /[^A-Za-z0-9]/.test(password);
  const score = [hasLower, hasUpper, hasDigit, hasSymbol].filter(Boolean).length + (password.length >= 12 ? 1 : 0);
  if (score >= 4) return { label: "Strong", tone: "text-green500" };
  if (score >= 2) return { label: "Okay", tone: "text-amber500" };
  return { label: "Weak", tone: "text-red500" };
}

const ResetPasswordPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") || "";
  const navigate = useNavigate();
  const { setMessage } = useMessage();
  const client = useApolloClient();
  const [resetPassword, { loading }] = useMutation(RESET_PASSWORD);
  const { formData, updateField } = useFormState<{ password: string; confirm: string }>({
    password: "",
    confirm: "",
  });
  const [showPassword, setShowPassword] = React.useState(false);
  const [errorMessage, setErrorMessage] = React.useState<string>("");

  const strength = passwordStrengthLabel(formData.password);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setErrorMessage("");

    if (!token) {
      setErrorMessage("This reset link is missing a token. Please request a new one.");
      return;
    }
    if (formData.password.length < MIN_PASSWORD_LENGTH) {
      setErrorMessage(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    if (formData.password !== formData.confirm) {
      setErrorMessage("Passwords do not match.");
      return;
    }

    try {
      const { data } = await resetPassword({
        variables: { token, newPassword: formData.password },
      });
      const result = data?.resetPassword;
      if (!result) {
        setErrorMessage("Could not reset your password. Please try again.");
        return;
      }
      if (typeof window !== "undefined" && result.token) {
        localStorage.setItem("access_token", result.token);
      }
      userVar({
        isLoggedIn: true,
        isGuest: Boolean(result.isGuest),
        userData: { userId: result.userId, email: result.email },
      });
      try {
        await client.refetchQueries({ include: ["GetProfile", "GetIdeas"] });
      } catch (refetchError) {
        logger.error("Refetch after password reset failed:", refetchError);
      }
      setMessage("Password updated. You're signed in.", "success");
      safeNavigate(navigate, setMessage, "/ideas");
    } catch (error: unknown) {
      logger.error("Password reset failed:", error);
      const err = error as {
        graphQLErrors?: Array<{ message: string }>;
        message?: string;
      };
      const message =
        err?.graphQLErrors?.[0]?.message ||
        err?.message ||
        "This password reset link is invalid or has expired.";
      setErrorMessage(message);
    }
  };

  return (
    <div className="manifest-page">
      <div className="manifest-shell">
        <div className="grid min-h-[calc(100dvh-10rem)] place-items-center">
          <section className="w-full max-w-[440px] py-6">
            <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">
              Account recovery
            </p>
            <h1 className="mt-2 text-[1.6rem] font-semibold tracking-[-0.03em] text-neutral900 dark:text-white">
              Choose a new password
            </h1>
            <p className="mt-3 text-sm text-gray600 dark:text-gray300">
              Pick a password you don't use anywhere else. After you save it, every device
              currently signed in will be signed out.
            </p>

            {!token && (
              <div className="mt-6 rounded-lg border border-red300 bg-red50 px-4 py-4 text-sm text-red700 dark:border-red500/40 dark:bg-red500/10 dark:text-red200">
                This reset link is missing a token.{" "}
                <Link to="/auth/forgot-password" className="font-semibold underline">
                  Request a new link
                </Link>
                .
              </div>
            )}

            <form onSubmit={handleSubmit} className="mt-6 space-y-4">
              <div className="space-y-2">
                <Input
                  type={showPassword ? "text" : "password"}
                  name="password"
                  label="New password"
                  placeholder="At least 8 characters"
                  value={formData.password}
                  onChange={(event) => updateField("password", event.target.value)}
                  autoComplete="new-password"
                  required
                />
                <div className="flex items-center justify-between text-xs">
                  <span className={`font-semibold ${strength.tone}`}>{strength.label}</span>
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    className="font-semibold text-accent-600 hover:text-accent-700 dark:text-accent-300 dark:hover:text-accent-200"
                  >
                    {showPassword ? "Hide" : "Show"}
                  </button>
                </div>
              </div>

              <Input
                type={showPassword ? "text" : "password"}
                name="confirm"
                label="Confirm new password"
                placeholder="Re-enter your new password"
                value={formData.confirm}
                onChange={(event) => updateField("confirm", event.target.value)}
                autoComplete="new-password"
                required
              />

              {errorMessage && (
                <div className="rounded-[14px] border border-red300 bg-red50 px-3 py-2 text-sm text-red700 dark:border-red500/40 dark:bg-red500/10 dark:text-red200">
                  {errorMessage}{" "}
                  {errorMessage.toLowerCase().includes("invalid") ||
                  errorMessage.toLowerCase().includes("expired") ? (
                    <Link
                      to="/auth/forgot-password"
                      className="font-semibold underline"
                    >
                      Request a new link
                    </Link>
                  ) : null}
                </div>
              )}

              <Button
                type="submit"
                disabled={loading || !token}
                variant="primary"
                className="w-full justify-center py-3"
              >
                {loading ? "Updating..." : "Update password and sign in"}
              </Button>

              <div className="pt-2 text-sm">
                <Link
                  to="/auth"
                  className="font-semibold text-accent-600 hover:text-accent-700 dark:text-accent-300 dark:hover:text-accent-200"
                >
                  Back to sign in
                </Link>
              </div>
            </form>
          </section>
        </div>
      </div>
    </div>
  );
};

export default ResetPasswordPage;
