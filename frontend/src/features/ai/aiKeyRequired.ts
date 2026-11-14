/**
 * Bring-your-own-key: the backend answers any AI request made without a key
 * with this message. The Apollo error link announces it; AiKeyRequiredNotice
 * turns it into a banner that links to the key settings.
 */
export const AI_KEY_REQUIRED_MARKER = "Add your OpenAI API key";
export const AI_KEY_REQUIRED_EVENT = "manifest:ai-key-required";
export const AI_KEY_SETTINGS_PATH = "/account#ai-key";

export const isAiKeyRequiredMessage = (message: string | null | undefined): boolean =>
  Boolean(message && message.includes(AI_KEY_REQUIRED_MARKER));

export const announceAiKeyRequired = (): void => {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(AI_KEY_REQUIRED_EVENT));
  }
};
