import React from "react";
import { useMutation } from "@apollo/client/react";
import { Link } from "react-router-dom";

import { REQUEST_PASSWORD_RESET } from "features/core/apollo/queries";
import { createLogger } from "features/core/logError";
import { useMessage } from "features/notifications/context/MessageContext";
import Button from "features/common-ui/Button";
import Input from "features/common-ui/Input";
import { useFormState } from "features/common-ui/hooks/formHooks";

const logger = createLogger("ForgotPasswordPage");

const ForgotPasswordPage: React.FC = () => {
  const { formData, updateField } = useFormState<{ email: string }>({ email: "" });
  const { setMessage } = useMessage();
  const [requestReset, { loading }] = useMutation(REQUEST_PASSWORD_RESET);
  const [submitted, setSubmitted] = React.useState(false);
  const [serverMessage, setServerMessage] = React.useState<string>("");

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const email = formData.email.trim();
    if (!email) {
      setMessage("Please enter your email address.", "error");
      return;
    }
    try {
      const { data } = await requestReset({ variables: { email } });
      const message =
        data?.requestPasswordReset?.message ||
        "If an account with that email exists, we've sent a password reset link.";
      setServerMessage(message);
      setSubmitted(true);
    } catch (error: unknown) {
      logger.error("Password reset request failed:", error);
      // Preserve generic UX even on transient errors so we don't leak signal.
      setServerMessage(
        "If an account with that email exists, we've sent a password reset link.",
      );
      setSubmitted(true);
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
              Forgot your password?
            </h1>
            <p className="mt-3 text-sm text-gray600 dark:text-gray300">
              Enter the email associated with your account and we'll send you a link to
              choose a new password. The link expires in 30 minutes.
            </p>

            {submitted ? (
              <div className="mt-6 rounded-lg border border-stone200 bg-stone50 px-4 py-5 text-sm text-neutral900 dark:border-neutral700 dark:bg-neutral800 dark:text-white">
                <p className="font-semibold">Check your inbox</p>
                <p className="mt-2 text-gray600 dark:text-gray300">{serverMessage}</p>
                <p className="mt-3 text-xs text-gray500 dark:text-gray400">
                  Didn't receive anything? Check your spam folder, or try again in a few minutes.
                </p>
                <div className="mt-5 flex flex-wrap gap-3">
                  <Link
                    to="/auth"
                    className="text-sm font-semibold text-accent-600 hover:text-accent-700 dark:text-accent-300 dark:hover:text-accent-200"
                  >
                    Back to sign in
                  </Link>
                  <button
                    type="button"
                    onClick={() => setSubmitted(false)}
                    className="text-sm font-semibold text-gray600 hover:text-neutral900 dark:text-gray300 dark:hover:text-white"
                  >
                    Use a different email
                  </button>
                </div>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="mt-6 space-y-4">
                <Input
                  type="email"
                  name="email"
                  label="Email address"
                  placeholder="you@example.com"
                  value={formData.email}
                  onChange={(event) => updateField("email", event.target.value)}
                  autoComplete="email"
                  required
                />
                <Button
                  type="submit"
                  disabled={loading}
                  variant="primary"
                  className="w-full justify-center py-3"
                >
                  {loading ? "Sending..." : "Send reset link"}
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
            )}
          </section>
        </div>
      </div>
    </div>
  );
};

export default ForgotPasswordPage;
