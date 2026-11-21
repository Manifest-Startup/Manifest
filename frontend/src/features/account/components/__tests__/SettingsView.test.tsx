import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import SettingsView, { searchSettings, type SettingsSection } from "../SettingsView";

const sections: SettingsSection[] = [
  {
    id: "profile",
    label: "Profile",
    summary: "How you appear.",
    icon: "user",
    items: [{ anchor: "profile-photo", label: "Profile photo", keywords: "avatar picture" }],
    content: <div id="profile-photo">Photo card</div>,
  },
  {
    id: "connections",
    label: "AI & sign-in",
    summary: "Your OpenAI key.",
    icon: "sparkles",
    status: { text: "Add your OpenAI key", tone: "warn" },
    items: [
      { anchor: "ai-key", label: "OpenAI API key", keywords: "byok" },
      { anchor: "open-media", label: "Open Media sign-in", keywords: "passkey" },
    ],
    content: <div id="ai-key">Key card</div>,
  },
  {
    id: "integrations",
    label: "Integrations",
    summary: "Connected tools.",
    icon: "puzzle",
    items: [{ anchor: "integrations", label: "Key partners", keywords: "suppliers" }],
    content: <div id="integrations">Integrations card</div>,
  },
];

const Harness: React.FC = () => {
  const [active, setActive] = React.useState("profile");
  return <SettingsView sections={sections} activeId={active} onSelect={setActive} />;
};

describe("searchSettings", () => {
  it("matches names and keywords, whole-word name matches first in sidebar order", () => {
    expect(searchSettings(sections, "key").map((hit) => hit.item.label)).toEqual([
      "OpenAI API key",
      "Key partners",
      "Open Media sign-in",
    ]);
    expect(searchSettings(sections, "avatar").map((hit) => hit.item.anchor)).toEqual(["profile-photo"]);
    expect(searchSettings(sections, "   ")).toEqual([]);
  });
});

describe("SettingsView", () => {
  it("shows one section at a time with status in the navigation", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    expect(screen.getByRole("heading", { name: "Profile" })).toBeInTheDocument();
    expect(screen.getByText("Add your OpenAI key")).toBeInTheDocument();
    expect(screen.queryByText("Key card")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /AI & sign-in/ }));
    expect(screen.getByRole("heading", { name: "AI & sign-in" })).toBeInTheDocument();
    expect(screen.getByText("Key card")).toBeInTheDocument();
  });

  it("finds a setting by search and opens its section with Enter", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    fireEvent.keyDown(window, { key: "/" });
    const search = screen.getByPlaceholderText("Search settings");
    expect(search).toHaveFocus();

    await user.type(search, "byok");
    expect(screen.getByRole("heading", { name: /1 setting for/ })).toBeInTheDocument();
    await user.keyboard("{Enter}");

    expect(search).toHaveValue("");
    expect(screen.getByRole("heading", { name: "AI & sign-in" })).toBeInTheDocument();
  });

  it("says so when nothing matches", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.type(screen.getByPlaceholderText("Search settings"), "zzz");
    expect(screen.getByRole("heading", { name: /No settings match/ })).toBeInTheDocument();
  });
});
