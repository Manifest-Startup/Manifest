import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import Input from "../Input";
import Button from "../Button";

describe("Shared controls", () => {
  it("gives each input a unique label association", () => {
    render(<><Input label="Email" /><Input label="Name" /></>);
    expect(screen.getByLabelText("Email")).toHaveAttribute("id");
    expect(screen.getByLabelText("Email").id).not.toBe(screen.getByLabelText("Name").id);
  });

  it("associates errors with the input while preserving help text", () => {
    render(<><p id="hint">Use your work email.</p><Input id="email" label="Email" error="Enter a valid email." aria-describedby="hint" /></>);
    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Email")).toHaveAccessibleDescription("Use your work email. Enter a valid email.");
  });

  it("keeps the disabled variant non-interactive even with disabled=false", () => {
    const onClick = jest.fn();
    render(<Button variant="disabled" disabled={false} onClick={onClick}>Continue</Button>);
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(onClick).not.toHaveBeenCalled();
    expect(screen.getByRole("button")).toBeDisabled();
  });
});
