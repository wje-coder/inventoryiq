import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LineChartCard } from "./LineChartCard";

describe("LineChartCard", () => {
  it("shows an empty message when there is no data", () => {
    render(<LineChartCard title="Monthly Revenue Trend" data={[]} />);
    expect(screen.getByText(/no data available/i)).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("renders a point and legend entry per datum", () => {
    render(
      <LineChartCard
        title="Monthly Revenue Trend"
        data={[
          { label: "2024-01-01", value: 100 },
          { label: "2024-02-01", value: 200 },
        ]}
      />,
    );

    expect(screen.getByRole("img", { name: "Monthly Revenue Trend" })).toBeInTheDocument();
    expect(screen.getByText("2024-01-01")).toBeInTheDocument();
    expect(screen.getByText("200")).toBeInTheDocument();
  });
});
