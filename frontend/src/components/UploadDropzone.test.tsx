import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { installXhrMock, makeDataset } from "../test/testUtils";
import { UploadDropzone } from "./UploadDropzone";

function csvFile(name = "sales.csv", contents = "a,b\n1,2\n"): File {
  return new File([contents], name, { type: "text/csv" });
}

describe("UploadDropzone", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the upload form with accepted formats and the size limit", () => {
    render(<UploadDropzone onUploaded={vi.fn()} />);

    expect(screen.getByRole("heading", { name: /upload a dataset/i })).toBeInTheDocument();
    expect(screen.getByText(/\.csv/i)).toBeInTheDocument();
    expect(screen.getByText(/\.xlsx/i)).toBeInTheDocument();
    expect(screen.getByText(/max size/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/choose a dataset file to upload/i)).toBeInTheDocument();
  });

  it("rejects an unsupported file type without starting an upload", async () => {
    // The input's `accept=".csv,.xlsx"` already stops a real browser's
    // file picker from offering a .pdf at all - user-event simulates that
    // same filtering by default, which would silently drop this file
    // before it ever reached our code. Disable it here so this test can
    // exercise our own validation, which is what actually protects the
    // drag-and-drop path (drag-and-drop never respects `accept`).
    const user = userEvent.setup({ applyAccept: false });
    const onUploaded = vi.fn();
    const { requests } = installXhrMock(() => ({ status: 201, body: makeDataset() }));

    render(<UploadDropzone onUploaded={onUploaded} />);

    const input = screen.getByLabelText(/choose a dataset file to upload/i);
    const badFile = new File(["not a spreadsheet"], "report.pdf", { type: "application/pdf" });
    await user.upload(input, badFile);

    expect(await screen.findByRole("alert")).toHaveTextContent(/unsupported file type/i);
    expect(requests).toHaveLength(0);
    expect(onUploaded).not.toHaveBeenCalled();
  });

  it("shows upload progress while the file is uploading", async () => {
    const user = userEvent.setup();
    installXhrMock(() => ({ status: 201, body: makeDataset() }), { progressSteps: [40, 100] });

    render(<UploadDropzone onUploaded={vi.fn()} />);

    const input = screen.getByLabelText(/choose a dataset file to upload/i);
    await user.upload(input, csvFile());

    const progressBar = await screen.findByRole("progressbar");
    expect(progressBar).toHaveAttribute("aria-valuenow", "100");
  });

  it("calls onUploaded and shows a success message when the upload succeeds", async () => {
    const user = userEvent.setup();
    const onUploaded = vi.fn();
    const dataset = makeDataset({ display_name: "Sales" });
    installXhrMock(() => ({ status: 201, body: dataset }));

    render(<UploadDropzone onUploaded={onUploaded} />);

    const input = screen.getByLabelText(/choose a dataset file to upload/i);
    await user.upload(input, csvFile());

    expect(await screen.findByRole("status")).toHaveTextContent(/uploaded successfully/i);
    await waitFor(() => expect(onUploaded).toHaveBeenCalledWith(dataset));
  });

  it("shows a structured validation error when the upload is rejected", async () => {
    const user = userEvent.setup();
    const onUploaded = vi.fn();
    installXhrMock(() => ({
      status: 422,
      body: {
        detail: {
          code: "DUPLICATE_COLUMN_NAMES",
          message: "The file has duplicate column names.",
          findings: [
            {
              severity: "error",
              code: "DUPLICATE_COLUMN",
              message: "Column 'sku' appears more than once.",
              row_number: null,
              column_name: "sku",
            },
          ],
        },
      },
    }));

    render(<UploadDropzone onUploaded={onUploaded} />);

    const input = screen.getByLabelText(/choose a dataset file to upload/i);
    await user.upload(input, csvFile());

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/duplicate column names/i);
    expect(alert).toHaveTextContent(/appears more than once/i);
    expect(onUploaded).not.toHaveBeenCalled();
  });
});
