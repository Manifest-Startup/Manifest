import { useEffect } from "react";

import { useMessage } from "features/notifications/context/MessageContext";
import { AI_KEY_REQUIRED_EVENT, AI_KEY_SETTINGS_PATH } from "./aiKeyRequired";

/** Shows one banner with a settings link whenever an AI call needs a key. */
const AiKeyRequiredNotice: React.FC = () => {
  const { setMessage } = useMessage();

  useEffect(() => {
    const show = () =>
      setMessage(
        "AI features use your own OpenAI API key. Add it once in Account settings to continue.",
        "info",
        12000,
        { url: AI_KEY_SETTINGS_PATH, label: "Add your key" },
      );
    window.addEventListener(AI_KEY_REQUIRED_EVENT, show);
    return () => window.removeEventListener(AI_KEY_REQUIRED_EVENT, show);
  }, [setMessage]);

  return null;
};

export default AiKeyRequiredNotice;
