import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BarChartCard } from "./BarChartCard";

describe("BarChartCard", () => {
  it("shows an empty message when there is no data", () => {
    render(<BarChartCard title="Category Performance" data={[]} />);
    expect(screen.getByText(/no data available/i)).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("renders a bar and legend entry per datum", () => {
    render(
      <BarChartCard
        title="Category Performance"
        data={[
          { label: "Tools", value: 100 },
          { label: "Electronics", value: 250 },
        ]}
      />,
    );

    expect(screen.getByRole("img", { name: "Category Performance" })).toBeInTheDocument();
    expect(screen.getByTestId("bar-Tools")).toBeInTheDocument();
    expect(screen.getByTestId("bar-Electronics")).toBeInTheDocument();
    expect(screen.getByText("Tools")).toBeInTheDocument();
    expect(screen.getByText("250")).toBeInTheDocument();
  });
});
