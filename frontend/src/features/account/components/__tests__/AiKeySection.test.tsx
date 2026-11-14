import React from "react";
import { MockedProvider } from "@apollo/client/testing/react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { GraphQLError } from "graphql";

import AiKeySection from "../AiKeySection";

// jest.setup.js stubs useMutation globally; this suite exercises the real hook.
jest.mock("@apollo/client/react", () => jest.requireActual("@apollo/client/react"));
import {
  GET_AI_KEY_STATUS,
  REMOVE_OPENAI_API_KEY,
  SAVE_OPENAI_API_KEY,
} from "features/core/apollo/queries";

const status = (source: "user" | "none", last4: string | null = null) => ({
  aiKeyStatus: { __typename: "AiKeyStatus", configured: source !== "none", source, last4 },
});

const statusMock = (source: "user" | "none", last4: string | null = null) => ({
  request: { query: GET_AI_KEY_STATUS },
  result: { data: status(source, last4) },
});

describe("AiKeySection", () => {
  it("explains that AI is off until a key is added", async () => {
    render(
      <MockedProvider mocks={[statusMock("none")]}>
        <AiKeySection />
      </MockedProvider>,
    );
    expect(await screen.findByText(/No key yet/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save key" })).toBeDisabled();
  });

  it("shows only the last four characters of a connected key", async () => {
    render(
      <MockedProvider mocks={[statusMock("user", "WXYZ")]}>
        <AiKeySection />
      </MockedProvider>,
    );
    expect(await screen.findByText("Connected: OpenAI key ending in WXYZ.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove key" })).toBeInTheDocument();
  });

  it("saves a key and clears the field", async () => {
    const apiKey = "sk-test-0123456789abcdefWXYZ";
    const mocks = [
      statusMock("none"),
      {
        request: { query: SAVE_OPENAI_API_KEY, variables: { apiKey } },
        result: { data: { saveOpenaiApiKey: status("user", "WXYZ").aiKeyStatus } },
      },
      statusMock("user", "WXYZ"),
    ];
    render(
      <MockedProvider mocks={mocks}>
        <AiKeySection />
      </MockedProvider>,
    );
    const input = await screen.findByLabelText("OpenAI API key");
    fireEvent.change(input, { target: { value: `  ${apiKey}  ` } });
    fireEvent.click(screen.getByRole("button", { name: "Save key" }));
    expect(await screen.findByText(/Key verified and saved/)).toBeInTheDocument();
    await waitFor(() => expect((input as HTMLInputElement).value).toBe(""));
  });

  it("shows why OpenAI rejected a key", async () => {
    const apiKey = "sk-bad-0123456789abcdef0000";
    const mocks = [
      statusMock("none"),
      {
        request: { query: SAVE_OPENAI_API_KEY, variables: { apiKey } },
        result: { errors: [new GraphQLError("OpenAI rejected this key. Check it and try again.")] },
      },
    ];
    render(
      <MockedProvider mocks={mocks}>
        <AiKeySection />
      </MockedProvider>,
    );
    fireEvent.change(await screen.findByLabelText("OpenAI API key"), { target: { value: apiKey } });
    fireEvent.click(screen.getByRole("button", { name: "Save key" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("OpenAI rejected this key");
  });

  it("removes a connected key", async () => {
    const mocks = [
      statusMock("user", "WXYZ"),
      { request: { query: REMOVE_OPENAI_API_KEY }, result: { data: { removeOpenaiApiKey: status("none").aiKeyStatus } } },
      statusMock("none"),
    ];
    render(
      <MockedProvider mocks={mocks}>
        <AiKeySection />
      </MockedProvider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Remove key" }));
    expect(await screen.findByText(/Key removed/)).toBeInTheDocument();
  });
});
