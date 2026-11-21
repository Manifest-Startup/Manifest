import React from "react";
import { MockedProvider } from "@apollo/client/testing/react";
import type { MockedResponse } from "@apollo/client/testing";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import GitHubSection, { GITHUB_TOKEN_URL } from "../GitHubSection";

// jest.setup.js stubs useMutation globally; this suite exercises the real hook.
jest.mock("@apollo/client/react", () => jest.requireActual("@apollo/client/react"));
import {
  CONNECT_GITHUB,
  GET_GITHUB_ACCOUNT,
  GET_GITHUB_RECENT_REPOS,
  GET_INTEGRATIONS,
} from "features/core/apollo/queries";

const account = (connected: boolean, extra: Record<string, unknown> = {}) => ({
  __typename: "GithubAccount",
  connected,
  oauthAvailable: false,
  login: connected ? "octo" : null,
  name: null,
  avatarUrl: null,
  htmlUrl: connected ? "https://github.com/octo" : null,
  scopes: connected ? ["repo", "workflow"] : [],
  method: connected ? "token" : null,
  connectedAt: null,
  message: null,
  ...extra,
});

const accountMock = (connected: boolean, extra: Record<string, unknown> = {}) => ({
  request: { query: GET_GITHUB_ACCOUNT },
  result: { data: { githubAccount: account(connected, extra) } },
});

const reposMock = {
  request: { query: GET_GITHUB_RECENT_REPOS, variables: { limit: 5 } },
  result: {
    data: {
      githubRepos: [
        { __typename: "GithubRepo", fullName: "octo/app", htmlUrl: "https://github.com/octo/app", private: true, description: null, updatedAt: null },
      ],
    },
  },
};

const integrationsMock = { request: { query: GET_INTEGRATIONS }, result: { data: { integrations: [] } } };

const renderSection = (mocks: MockedResponse[]) =>
  render(
    <MemoryRouter>
      <MockedProvider mocks={mocks}>
        <GitHubSection />
      </MockedProvider>
    </MemoryRouter>,
  );

describe("GitHubSection", () => {
  it("has one Connect GitHub action, and the token is its next step when sign-in isn't set up", async () => {
    renderSection([accountMock(false)]);
    await screen.findByText("Not connected.");
    const connect = screen.getByRole("button", { name: "Connect GitHub" });
    expect(screen.queryByLabelText("GitHub token")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Sign in with GitHub/ })).not.toBeInTheDocument();
    expect(screen.getByText("manifest github connect")).toBeInTheDocument();

    fireEvent.click(connect);
    expect(await screen.findByLabelText("GitHub token")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Create a token on GitHub" })).toHaveAttribute("href", GITHUB_TOKEN_URL);
    expect(screen.getByRole("button", { name: "Connect" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Connect GitHub" })).not.toBeInTheDocument();
  });

  it("uses Sign in with GitHub when the deployment has it", async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ auth_url: "https://github.com/login/oauth/authorize?x=1" }),
    });
    const originalFetch = global.fetch;
    global.fetch = fetchMock as unknown as typeof fetch;
    const popup = { closed: false } as Window;
    const openSpy = jest.spyOn(window, "open").mockReturnValue(popup);
    try {
      renderSection([accountMock(false, { oauthAvailable: true })]);
      await screen.findByText("Not connected.");
      fireEvent.click(screen.getByRole("button", { name: "Connect GitHub" }));
      await waitFor(() => expect(openSpy).toHaveBeenCalledWith("https://github.com/login/oauth/authorize?x=1", "oauth_github", expect.any(String)));
      expect(fetchMock).toHaveBeenCalledWith("/auth/github/start", { credentials: "include" });
      expect(screen.queryByLabelText("GitHub token")).not.toBeInTheDocument();
      expect(await screen.findByRole("button", { name: "Waiting for GitHub…" })).toBeInTheDocument();
    } finally {
      openSpy.mockRestore();
      global.fetch = originalFetch;
    }
  });

  it("connects with a token", async () => {
    const token = "ghp_" + "a".repeat(36);
    renderSection([
      accountMock(false),
      { request: { query: CONNECT_GITHUB, variables: { token } }, result: { data: { connectGithub: account(true) } } },
      accountMock(true),
      integrationsMock,
      reposMock,
    ]);
    await screen.findByText("Not connected.");
    fireEvent.click(screen.getByRole("button", { name: "Connect GitHub" }));
    fireEvent.change(await screen.findByLabelText("GitHub token"), { target: { value: token } });
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));
    expect(await screen.findByText("Connected as octo.")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByLabelText("GitHub token")).not.toBeInTheDocument());
  });

  it("shows who is connected and their recent repositories", async () => {
    renderSection([accountMock(true), reposMock]);
    expect(await screen.findByText("Connected as @octo.")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "octo/app" })).toHaveAttribute("href", "https://github.com/octo/app");
    expect(screen.getByRole("button", { name: "Disconnect" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Connect GitHub" })).not.toBeInTheDocument();
  });

  it("offers to reconnect when the connection can't run workflows", async () => {
    renderSection([accountMock(true, { scopes: ["repo"] }), reposMock]);
    expect(await screen.findByText(/can't use workflow/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reconnect GitHub" })).toBeInTheDocument();
  });
});
