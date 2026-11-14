import React from "react";
import { render, screen } from "@testing-library/react";
import { ApolloClient, ApolloLink, InMemoryCache, Observable } from "@apollo/client";
import { ApolloProvider } from "@apollo/client/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import MessagesPage from "../MessagesPage";

function renderWithCountingClient(operationNames: string[]) {
  const link = new ApolloLink((operation) => {
    operationNames.push(operation.operationName);
    return new Observable((observer) => {
      observer.next({
        data: {
          myConversations: [],
        },
      });
      observer.complete();
    });
  });

  const client = new ApolloClient({
    cache: new InMemoryCache(),
    link,
  });

  render(
    <ApolloProvider client={client}>
      <MemoryRouter initialEntries={["/messages"]}>
        <Routes>
          <Route path="/messages" element={<MessagesPage />} />
        </Routes>
      </MemoryRouter>
    </ApolloProvider>,
  );
}

describe("MessagesPage performance guards", () => {
  it("shares the conversation query with the list instead of issuing duplicate requests", async () => {
    const operationNames: string[] = [];

    renderWithCountingClient(operationNames);

    expect(await screen.findByTestId("messages-empty-state")).toBeInTheDocument();
    expect(operationNames.filter((name) => name === "GetMyConversations")).toHaveLength(1);
  });
});
