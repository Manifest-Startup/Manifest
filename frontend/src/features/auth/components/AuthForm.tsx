import React from "react";
import { useApolloClient, useMutation } from "@apollo/client/react";
import { Link, useNavigate } from "react-router-dom";

import { clearLogoutRedirectInProgress } from "features/auth/logout";
import { trackEvent } from "features/analytics/projectAnalytics";
import { userVar } from "features/core/apollo/localState";
import { mergePendingGuestWorkspace } from "features/auth/mergeGuestWorkspace";
import { COMPLETE_GUEST_ACCOUNT_UPGRADE, LOGIN_USER, SIGNUP_USER } from "features/core/apollo/queries";
import { createLogger } from "features/core/logError";
import { useMessage } from "features/notifications/context/MessageContext";
import Button from "features/common-ui/Button";
import Input from "features/common-ui/Input";
import { useFormState } from "features/common-ui/hooks/formHooks";
import { safeNavigate } from "utils/safeNavigate";

const logger = createLogger("AuthForm");

const AuthForm: React.FC = () => {
  logger.log("rendered");

  const { formData, updateField } = useFormState<{ email: string; password: string }>({ email: "", password: "" });
  const [isLogin, setIsLogin] = React.useState(true);
  const [showPassword, setShowPassword] = React.useState(false);
  const navigate = useNavigate();
  const { setMessage, clearMessage } = useMessage();
  const client = useApolloClient();
  const [loginUser, { loading: loginLoading }] = useMutation(LOGIN_USER);
  const [signupUser, { loading: signupLoading }] = useMutation(SIGNUP_USER);
  const [completeGuestUpgrade, { loading: guestUpgradeLoading }] = useMutation(COMPLETE_GUEST_ACCOUNT_UPGRADE);

  const [guestUpgradeToken, setGuestUpgradeToken] = React.useState<string | null>(() => {
    if (typeof window === "undefined") {
      return null;
    }
    try {
      return new URL(window.location.href).searchParams.get("guest_upgrade_token");
    } catch {
      return null;
    }
  });

  const isLoading = loginLoading || signupLoading || guestUpgradeLoading;

  React.useEffect(() => {
    if (clearLogoutRedirectInProgress()) {
      clearMessage();
    }

    const url = new URL(window.location.href);
    const oauthError = url.searchParams.get("oauth_error");

    if (oauthError === "not_configured") {
      setMessage("OAuth login is not configured in this environment. Use email sign-in for local demo access.", "info");
      url.searchParams.delete("oauth_error");
      window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
    }

    if (url.searchParams.has("guest_upgrade_token")) {
      url.searchParams.delete("guest_upgrade_token");
      window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
    }
  }, [clearMessage, setMessage]);

  const handleOAuthLogin = () => {
    logger.log("Redirecting to OAuth login");
    window.location.href = "/auth/login";
  };

  const handleGuestUpgradeSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const { password } = formData;
    if (!guestUpgradeToken) {
      return;
    }
    if (!password || password.length < 8) {
      setMessage("Password must be at least 8 characters.", "error");
      return;
    }
    try {
      const { data } = await completeGuestUpgrade({
        variables: { token: guestUpgradeToken, password },
      });
      const auth = data?.completeGuestAccountUpgrade;
      if (auth?.token) {
        if (typeof window !== "undefined") {
          localStorage.setItem("access_token", auth.token);
        }
        userVar({
          isLoggedIn: true,
          isGuest: false,
          authChecked: true,
          userData: { userId: auth.userId, email: auth.email },
        });
        setGuestUpgradeToken(null);
        await client.refetchQueries({ include: ["GetProfile", "GetIdeas"] });
        setMessage("Welcome to Manifest — your guest workspace is now a full account.", "success");
        trackEvent("auth_completed", {
          method: "password",
          mode: "guest_upgrade",
          guest_upgrade: true,
        });
        safeNavigate(navigate, setMessage, "/ideas");
      }
    } catch (error: unknown) {
      logger.error("Guest upgrade failed:", error);
      const err = error as { graphQLErrors?: Array<{ message: string }>; message?: string };
      const msg = err?.graphQLErrors?.[0]?.message || err?.message || "Could not complete upgrade.";
      setMessage(msg, "error");
    }
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const { email, password } = formData;

    if (guestUpgradeToken) {
      await handleGuestUpgradeSubmit(event);
      return;
    }

    if (!email || !password) {
      setMessage("Please fill in all fields.", "error");
      return;
    }

    if (password.length < 8) {
      setMessage("Password must be at least 8 characters.", "error");
      return;
    }

    try {
      if (isLogin) {
        const { data } = await loginUser({ variables: { email, password } });
        if (data?.loginUser) {
          if (typeof window !== "undefined" && data.loginUser.token) {
            localStorage.setItem("access_token", data.loginUser.token);
          }
          userVar({
            isLoggedIn: true,
            isGuest: Boolean(data.loginUser.isGuest),
            userData: { userId: data.loginUser.userId, email: data.loginUser.email },
          });
          try {
            const merged = await mergePendingGuestWorkspace(client);
            if (merged > 0) {
              setMessage(`Welcome back! We moved ${merged} idea(s) from your guest session.`, "success");
            }
          } catch (mergeErr) {
            logger.error("Guest workspace merge failed:", mergeErr);
            setMessage("Signed in, but we could not attach your guest workspace. You can contact support if ideas are missing.", "error");
          }
          await client.refetchQueries({ include: ["GetProfile", "GetIdeas"] });
          trackEvent("auth_completed", {
            method: "password",
            mode: "login",
            guest_upgrade: false,
          });
          safeNavigate(navigate, setMessage, "/ideas");
        }
      } else {
        const { data } = await signupUser({ variables: { email, password } });
        if (data?.signupUser) {
          if (data.signupUser.token) {
            if (typeof window !== "undefined") {
              localStorage.setItem("access_token", data.signupUser.token);
            }
            userVar({
              isLoggedIn: true,
              isGuest: Boolean(data.signupUser.isGuest),
              userData: { userId: data.signupUser.userId, email: data.signupUser.email },
            });
            try {
              const merged = await mergePendingGuestWorkspace(client);
              if (merged > 0) {
                setMessage(`Welcome to Manifest! We saved ${merged} idea(s) from your try session.`, "success");
              } else {
                setMessage("Welcome to Manifest!", "success");
              }
            } catch (mergeErr) {
              logger.error("Guest workspace merge failed:", mergeErr);
              setMessage("Account created, but we could not attach your guest workspace. Try signing in again or contact support.", "error");
            }
            await client.refetchQueries({ include: ["GetProfile", "GetIdeas"] });
            trackEvent("auth_completed", {
              method: "password",
              mode: "signup",
              guest_upgrade: false,
            });
            safeNavigate(navigate, setMessage, "/ideas");
          } else {
            setMessage("Account created! Please sign in.", "success");
            setIsLogin(true);
          }
        }
      }
    } catch (error: unknown) {
      logger.error("Authentication failed:", error);
      let errorMessage = "Authentication failed. Please try again.";

      const err = error as {
        networkError?: { message?: string; statusCode?: number };
        graphQLErrors?: Array<{ message: string }>;
        message?: string;
      };

      if (err?.networkError) {
        const networkErr = err.networkError;
        const networkMessage = networkErr.message || "";

        if (networkMessage.includes("JSON Parse error") || networkMessage.includes("Unexpected EOF")) {
          errorMessage = "Server error. Please try again.";
        } else if (networkErr.statusCode === 0 || networkMessage.includes("Failed to fetch")) {
          errorMessage = "Unable to connect. Please check your internet connection.";
        } else if (networkErr.statusCode && networkErr.statusCode >= 500) {
          errorMessage = "Server error. Please try again in a moment.";
        } else {
          errorMessage = networkErr.message || "Network error.";
        }
      } else if (err?.graphQLErrors && err.graphQLErrors.length > 0) {
        errorMessage = err.graphQLErrors[0].message || errorMessage;
      } else if (err?.message) {
        errorMessage = err.message;
      }

      setMessage(errorMessage, "error");
    }
  };

  const isClaimFlow = Boolean(guestUpgradeToken);

  return (
    <div className="manifest-page manifest-page-auth">
      <div className="manifest-auth-shell">
        <div className="w-full">
          {isClaimFlow ? <p className="mb-4 text-sm text-theme-secondary">Choose a password to keep your guest ideas under the email from your link.</p> : null}


          <section className="flex items-center py-6">
            <div className="w-full">
              <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
                <div className="min-w-0">
                  <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">
                    {isClaimFlow ? "Secure claim" : isLogin ? "Welcome back" : "Create your workspace"}
                  </p>
                  <h1 className="manifest-page-title mt-2">
                    {isClaimFlow ? "Set your password" : isLogin ? "Sign in to continue" : "Create an account"}
                  </h1>
                </div>

              </div>

              {isClaimFlow ? null : (
                <>
                  <Button
                    onClick={handleOAuthLogin}
                    variant="secondary"
                    className="mt-6 w-full justify-center py-3"
                  >
                    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0 1 12 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12Z" />
                    </svg>
                    Continue with GitHub
                  </Button>

                  <div className="relative my-6">
                    <div className="absolute inset-0 flex items-center">
                      <div className="w-full border-t border-stone200 dark:border-neutral700" />
                    </div>
                    <div className="relative flex justify-center">
                      <span className="bg-theme-primary px-3 py-1 text-xs text-theme-secondary">
                        or continue with email
                      </span>
                    </div>
                  </div>
                </>
              )}

              <form onSubmit={handleSubmit} className="space-y-4">
                {isClaimFlow ? null : (
                  <Input
                    type="email"
                    name="email"
                    label="Email address"
                    placeholder="Email address"
                    value={formData.email}
                    onChange={(event) => updateField("email", event.target.value)}
                    autoComplete="email"
                  />
                )}

                <div className="space-y-2">
                  <Input
                    type={showPassword ? "text" : "password"}
                    name="password"
                    label="Password"
                    placeholder="Password"
                    value={formData.password}
                    onChange={(event) => updateField("password", event.target.value)}
                    autoComplete={isClaimFlow ? "new-password" : isLogin ? "current-password" : "new-password"}
                  />
                  <div className="flex items-center justify-between">
                    <button
                      type="button"
                      onClick={() => setShowPassword((previous) => !previous)}
                      className="text-sm font-semibold text-accent-600 hover:text-accent-700 dark:text-accent-300 dark:hover:text-accent-200"
                    >
                      {showPassword ? "Hide password" : "Show password"}
                    </button>
                    {isClaimFlow || !isLogin ? null : (
                      <Link
                        to="/auth/forgot-password"
                        className="text-sm font-semibold text-accent-600 hover:text-accent-700 dark:text-accent-300 dark:hover:text-accent-200"
                      >
                        Forgot password?
                      </Link>
                    )}
                  </div>
                </div>

                <Button type="submit" disabled={isLoading} variant="primary" className="w-full justify-center py-3">
                  {isLoading
                    ? "Please wait..."
                    : isClaimFlow
                      ? "Claim account"
                      : isLogin
                        ? "Sign In"
                        : "Create Account"}
                </Button>
              </form>

              {isClaimFlow ? null : (
              <div className="mt-6 rounded-lg border border-stone200 bg-stone50 px-4 py-4 dark:border-neutral700 dark:bg-neutral800">
                <p className="text-sm font-semibold text-neutral900 dark:text-white">
                  {isLogin ? "Need an account?" : "Already have an account?"}
                </p>
                <button
                  onClick={() => setIsLogin(!isLogin)}
                  className="mt-2 text-sm font-semibold text-accent-600 hover:text-accent-700 dark:text-accent-300 dark:hover:text-accent-200"
                >
                  {isLogin ? "Sign up" : "Sign in"}
                </button>
              </div>
              )}

              <p className="mt-6 text-xs leading-6 text-gray500 dark:text-gray400">
                By continuing, you agree to our{" "}
                <Link to="/legal/terms" className="font-semibold text-accent-600 hover:text-accent-700 dark:text-accent-300 dark:hover:text-accent-200">
                  Terms of Service
                </Link>{" "}
                and acknowledge our{" "}
                <Link to="/legal/privacy" className="font-semibold text-accent-600 hover:text-accent-700 dark:text-accent-300 dark:hover:text-accent-200">
                  Privacy Policy
                </Link>
                .
              </p>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};

export default AuthForm;
