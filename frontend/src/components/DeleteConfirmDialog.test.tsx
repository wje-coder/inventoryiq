import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DeleteConfirmDialog } from "./DeleteConfirmDialog";

describe("DeleteConfirmDialog", () => {
  it("asks the user to confirm deletion of the named dataset", () => {
    render(
      <DeleteConfirmDialog datasetName="Q1 Sales" onConfirm={vi.fn()} onCancel={vi.fn()} busy={false} />,
    );

    const dialog = screen.getByRole("alertdialog", { name: /delete dataset/i });
    expect(dialog).toHaveTextContent(/Q1 Sales/);
  });

  it("calls onConfirm when the delete button is clicked", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();

    render(
      <DeleteConfirmDialog datasetName="Q1 Sales" onConfirm={onConfirm} onCancel={vi.fn()} busy={false} />,
    );

    await user.click(screen.getByRole("button", { name: /delete dataset/i }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("calls onCancel when the cancel button is clicked", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();

    render(
      <DeleteConfirmDialog datasetName="Q1 Sales" onConfirm={vi.fn()} onCancel={onCancel} busy={false} />,
    );

    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("disables both buttons while busy", () => {
    render(
      <DeleteConfirmDialog datasetName="Q1 Sales" onConfirm={vi.fn()} onCancel={vi.fn()} busy={true} />,
    );

    expect(screen.getByRole("button", { name: /cancel/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /deleting/i })).toBeDisabled();
  });
});
