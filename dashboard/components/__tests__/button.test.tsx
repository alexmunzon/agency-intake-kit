import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Button } from "@/components/ui/button";

describe("Button", () => {
  it("renders its label", () => {
    render(<Button>Run intake</Button>);
    expect(screen.getByRole("button", { name: "Run intake" })).toBeInTheDocument();
  });
});
