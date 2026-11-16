import React from "react";
import { render, waitFor } from "@testing-library/react";

import { useOpenMediaRealtime } from "../useOpenMediaRealtime";

const mockQuery = jest.fn();
const mockSubscribe = jest.fn();
const mockOn = jest.fn();
const mockRemoveChannel = jest.fn();
const mockDisconnect = jest.fn();
const mockCreateClient = jest.fn();

jest.mock("@apollo/client/react", () => ({
  ...jest.requireActual("@apollo/client/react"),
  useApolloClient: () => ({ query: mockQuery }),
}));

jest.mock("@supabase/supabase-js", () => ({
  createClient: (...args: unknown[]) => mockCreateClient(...args),
}));

const Probe = ({ enabled, onChange }: { enabled: boolean; onChange: () => void }) => {
  useOpenMediaRealtime(enabled, onChange);
  return null;
};

describe("useOpenMediaRealtime", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    const channel = { on: mockOn, subscribe: mockSubscribe };
    mockOn.mockReturnValue(channel);
    mockSubscribe.mockReturnValue(channel);
    mockCreateClient.mockReturnValue({
      channel: () => channel,
      removeChannel: mockRemoveChannel,
      realtime: { disconnect: mockDisconnect },
    });
    mockQuery.mockResolvedValue({
      data: {
        openMediaRealtimeToken: {
          supabaseUrl: "https://om.supabase.co",
          anonKey: "anon",
          accessToken: "user-jwt",
          expiresAt: null,
          omUserId: "om-1",
        },
      },
    });
  });

  it("does nothing until Open Media is ready", () => {
    render(<Probe enabled={false} onChange={jest.fn()} />);
    expect(mockQuery).not.toHaveBeenCalled();
  });

  it("subscribes to message changes with the user's Open Media token and cleans up", async () => {
    const onChange = jest.fn();
    const { unmount } = render(<Probe enabled onChange={onChange} />);

    await waitFor(() => expect(mockSubscribe).toHaveBeenCalled());
    const [url, key, options] = mockCreateClient.mock.calls[0];
    expect([url, key]).toEqual(["https://om.supabase.co", "anon"]);
    await expect(options.accessToken()).resolves.toBe("user-jwt");
    expect(mockOn).toHaveBeenCalledWith(
      "postgres_changes",
      { event: "*", schema: "public", table: "messages" },
      expect.any(Function),
    );

    jest.useFakeTimers();
    mockOn.mock.calls[0][2]();
    mockOn.mock.calls[0][2]();
    jest.advanceTimersByTime(500);
    expect(onChange).toHaveBeenCalledTimes(1);
    jest.useRealTimers();

    unmount();
    expect(mockRemoveChannel).toHaveBeenCalled();
    expect(mockDisconnect).toHaveBeenCalled();
  });

  it("falls back quietly when no token is available", async () => {
    mockQuery.mockRejectedValue(new Error("Connect your Open Media account"));
    render(<Probe enabled onChange={jest.fn()} />);
    await waitFor(() => expect(mockQuery).toHaveBeenCalled());
    expect(mockCreateClient).not.toHaveBeenCalled();
  });
});
