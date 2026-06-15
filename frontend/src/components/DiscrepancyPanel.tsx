import React from 'react';

export type DiscrepancyItemRow = {
  id: number;
  quantity: number;
  quantity_kg?: string | null;
  actual_quantity: number;
  actual_quantity_kg?: string | null;
  discrepancy_note?: string;
  product_detail?: {
    name: string;
    sku: string;
    sale_unit?: 'piece' | 'weight';
  };
  product?: number;
};

function isWeightItem(item: DiscrepancyItemRow): boolean {
  return (
    item.product_detail?.sale_unit === 'weight' || item.quantity_kg != null
  );
}

function formatQty(item: DiscrepancyItemRow, field: 'ordered' | 'actual'): string {
  if (isWeightItem(item)) {
    const kg =
      field === 'ordered'
        ? item.quantity_kg ?? String((item.quantity || 0) / 1000)
        : item.actual_quantity_kg ?? String((item.actual_quantity || 0) / 1000);
    return `${kg} кг`;
  }
  const qty = field === 'ordered' ? item.quantity : item.actual_quantity;
  return `${qty} шт.`;
}

function formatDelta(item: DiscrepancyItemRow): string {
  if (isWeightItem(item)) {
    const ordered =
      Number(item.quantity_kg ?? (item.quantity || 0) / 1000) || 0;
    const actual =
      Number(item.actual_quantity_kg ?? (item.actual_quantity || 0) / 1000) || 0;
    const delta = actual - ordered;
    const formatted = delta.toFixed(3).replace(/\.?0+$/, '');
    return delta > 0 ? `+${formatted} кг` : `${formatted} кг`;
  }
  const delta = item.actual_quantity - item.quantity;
  return delta > 0 ? `+${delta} шт.` : `${delta} шт.`;
}

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
            {rows.map((item) => (
              <tr key={item.id} className="border-b border-amber-900/30">
                <td className="py-1.5 pr-2 text-slate-100">
                  {item.product_detail?.name ?? `#${item.product}`}
                </td>
                <td className="py-1.5 pr-2 font-mono text-[11px]">
                  {item.product_detail?.sku ?? '—'}
                </td>
                <td className="py-1.5 pr-2 text-right">{formatQty(item, 'ordered')}</td>
                <td className="py-1.5 pr-2 text-right text-amber-200">
                  {formatQty(item, 'actual')}
                </td>
                <td
                  className={`py-1.5 pr-2 text-right font-medium ${
                    item.actual_quantity > item.quantity
                      ? 'text-sky-300'
                      : 'text-rose-300'
                  }`}
                >
                  {formatDelta(item)}
                </td>
                <td className="py-1.5 text-slate-200">
                  {item.discrepancy_note?.trim() || '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
