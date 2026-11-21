import React, { useState } from "react";
import { useMutation, useQuery } from "@apollo/client/react";

import Button from "features/common-ui/Button";
import Input from "features/common-ui/Input";
import {
  GET_APOLLO_KEY_STATUS,
  REMOVE_APOLLO_API_KEY,
  SAVE_APOLLO_API_KEY,
} from "features/core/apollo/queries";

/**
 * Optional, bring-your-own Apollo.io key for finding potential customers. Like the OpenAI
 * key it is verified, encrypted on the server and only its last four characters are shown;
 * searches use the person's own Apollo account and credits, never a shared one.
 */
const ApolloKeySection: React.FC = () => {
  const { data, loading } = useQuery(GET_APOLLO_KEY_STATUS, { fetchPolicy: "cache-and-network" });
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const options = { refetchQueries: [{ query: GET_APOLLO_KEY_STATUS }], errorPolicy: "all" as const };
  const [saveKey, { loading: saving }] = useMutation(SAVE_APOLLO_API_KEY, options);
  const [removeKey, { loading: removing }] = useMutation(REMOVE_APOLLO_API_KEY, options);

  const status = data?.apolloKeyStatus;
  const connected = Boolean(status?.connected);

  const onSave = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setNotice(null);
    try {
      const result = await saveKey({ variables: { apiKey: apiKey.trim() } });
      if (result?.error || !result?.data?.saveApolloApiKey) {
        setError(result?.error?.message || "Could not save the key. Try again.");
        return;
      }
      setApiKey("");
      setNotice("Key verified and saved. Prospect searches now use your Apollo.io account.");
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
      setNotice("Key removed. Prospects now come from web search only.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove the key. Try again.");
    }
  };

  return (
    <div className="space-y-4" data-testid="apollo-key-section">
      <p className="text-sm text-gray500 dark:text-gray400" aria-live="polite">
        {loading && !status
          ? "Checking your Apollo.io key…"
          : connected
            ? `Connected: Apollo.io key ending in ${status?.last4}.`
            : "Optional. Without it, potential customers come from web search."}
      </p>

      <form onSubmit={onSave} className="space-y-3">
        <Input
          id="apollo-api-key"
          name="apolloApiKey"
          label={connected ? "Replace your Apollo.io API key" : "Apollo.io API key"}
          type="password"
          autoComplete="off"
          value={apiKey}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setApiKey(e.target.value)}
        />
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" disabled={!apiKey.trim() || saving}>
            {saving ? "Verifying…" : connected ? "Replace key" : "Save key"}
          </Button>
          {connected ? (
            <Button type="button" variant="secondary" onClick={onRemove} disabled={removing}>
              {removing ? "Removing…" : "Remove key"}
            </Button>
          ) : null}
          <a
            className="text-sm underline text-gray500 dark:text-gray400"
            href="https://docs.apollo.io/docs/create-api-key"
            target="_blank"
            rel="noreferrer"
          >
            How to get an Apollo.io key
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

export default ApolloKeySection;
