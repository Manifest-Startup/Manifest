// index.js is the entry point for the React application. It initializes providers, routing, and renders the root component.

import React from "react"; // Importing React library
import ReactDOM from "react-dom/client"; // Importing ReactDOM for rendering
import { createBrowserRouter, RouterProvider } from "react-router-dom"; // Import new data router APIs
import App from "./App"; // Importing main App component
import "./index.css"; // Importing CSS for this file
import { ApolloProvider } from '@apollo/client/react'; // Added ApolloProvider import
import { client } from './features/core/apollo/client'; // Added Apollo Client instance import
import { PrivacyConsentProvider } from "features/privacy/PrivacyConsentContext";
import { VaultGate } from "features/vault/VaultGate";
import { CREATE_IDEA, GET_IDEA, GET_IDEAS, UPDATE_IDEA } from "features/core/apollo/queries";

declare global {
  interface Window {
    manifestWebMcpApi?: {
      listIdeas: () => Promise<unknown>;
      readIdea: (ideaId: string) => Promise<unknown>;
      createIdea: (title: string, description?: string) => Promise<unknown>;
      updateIdea: (ideaId: string, title?: string, description?: string) => Promise<unknown>;
    };
  }
}

window.manifestWebMcpApi = {
  async listIdeas() {
    const { data } = await client.query({ query: GET_IDEAS, fetchPolicy: "network-only" });
    return data?.ideas ?? [];
  },
  async readIdea(ideaId) {
    const { data } = await client.query({ query: GET_IDEA, variables: { ideaId }, fetchPolicy: "network-only" });
    if (!data?.idea) throw new Error("Idea not found or not available to this account.");
    return data.idea;
  },
  async createIdea(title, description) {
    const { data } = await client.mutate({ mutation: CREATE_IDEA, variables: { title, description } });
    if (!data?.createIdea) throw new Error("Manifest did not create the idea.");
    return data.createIdea;
  },
  async updateIdea(ideaId, title, description) {
    const { data } = await client.mutate({ mutation: UPDATE_IDEA, variables: { ideaId, title, description } });
    if (!data?.updateIdea) throw new Error("Idea not found or not available to this account.");
    return data.updateIdea;
  },
};
window.dispatchEvent(new Event("manifest:webmcp-ready"));

// Create React root and render application wrapped in necessary providers
const container = document.getElementById("root"); // Getting the root element from the DOM
if (!container) throw new Error("Root container missing in index.html"); // Throwing error if root is not found

const root = ReactDOM.createRoot(container); // Creating a root for ReactDOM

// Define the router using the new data router API
const router = createBrowserRouter([
  {
    path: "/*",
    element: <App />,
  },
]);

const AppWithProviders = () => {
  return (
    <PrivacyConsentProvider>
      {/* Local vault mode (ADR 0011) waits for folder access; cloud mode passes through. */}
      <VaultGate client={client}>
        <RouterProvider router={router} />
      </VaultGate>
    </PrivacyConsentProvider>
  );
};

root.render( // Rendering the root
  <React.StrictMode>
    <ApolloProvider client={client}> {/* Wrap with ApolloProvider to provide Apollo Client context */}
      <AppWithProviders />
    </ApolloProvider>
  </React.StrictMode>
);
