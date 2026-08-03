import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { makeDataset } from "../test/testUtils";
import { DatasetList } from "./DatasetList";

describe("DatasetList", () => {
  it("shows an empty state when there are no datasets", () => {
    render(
      <DatasetList datasets={[]} selectedId={null} onSelect={vi.fn()} loading={false} error={null} />,
    );

    expect(screen.getByText(/no datasets uploaded yet/i)).toBeInTheDocument();
  });

  it("renders a row per dataset with status, row count, and column count", () => {
    const datasets = [
      makeDataset({
        id: "1",
        display_name: "Q1 Sales",
        status: "ready",
        row_count: 1500,
        column_count: 8,
      }),
      makeDataset({
        id: "2",
        display_name: "Broken Upload",
        status: "failed",
        row_count: null,
        column_count: null,
      }),
    ];

    render(
      <DatasetList
        datasets={datasets}
        selectedId={null}
        onSelect={vi.fn()}
        loading={false}
        error={null}
      />,
    );

    expect(screen.getByRole("table", { name: /uploaded datasets/i })).toBeInTheDocument();
    expect(screen.getByText("Q1 Sales")).toBeInTheDocument();
    expect(screen.getByText("1500")).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
    expect(screen.getByText("Broken Upload")).toBeInTheDocument();
    expect(screen.getAllByText("—")).toHaveLength(2);
    expect(screen.getByText("ready")).toBeInTheDocument();
    expect(screen.getByText("failed")).toBeInTheDocument();
  });

  it("calls onSelect when a row is clicked", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const datasets = [makeDataset({ id: "1", display_name: "Q1 Sales" })];

    render(
      <DatasetList
        datasets={datasets}
        selectedId={null}
        onSelect={onSelect}
        loading={false}
        error={null}
      />,
    );

    await user.click(screen.getByText("Q1 Sales"));
    expect(onSelect).toHaveBeenCalledWith("1");
  });

  it("shows a loading state instead of the table", () => {
    render(
      <DatasetList datasets={[]} selectedId={null} onSelect={vi.fn()} loading={true} error={null} />,
    );

    expect(screen.getByText(/loading datasets/i)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows an error message when loading fails", () => {
    render(
      <DatasetList
        datasets={[]}
        selectedId={null}
        onSelect={vi.fn()}
        loading={false}
        error="Failed to load datasets."
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(/failed to load datasets/i);
  });
});
