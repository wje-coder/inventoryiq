import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { makeDataset } from "../test/testUtils";
import { AnalyticsFilters, EMPTY_ANALYTICS_FILTERS } from "./AnalyticsFilters";

describe("AnalyticsFilters", () => {
  it("lists every dataset in the selector", () => {
    const datasets = [
      makeDataset({ id: "1", display_name: "Q1 Sales" }),
      makeDataset({ id: "2", display_name: "Q2 Sales" }),
    ];

    render(
      <AnalyticsFilters
        datasets={datasets}
        selectedDatasetId="1"
        onDatasetChange={vi.fn()}
        filters={EMPTY_ANALYTICS_FILTERS}
        onFiltersChange={vi.fn()}
      />,
    );

    expect(screen.getByRole("option", { name: "Q1 Sales" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Q2 Sales" })).toBeInTheDocument();
  });

  it("calls onDatasetChange when a different dataset is selected", async () => {
    const user = userEvent.setup();
    const onDatasetChange = vi.fn();
    const datasets = [
      makeDataset({ id: "1", display_name: "Q1 Sales" }),
      makeDataset({ id: "2", display_name: "Q2 Sales" }),
    ];

    render(
      <AnalyticsFilters
        datasets={datasets}
        selectedDatasetId="1"
        onDatasetChange={onDatasetChange}
        filters={EMPTY_ANALYTICS_FILTERS}
        onFiltersChange={vi.fn()}
      />,
    );

    await user.selectOptions(screen.getByLabelText("Dataset"), "2");
    expect(onDatasetChange).toHaveBeenCalledWith("2");
  });

  it("calls onFiltersChange with the updated field when typing into a filter", async () => {
    const user = userEvent.setup();
    const onFiltersChange = vi.fn();

    render(
      <AnalyticsFilters
        datasets={[]}
        selectedDatasetId={null}
        onDatasetChange={vi.fn()}
        filters={EMPTY_ANALYTICS_FILTERS}
        onFiltersChange={onFiltersChange}
      />,
    );

    await user.type(screen.getByLabelText("Category"), "T");
    expect(onFiltersChange).toHaveBeenCalledWith({ ...EMPTY_ANALYTICS_FILTERS, category: "T" });
  });
});
