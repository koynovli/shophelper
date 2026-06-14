import React, { useCallback, useEffect, useState } from 'react';
import { Loader2, Package } from 'lucide-react';
import type { AxiosError } from 'axios';

import api from '../../api';

type PickingGroup = {
  product: {
    id: number;
    name: string;
    sku: string;
    gtin: string | null;
    is_marked: boolean;
  };
  total_qty: number;
  tasks: Array<{
    id: number;
    quantity: number;
    destination: string;
    batch_expiration: string | null;
  }>;
};

export function PickingListPanel(): React.ReactElement {
  const [groups, setGroups] = useState<PickingGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (): Promise<void> => {
    setError(null);
    setLoading(true);
    try {
      const r = await api.get<PickingGroup[]>('/placement-tasks/picking-list/');
      setGroups(Array.isArray(r.data) ? r.data : []);
    } catch (err) {
      const ax = err as AxiosError<{ detail?: string }>;
      setError(ax.response?.data?.detail ?? 'Не удалось загрузить список для сбора.');
      setGroups([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-6 text-slate-400">
        <Loader2 className="h-5 w-5 animate-spin" />
        Загрузка списка…
      </div>
    );
  }

  if (error) {
    return <p className="text-sm text-rose-200">{error}</p>;
  }

  if (groups.length === 0) {
    return (
      <p className="rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-8 text-center text-sm text-slate-400">
        Нет товаров для сбора на склад.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm font-medium text-slate-200">
        <Package className="h-4 w-4 text-emerald-400" />
        Что взять в тележку
      </div>
      <ul className="space-y-2">
        {groups.map((g) => (
          <li
            key={g.product.id}
            className="rounded-xl border border-slate-800 bg-slate-900/60 px-4 py-3"
          >
            <div className="font-medium text-slate-100">{g.product.name}</div>
            <div className="mt-1 text-sm text-emerald-200">Всего: {g.total_qty} шт.</div>
            {g.product.gtin ? (
              <div className="text-xs text-slate-500">GTIN: {g.product.gtin}</div>
            ) : (
              <div className="text-xs text-slate-500">SKU: {g.product.sku}</div>
            )}
            <ul className="mt-2 space-y-1 text-xs text-slate-400">
              {g.tasks.map((t) => (
                <li key={t.id}>
                  {t.quantity} шт. → {t.destination}
                  {t.batch_expiration ? ` (до ${t.batch_expiration})` : ''}
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </div>
  );
}
