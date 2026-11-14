// context/MessageContext.tsx
import React, { createContext, useContext, useState, useCallback } from "react";

type Message = {
  text: string | null;
  type: "error" | "success" | "info";
  link?: { url: string; label: string };
};

export const MessageContext = createContext<{
  message: Message;
  setMessage: (text: string, type?: "error" | "success" | "info", timeout?: number, link?: { url: string; label: string }) => void;
  clearMessage: () => void;
}>({
  message: { text: null, type: "info" },
  setMessage: () => {},
  clearMessage: () => {},
});

export const MessageProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [message, setMessageState] = useState<Message>({ text: null, type: "info" });

  const setMessage = useCallback((
    text: string,
    type: "error" | "success" | "info" = "info",
    timeout = 4000,
    link?: { url: string; label: string },
  ) => {
    setMessageState({ text, type, link });
    if (timeout > 0) {
      setTimeout(() => {
        setMessageState({ text: null, type: "info" });
      }, timeout);
    }
  }, []);

  const clearMessage = useCallback(() => {
    setMessageState({ text: null, type: "info" });
  }, []);

  return (
    <MessageContext.Provider value={{ message, setMessage, clearMessage }}>
      {children}
    </MessageContext.Provider>
  );
};

export const useMessage = () => {
  return useContext(MessageContext);
}
