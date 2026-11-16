import { useMutation } from "@apollo/client/react";
import { useNavigate } from "react-router-dom";

import { trackEvent } from "features/analytics/projectAnalytics";
import { applyGuestSessionPayload } from "features/auth/guestSessionBootstrap";
import { START_GUEST_SESSION } from "features/core/apollo/queries";
import { useMessage } from "features/notifications/context/MessageContext";

/** "Try without an account": start a server-backed guest workspace and open it. */
export function useStartGuestSession(source: string): { start: () => Promise<void>; loading: boolean } {
  const navigate = useNavigate();
  const { setMessage } = useMessage();
  const [startGuestSession, { loading }] = useMutation(START_GUEST_SESSION);

  const start = async () => {
    try {
      const { data } = await startGuestSession();
      if (!applyGuestSessionPayload(data?.startGuestSession ?? undefined)) {
        setMessage("The demo could not be opened. Please try again later.", "error");
        return;
      }
      trackEvent("demo_session_started", { session_type: "guest", source });
      navigate("/ideas");
    } catch (error) {
      console.error(error);
      setMessage("The demo could not be opened. Please try again later.", "error");
    }
  };

  return { start, loading };
}
