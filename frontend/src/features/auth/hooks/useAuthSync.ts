import { useEffect } from "react";
import { useSafeQuery } from "../../common-ui/api/useSafeQuery";
import { useNavigate } from "react-router-dom";

import { isLogoutRedirectInProgress } from "features/auth/logout";
import { GET_PROFILE } from "features/core/apollo/queries";
import { useMessage } from "features/notifications/context/MessageContext";
import { createLogger } from "features/core/logError";
import { userVar } from "features/core/apollo/localState";

const logger = createLogger('useAuthSync');

/**
 * Synchronises the authenticated user between Apollo cache & Redux.
 * Also handles session expiry and redirects to /login when the session is invalid.
 */
export const useAuthSync = () => {
  const navigate = useNavigate();
  const { setMessage } = useMessage();

  // The Open Media sign-in callback adds ``?merged=N`` after moving a guest workspace.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const url = new URL(window.location.href);
    const merged = Number(url.searchParams.get('merged'));
    if (!url.searchParams.has('merged')) return;
    url.searchParams.delete('merged');
    window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`);
    if (merged > 0) {
      setMessage(`Welcome! We moved ${merged} idea${merged === 1 ? '' : 's'} from your guest workspace.`, 'success');
    }
  }, [setMessage]);

  // Handler for GET_PROFILE errors. Must always mark `authChecked: true` so
  // `PrivateRoute` does not stay on the initial Loading gate forever — even
  // for transient network errors during a hard reload.
  const handleGetProfileError = (error: any) => {
    logger.error('GET_PROFILE failed', error);
    userVar({ isLoggedIn: false, authChecked: true, isGuest: false, userData: null });
    const isUnauthenticated = Array.isArray(error?.graphQLErrors)
      && error.graphQLErrors.some((e: any) => e?.extensions?.code === 'UNAUTHENTICATED');
    if (isUnauthenticated && !isLogoutRedirectInProgress()) {
      setMessage('Your session has expired. Please log in again.', 'error');
      navigate('/login');
    }
  };

  useSafeQuery(GET_PROFILE, {
    skip: false,
    // Always verify with the server so a cached `profile: null` cannot clobber a fresh login.
    fetchPolicy: 'network-only',
    onError: handleGetProfileError,
    onCompleted: (data) => {
      if (data?.profile) {
        userVar({
          isLoggedIn: true,
          authChecked: true,
          isGuest: Boolean(data.profile.isGuest),
          userData: {
            userId: data.profile.userId ?? data.profile.id,
            email: data.profile.email,
          },
        });
      } else {
        userVar({ isLoggedIn: false, authChecked: true, isGuest: false, userData: null });
      }
    },
  });
};