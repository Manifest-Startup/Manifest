import React from "react";
import { MockedProvider } from "@apollo/client/testing/react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { GraphQLError } from "graphql";

import ApolloKeySection from "../ApolloKeySection";

// jest.setup.js stubs useMutation globally; this suite exercises the real hook.
jest.mock("@apollo/client/react", () => jest.requireActual("@apollo/client/react"));
import { GET_APOLLO_KEY_STATUS, SAVE_APOLLO_API_KEY } from "features/core/apollo/queries";

const status = (connected: boolean, last4: string | null = null) => ({
  __typename: "ApolloKeyStatus",
  connected,
  last4,
});
const statusMock = (connected: boolean, last4: string | null = null) => ({
  request: { query: GET_APOLLO_KEY_STATUS },
  result: { data: { apolloKeyStatus: status(connected, last4) } },
});

describe("ApolloKeySection", () => {
  it("says the key is optional", async () => {
    render(
      <MockedProvider mocks={[statusMock(false)]}>
        <ApolloKeySection />
      </MockedProvider>,
    );
    expect(await screen.findByText(/Optional/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save key" })).toBeDisabled();
  });

  it("saves a key and shows only its last four characters", async () => {
    const apiKey = "apollo-test-key-ABCD";
    const mocks = [
      statusMock(false),
      {
        request: { query: SAVE_APOLLO_API_KEY, variables: { apiKey } },
        result: { data: { saveApolloApiKey: status(true, "ABCD") } },
      },
      statusMock(true, "ABCD"),
    ];
    render(
      <MockedProvider mocks={mocks}>
        <ApolloKeySection />
      </MockedProvider>,
    );
    await screen.findByText(/Optional/);
    fireEvent.change(screen.getByLabelText("Apollo.io API key"), { target: { value: apiKey } });
    fireEvent.click(screen.getByRole("button", { name: "Save key" }));
    expect(await screen.findByText(/Key verified and saved/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Connected: Apollo.io key ending in ABCD.")).toBeInTheDocument());
  });

  it("shows Apollo's rejection", async () => {
    const apiKey = "apollo-bad-key-0000";
    const mocks = [
      statusMock(false),
      {
        request: { query: SAVE_APOLLO_API_KEY, variables: { apiKey } },
        result: { errors: [new GraphQLError("Apollo.io rejected this key. Check it and try again.")] },
      },
    ];
    render(
      <MockedProvider mocks={mocks}>
        <ApolloKeySection />
      </MockedProvider>,
    );
    await screen.findByText(/Optional/);
    fireEvent.change(screen.getByLabelText("Apollo.io API key"), { target: { value: apiKey } });
    fireEvent.click(screen.getByRole("button", { name: "Save key" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Apollo.io rejected this key");
  });
});
