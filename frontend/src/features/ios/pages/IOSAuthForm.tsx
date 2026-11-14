import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { clearLogoutRedirectInProgress } from 'features/auth/logout';
import { safeNavigate } from 'utils/safeNavigate';
import { useApolloClient, useMutation } from '@apollo/client/react';
import { mergePendingGuestWorkspace } from 'features/auth/mergeGuestWorkspace';
import { COMPLETE_GUEST_ACCOUNT_UPGRADE, LOGIN_USER, SIGNUP_USER } from 'features/core/apollo/queries';
import Input from 'features/common-ui/Input';
import Button from 'features/common-ui/Button';
import { useMessage } from 'features/notifications/context/MessageContext';
import { createLogger } from 'features/core/logError';
import { userVar } from "features/core/apollo/localState";
import { useFormState, useInputHandlers } from 'features/common-ui/hooks/formHooks';
import IOSPageWrapper from '../components/IOSPageWrapper';

const logger = createLogger('IOSAuthForm');

/**
 * iOS-styled authentication form with native iOS design patterns
 */
const IOSAuthForm: React.FC = () => {
  logger.log('rendered');
  const { formData, updateField } = useFormState<{ email: string; password: string }>({ email: '', password: '' });
  const { handleInputChange } = useInputHandlers(updateField);
  
  // Create field-specific handlers
  const handleEmailChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    updateField('email', e.target.value);
  };
  
  const handlePasswordChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    updateField('password', e.target.value);
  };
  const [isLogin, setIsLogin] = React.useState<boolean>(true);
  const navigate = useNavigate();
  const { setMessage, clearMessage } = useMessage();
  const client = useApolloClient();
  const [loginUser, { loading: loginLoading }] = useMutation(LOGIN_USER);
  const [signupUser, { loading: signupLoading }] = useMutation(SIGNUP_USER);
  const [completeGuestUpgrade, { loading: upgradeLoading }] = useMutation(COMPLETE_GUEST_ACCOUNT_UPGRADE);

  const [guestUpgradeToken] = React.useState<string | null>(() => {
    if (typeof window === 'undefined') {
      return null;
    }
    try {
      return new URL(window.location.href).searchParams.get('guest_upgrade_token');
    } catch {
      return null;
    }
  });

  const isLoading = loginLoading || signupLoading || upgradeLoading;

  React.useEffect(() => {
    if (clearLogoutRedirectInProgress()) {
      clearMessage();
    }
    const url = new URL(window.location.href);
    if (url.searchParams.has('guest_upgrade_token')) {
      url.searchParams.delete('guest_upgrade_token');
      window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
    }
  }, [clearMessage]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const { email, password } = formData;

    if (guestUpgradeToken) {
      if (!password || password.length < 8) {
        setMessage('Password must be at least 8 characters.', 'error');
        return;
      }
      try {
        const { data } = await completeGuestUpgrade({
          variables: { token: guestUpgradeToken, password },
        });
        const auth = data?.completeGuestAccountUpgrade;
        if (auth?.token) {
          if (typeof window !== 'undefined') {
            localStorage.setItem('access_token', auth.token);
          }
          userVar({
            isLoggedIn: true,
            isGuest: false,
            authChecked: true,
            userData: { userId: auth.userId, email: auth.email },
          });
          await client.refetchQueries({ include: ['GetProfile', 'GetIdeas'] });
          setMessage('Welcome — your workspace is now a full account.', 'success');
          safeNavigate(navigate, setMessage, '/ideas');
        }
      } catch (error: any) {
        const msg = error?.graphQLErrors?.[0]?.message || error?.message || 'Could not complete upgrade.';
        setMessage(msg, 'error');
      }
      return;
    }

    logger.log('handleSubmit called', { email, isLogin });
    
    if (!email || !password) {
      setMessage("Please fill in all fields.", "error");
      return;
    }

    try {
      logger.log(`${isLogin ? 'Attempting login' : 'Attempting signup'} for`, email);
      
      if (isLogin) {
        const { data } = await loginUser({ variables: { email, password } });
        if (data?.loginUser) {
          logger.log("Logged in as", data.loginUser.email);
          if (typeof window !== 'undefined' && data.loginUser.token) {
            localStorage.setItem('access_token', data.loginUser.token);
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
            setMessage("Signed in, but we could not attach your guest workspace.", "error");
          }
          await client.refetchQueries({ include: ["GetProfile", "GetIdeas"] });
          safeNavigate(navigate, setMessage, "/ideas");
        }
      } else {
        const { data } = await signupUser({ variables: { email, password } });
        if (data?.signupUser) {
          logger.log("Signup successful for", data.signupUser.email);
          
          if (data.signupUser.token) {
            logger.log("Token provided - auto-logging in user");
            if (typeof window !== 'undefined') {
              localStorage.setItem('access_token', data.signupUser.token);
            }
            userVar({
              isLoggedIn: true,
              isGuest: Boolean(data.signupUser.isGuest),
              userData: {
                userId: data.signupUser.userId,
                email: data.signupUser.email,
              },
            });
            try {
              const merged = await mergePendingGuestWorkspace(client);
              if (merged > 0) {
                setMessage(`Account created! We saved ${merged} idea(s) from your try session.`, "success");
              } else {
                setMessage("Account created successfully! You are now logged in.", "success");
              }
            } catch (mergeErr) {
              logger.error("Guest workspace merge failed:", mergeErr);
              setMessage("Account created, but we could not attach your guest workspace.", "error");
            }
            await client.refetchQueries({ include: ["GetProfile", "GetIdeas"] });
            safeNavigate(navigate, setMessage, "/ideas");
          } else {
            logger.log("No token provided - email confirmation required");
            if (typeof window !== 'undefined') {
              localStorage.removeItem('access_token');
            }
            setMessage("Account created successfully! Please check your email to confirm your account.", "success");
            setIsLogin(true);
          }
        } else {
          setMessage("Account created successfully! Please check your email to confirm your account.", "success");
          setIsLogin(true);
        }
      }
    } catch (error: any) {
      logger.error("Authentication failed:", error);
      let errorMessage = "Authentication failed. Please try again.";
      
      // Handle network errors first (most common in production)
      if (error?.networkError) {
        const networkErr = error.networkError;
        const errorMsg = networkErr.message || '';
        
        // Check for JSON parse errors (empty or incomplete responses)
        if (errorMsg.includes('JSON Parse error') || 
            errorMsg.includes('Unexpected EOF') || 
            errorMsg.includes('Unexpected end of JSON input') ||
            errorMsg.includes('empty or incomplete response')) {
          errorMessage = "Server returned an empty response. Please check your connection and try again.";
        } else if (networkErr.statusCode === 0 || errorMsg.includes('Failed to fetch')) {
          errorMessage = "Unable to connect to server. Please check your internet connection and try again.";
        } else if (networkErr.statusCode >= 500) {
          errorMessage = "Server error. Please try again in a few moments.";
        } else if (networkErr.statusCode === 404) {
          errorMessage = "API endpoint not found. Please contact support.";
        } else {
          errorMessage = networkErr.message || "Network error. Please check your connection.";
        }
      } else if (error?.graphQLErrors && error.graphQLErrors.length > 0) {
        // Handle GraphQL errors
        const graphQLError = error.graphQLErrors[0];
        errorMessage = graphQLError.message || errorMessage;
        
        // Check for specific error codes
        if (graphQLError.extensions?.code === 'UNAUTHENTICATED') {
          errorMessage = "Invalid email or password. Please try again.";
        }
      } else if (error?.message) {
        errorMessage = error.message;
      }
      
      logger.error("Final error message:", errorMessage);
      setMessage(errorMessage, "error");
    }
  };

  return (
    <IOSPageWrapper showTabBar={false}>
      <div className="manifest-auth-shell px-4 py-8">
        <div className="mb-6">
          <h1 className="manifest-page-title mb-2">Manifest</h1>
          <p className="text-sm text-theme-secondary">
            {guestUpgradeToken ? 'Set a password to claim your guest workspace' : 'Turn your ideas into reality'}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {guestUpgradeToken ? null : (
            <div>
              <Input
                type="email"
                label="Email"
                autoComplete="email"
                placeholder="Email"
                value={formData.email}
                onChange={handleEmailChange}
                className="ios-input"
              />
            </div>
          )}

          <div>
            <Input
              type="password"
              label="Password"
              autoComplete={isLogin ? "current-password" : "new-password"}
              placeholder="Password"
              value={formData.password}
              onChange={handlePasswordChange}
              className="ios-input"
            />
          </div>

          <Button
            type="submit"
            disabled={isLoading}
            className="w-full"
          >
            {isLoading ? 'Loading...' : guestUpgradeToken ? 'Claim account' : (isLogin ? 'Sign In' : 'Sign Up')}
          </Button>
        </form>

        {guestUpgradeToken ? null : (
        <div className="mt-6 text-center">
          <button
            onClick={() => setIsLogin(!isLogin)}
            className="text-accent-600 font-medium text-sm active:opacity-70"
          >
            {isLogin ? "Don't have an account? Sign Up" : "Already have an account? Sign In"}
          </button>
        </div>
        )}

        <p className="mt-6 text-center text-xs leading-6 text-gray-500 dark:text-gray-400">
          By continuing, you agree to our{" "}
          <Link to="/legal/terms" className="font-semibold text-accent-600 active:opacity-70">
            Terms of Service
          </Link>{" "}
          and acknowledge our{" "}
          <Link to="/legal/privacy" className="font-semibold text-accent-600 active:opacity-70">
            Privacy Policy
          </Link>
          .
        </p>
      </div>
    </IOSPageWrapper>
  );
};

export default IOSAuthForm;

