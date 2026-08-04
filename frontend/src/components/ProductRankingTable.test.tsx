import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProductRankingTable } from "./ProductRankingTable";

describe("ProductRankingTable", () => {
  it("shows an empty message when there are no products", () => {
    render(<ProductRankingTable title="Top Selling Products" products={[]} />);
    expect(screen.getByText(/no products to show/i)).toBeInTheDocument();
  });

  it("renders a row per product with name, units sold, and revenue", () => {
    render(
      <ProductRankingTable
        title="Top Selling Products"
        products={[
          { product_id: "P1", product_name: "Widget", units_sold: 10, revenue: 100 },
          { product_id: "P2", product_name: null, units_sold: 5, revenue: null },
        ]}
      />,
    );

    expect(screen.getByRole("table", { name: "Top Selling Products" })).toBeInTheDocument();
    expect(screen.getByText("Widget")).toBeInTheDocument();
    expect(screen.getByText("$100")).toBeInTheDocument();
    expect(screen.getByText("P2")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
