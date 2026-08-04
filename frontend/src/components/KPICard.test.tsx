import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { KPICard } from "./KPICard";

describe("KPICard", () => {
  it("formats a USD value as currency", () => {
    render(<KPICard label="Revenue" value={1234.5} unit="USD" />);
    expect(screen.getByRole("group", { name: "Revenue" })).toBeInTheDocument();
    expect(screen.getByText("$1,234.50")).toBeInTheDocument();
  });

  it("formats a percent value with a % suffix", () => {
    render(<KPICard label="Gross Margin" value={42.567} unit="%" />);
    expect(screen.getByText("42.57%")).toBeInTheDocument();
  });

  it("formats a plain count without a unit suffix", () => {
    render(<KPICard label="Stockouts" value={7} unit="count" />);
    expect(screen.getByText("7")).toBeInTheDocument();
  });

  it("formats a multiple with an x suffix", () => {
    render(<KPICard label="Inventory Turnover" value={1.5} unit="x" />);
    expect(screen.getByText("1.5x")).toBeInTheDocument();
  });
});
