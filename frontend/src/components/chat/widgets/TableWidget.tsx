import { lazy, Suspense } from "react";

import type { TableDisplay } from "../../../lib/ohlcv";

const CorrelationBars3D = lazy(() => import("../../CorrelationBars3D"));

export default function TableWidget({ display }: { display: TableDisplay }) {
  return (
    <figure className="chat-table">
      <figcaption>{display.title}</figcaption>
      <table>
        <tbody>
          {display.rows.map(([label, value]) => (
            <tr key={label}>
              <th scope="row">{label}</th>
              <td>{value}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {display.matrix && (
        <Suspense fallback={<div className="chat-widget-loading">Loading 3D view…</div>}>
          <p className="chat-hint">{display.matrix.title ?? "Correlation"}</p>
          <CorrelationBars3D matrix={display.matrix} />
        </Suspense>
      )}
      {display.note && <p className="chat-hint">{display.note}</p>}
    </figure>
  );
}
