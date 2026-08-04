import type { ProductRanking } from "../api/analytics";

interface ProductRankingTableProps {
  title: string;
  products: ProductRanking[];
}

export function ProductRankingTable({ title, products }: ProductRankingTableProps) {
  return (
    <div className="panel">
      <h3>{title}</h3>
      {products.length === 0 ? (
        <p className="text-muted">No products to show.</p>
      ) : (
        <table aria-label={title}>
          <thead>
            <tr>
              <th scope="col">Product</th>
              <th scope="col">Units sold</th>
              <th scope="col">Revenue</th>
            </tr>
          </thead>
          <tbody>
            {products.map((product, index) => (
              <tr key={`${product.product_id}-${index}`}>
                <td>{product.product_name ?? product.product_id}</td>
                <td>{product.units_sold ?? "—"}</td>
                <td>
                  {product.revenue != null
                    ? product.revenue.toLocaleString(undefined, {
                        style: "currency",
                        currency: "USD",
                        maximumFractionDigits: 0,
                      })
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
