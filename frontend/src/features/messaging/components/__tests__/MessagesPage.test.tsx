import React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { MockedProvider } from "@apollo/client/testing/react";

import MessagesPage from "../MessagesPage";
import { GET_MY_CONVERSATIONS } from "features/core/apollo/queries";

const mocks = [
  {
    request: { query: GET_MY_CONVERSATIONS, variables: { limit: 50, offset: 0 } },
    result: {
      data: {
        myConversations: [],
      },
    },
  },
];

describe("MessagesPage", () => {
  it("renders inbox layout and empty state", async () => {
    render(
      <MockedProvider mocks={mocks} addTypename={false}>
        <MemoryRouter initialEntries={["/messages"]}>
          <Routes>
            <Route path="/messages" element={<MessagesPage />} />
          </Routes>
        </MemoryRouter>
      </MockedProvider>,
    );

    expect(await screen.findByTestId("messages-page")).toBeInTheDocument();
    expect(await screen.findByTestId("messages-empty-state")).toBeInTheDocument();
    expect(screen.getByText("Inbox")).toBeInTheDocument();
  });
});
