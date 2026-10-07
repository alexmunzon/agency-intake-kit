import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Button } from "@/components/ui/button";

describe("Button", () => {
  it("renders its label", () => {
    render(<Button>Run intake</Button>);
    expect(screen.getByRole("button", { name: "Run intake" })).toBeInTheDocument();
  });
  it("keeps a disabled primary action unavailable and labeled", () => {
    const onClick = vi.fn();
    render(<Button disabled onClick={onClick}>Download decisions</Button>);
    const button = screen.getByRole("button", { name: "Download decisions" });
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });
});
