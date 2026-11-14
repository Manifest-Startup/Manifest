import React, { useState } from "react";
import { useMutation, useQuery } from "@apollo/client/react";

import Button from "features/common-ui/Button";
import Input from "features/common-ui/Input";
import {
  GET_AI_KEY_STATUS,
  REMOVE_OPENAI_API_KEY,
  SAVE_OPENAI_API_KEY,
} from "features/core/apollo/queries";

/**
 * Bring-your-own-key: customers paste their OpenAI API key once. It is
 * verified with OpenAI, encrypted on the server, and used for all of their AI
 * generation. Only the last four characters are ever shown again.
 */
const AiKeySection: React.FC = () => {
  const { data, loading } = useQuery(GET_AI_KEY_STATUS, { fetchPolicy: "cache-and-network" });
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // errorPolicy "all": GraphQL errors (e.g. "OpenAI rejected this key") come back
  // on result.error instead of throwing, so both paths are handled explicitly.
  const options = { refetchQueries: [{ query: GET_AI_KEY_STATUS }], errorPolicy: "all" as const };
  const [saveKey, { loading: saving }] = useMutation(SAVE_OPENAI_API_KEY, options);
  const [removeKey, { loading: removing }] = useMutation(REMOVE_OPENAI_API_KEY, options);

  const status = data?.aiKeyStatus;
  const hasOwnKey = status?.source === "user";

  const onSave = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setNotice(null);
    try {
      const result = await saveKey({ variables: { apiKey: apiKey.trim() } });
      if (result?.error || !result?.data?.saveOpenaiApiKey) {
        setError(result?.error?.message || "Could not save the key. Try again.");
        return;
      }
      setApiKey("");
      setNotice("Key verified and saved. AI features now use your OpenAI account.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the key. Try again.");
    }
  };

  const onRemove = async () => {
    setError(null);
    setNotice(null);
    try {
      const result = await removeKey();
      if (result?.error) {
        setError(result.error.message);
        return;
      }
      setNotice("Key removed. AI features are paused until you add a key.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove the key. Try again.");
    }
  };

  return (
    <div className="space-y-4" data-testid="ai-key-section">
      <p className="text-sm text-gray500 dark:text-gray400" aria-live="polite">
        {loading && !status
          ? "Checking your AI key…"
          : hasOwnKey
            ? `Connected: OpenAI key ending in ${status?.last4}.`
            : status?.source === "platform"
              ? "Using Manifest's shared key for now. Add your own to keep AI working."
              : "No key yet. AI generation is off until you add one."}
      </p>

      <form onSubmit={onSave} className="space-y-3">
        <Input
          id="openai-api-key"
          name="openaiApiKey"
          label={hasOwnKey ? "Replace your OpenAI API key" : "OpenAI API key"}
          type="password"
          autoComplete="off"
          placeholder="sk-..."
          value={apiKey}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setApiKey(e.target.value)}
        />
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" disabled={!apiKey.trim() || saving}>
            {saving ? "Verifying…" : hasOwnKey ? "Replace key" : "Save key"}
          </Button>
          {hasOwnKey ? (
            <Button type="button" variant="secondary" onClick={onRemove} disabled={removing}>
              {removing ? "Removing…" : "Remove key"}
            </Button>
          ) : null}
          <a
            className="text-sm underline text-gray500 dark:text-gray400"
            href="https://platform.openai.com/api-keys"
            target="_blank"
            rel="noreferrer"
          >
            Get a key from OpenAI
          </a>
        </div>
      </form>

      {error ? (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      ) : null}
      {notice ? <p className="text-sm text-green-700 dark:text-green-400">{notice}</p> : null}
    </div>
  );
};

export default AiKeySection;
