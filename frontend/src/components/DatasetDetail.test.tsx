import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createFetchMock, jsonResponse, makeDataset, makeDatasetColumn } from "../test/testUtils";
import { DatasetDetail } from "./DatasetDetail";

describe("DatasetDetail", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the preview table for a ready dataset", async () => {
    const dataset = makeDataset({ id: "ds-1", status: "ready", row_count: 2, column_count: 2 });
    const column = makeDatasetColumn({ id: "col-1", source_name: "sku" });

    vi.stubGlobal(
      "fetch",
      createFetchMock([
        {
          match: (url) => url.endsWith("/datasets/ds-1/columns"),
          response: () => jsonResponse({ columns: [column], available_analyses: [] }),
        },
        {
          match: (url) => url.endsWith("/datasets/ds-1/preview"),
          response: () =>
            jsonResponse({
              columns: ["sku", "quantity"],
              rows: [{ sku: "A1", quantity: 5 }],
              returned_row_count: 1,
              total_row_count: 2,
            }),
        },
      ]),
    );

    render(
      <DatasetDetail dataset={dataset} onDatasetUpdated={vi.fn()} onDatasetDeleted={vi.fn()} />,
    );

    const previewTable = await screen.findByRole("table", { name: /dataset preview/i });
    expect(within(previewTable).getByText("A1")).toBeInTheDocument();
    expect(within(previewTable).getByText("5")).toBeInTheDocument();
  });

  it("lets the user map a column to a business field and save the mapping", async () => {
    const user = userEvent.setup();
    const dataset = makeDataset({ id: "ds-2", status: "ready" });
    const column = makeDatasetColumn({ id: "col-1", source_name: "sku", mapped_business_field: null });
    const onDatasetUpdated = vi.fn();

    vi.stubGlobal(
      "fetch",
      createFetchMock([
        {
          match: (url, init) => url.endsWith("/datasets/ds-2/columns") && init?.method !== "PATCH",
          response: () => jsonResponse({ columns: [column], available_analyses: [] }),
        },
        {
          match: (url) => url.endsWith("/datasets/ds-2/preview"),
          response: () =>
            jsonResponse({ columns: [], rows: [], returned_row_count: 0, total_row_count: 0 }),
        },
        {
          match: (url, init) => url.endsWith("/datasets/ds-2/columns") && init?.method === "PATCH",
          response: () =>
            jsonResponse({
              columns: [{ ...column, mapped_business_field: "sku" }],
              available_analyses: ["Inventory turnover"],
            }),
        },
      ]),
    );

    render(
      <DatasetDetail dataset={dataset} onDatasetUpdated={onDatasetUpdated} onDatasetDeleted={vi.fn()} />,
    );

    const select = await screen.findByLabelText(/business field for sku/i);
    await user.selectOptions(select, "sku");
    await user.click(screen.getByRole("button", { name: /save column mapping/i }));

    await waitFor(() => {
      expect(screen.getByText(/inventory turnover/i)).toBeInTheDocument();
    });
    expect(screen.getByRole("status")).toHaveTextContent(/saved/i);
  });
});
