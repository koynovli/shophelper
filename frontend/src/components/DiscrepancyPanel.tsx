import React from 'react';

export type DiscrepancyItemRow = {
  id: number;
  quantity: number;
  actual_quantity: number;
  discrepancy_note?: string;
  product_detail?: { name: string; sku: string };
  product?: number;
};

type Props = {
  items: DiscrepancyItemRow[];
};

export function DiscrepancyPanel({ items }: Props): React.ReactElement {
  const rows = items.filter((item) => item.actual_quantity !== item.quantity);

  if (rows.length === 0) {
    return (
      <p className="text-sm text-slate-400">Нет строк с расхождением количества.</p>
    );
  }

  return (
    <div className="rounded-lg border border-amber-500/40 bg-amber-950/20 p-3">
      <h4 className="mb-2 text-sm font-medium text-amber-100">
        Расхождения при приёмке
      </h4>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] text-left text-xs text-slate-300">
          <thead>
            <tr className="border-b border-amber-700/40 text-slate-500">
              <th className="py-1 pr-2">Товар</th>
              <th className="py-1 pr-2">SKU</th>
              <th className="py-1 pr-2 text-right">Заказано</th>
              <th className="py-1 pr-2 text-right">Принято</th>
              <th className="py-1 pr-2 text-right">Δ</th>
              <th className="py-1">Примечание</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((item) => {
              const delta = item.actual_quantity - item.quantity;
              return (
                <tr key={item.id} className="border-b border-amber-900/30">
                  <td className="py-1.5 pr-2 text-slate-100">
                    {item.product_detail?.name ?? `#${item.product}`}
                  </td>
                  <td className="py-1.5 pr-2 font-mono text-[11px]">
                    {item.product_detail?.sku ?? '—'}
                  </td>
                  <td className="py-1.5 pr-2 text-right">{item.quantity}</td>
                  <td className="py-1.5 pr-2 text-right text-amber-200">
                    {item.actual_quantity}
                  </td>
                  <td
                    className={`py-1.5 pr-2 text-right font-medium ${
                      delta > 0 ? 'text-sky-300' : 'text-rose-300'
                    }`}
                  >
                    {delta > 0 ? `+${delta}` : delta}
                  </td>
                  <td className="py-1.5 text-slate-200">
                    {item.discrepancy_note?.trim() || '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
