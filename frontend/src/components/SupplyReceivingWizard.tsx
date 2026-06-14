import React, { useEffect, useMemo, useState } from 'react';
import type { AxiosError } from 'axios';
import { Loader2 } from 'lucide-react';

import api from '../api';
import type { TaskPoolItem } from '../api/taskPool';

type ReceivingLine = {
  item_id: number;
  product_name: string;
  sku: string;
  shelf_life_days: number | null;
  quantity: number;
  actualQty: string;
  manufactureDate: string;
  note: string;
};

type ReceivingTaskDetail = {
  id: number;
  status: string;
  supply_order: {
    id: number;
    planned_receiving_date?: string | null;
    items: {
      id: number;
      quantity: number;
      product_detail?: {
        name: string;
        sku: string;
        shelf_life_days?: number | null;
      };
    }[];
  };
};

type Props = {
  task: TaskPoolItem;
  onDone: () => void;
};

function parseApiError(err: unknown, fallback: string): string {
  const ax = err as AxiosError<{ detail?: string } & Record<string, unknown>>;
  const detail = ax.response?.data?.detail;
  if (typeof detail === 'string') {
    return detail;
  }
  const data = ax.response?.data;
  if (data && typeof data === 'object') {
    for (const val of Object.values(data)) {
      if (Array.isArray(val) && typeof val[0] === 'string') {
        return val[0];
      }
      if (typeof val === 'string') {
        return val;
      }
    }
  }
  return fallback;
}

function formatPlannedDate(iso: string | null | undefined): string {
  if (!iso) {
    return '';
  }
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) {
    return iso;
  }
  return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium' }).format(d);
}

function tracksExpiry(shelfLifeDays: number | null | undefined): boolean {
  return shelfLifeDays != null && shelfLifeDays > 0;
}

function previewExpirationDate(manufactureDate: string, shelfLifeDays: number): string {
  const base = new Date(`${manufactureDate}T00:00:00`);
  if (Number.isNaN(base.getTime())) {
    return '';
  }
  base.setDate(base.getDate() + shelfLifeDays);
  return base.toISOString().slice(0, 10);
}

function formatRuDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) {
    return iso;
  }
  return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium' }).format(d);
}

export function SupplyReceivingWizard({ task, onDone }: Props): React.ReactElement {
  const [detail, setDetail] = useState<ReceivingTaskDetail | null>(null);
  const [lines, setLines] = useState<ReceivingLine[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState(task.status);
  const [confirmDiscrepancies, setConfirmDiscrepancies] = useState(false);

  const plannedDate =
    detail?.supply_order.planned_receiving_date ?? task.planned_receiving_date ?? null;

  useEffect(() => {
    const load = async (): Promise<void> => {
      try {
        const { data } = await api.get<ReceivingTaskDetail>(
          `/receiving-tasks/${task.id}/`,
        );
        setDetail(data);
        setStatus(data.status);
        setLines(
          data.supply_order.items.map((item) => ({
            item_id: item.id,
            product_name: item.product_detail?.name ?? `Товар #${item.id}`,
            sku: item.product_detail?.sku ?? '—',
            shelf_life_days: item.product_detail?.shelf_life_days ?? null,
            quantity: item.quantity,
            actualQty: String(item.quantity),
            manufactureDate: '',
            note: '',
          })),
        );
      } catch {
        setError('Не удалось загрузить заказ.');
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [task.id]);

  const discrepancyLines = useMemo(() => {
    return lines.filter((line) => {
      const actual = Math.floor(Number(line.actualQty) || 0);
      return actual !== line.quantity;
    });
  }, [lines]);

  const missingNotes = discrepancyLines.some((line) => !line.note.trim());

  const accept = async (): Promise<void> => {
    setSaving(true);
    setError(null);
    try {
      const { data } = await api.post<ReceivingTaskDetail>(
        `/receiving-tasks/${task.id}/accept/`,
      );
      setStatus(data.status);
    } catch (err) {
      setError(parseApiError(err, 'Не удалось взять задачу.'));
    } finally {
      setSaving(false);
    }
  };

  const complete = async (): Promise<void> => {
    for (const line of lines) {
      if (tracksExpiry(line.shelf_life_days) && !line.manufactureDate) {
        setError(`Укажите дату производства: ${line.product_name}`);
        return;
      }
    }
    if (discrepancyLines.length > 0) {
      if (missingNotes) {
        setError('Заполните примечание для каждой позиции с расхождением.');
        return;
      }
      if (!confirmDiscrepancies) {
        setError('Подтвердите расхождения перед приёмкой.');
        return;
      }
    }
    setSaving(true);
    setError(null);
    try {
      await api.post(`/receiving-tasks/${task.id}/complete/`, {
        lines: lines.map((line) => ({
          item_id: line.item_id,
          manufacture_date: tracksExpiry(line.shelf_life_days)
            ? line.manufactureDate
            : null,
          actual_quantity: Math.max(0, Math.floor(Number(line.actualQty) || 0)),
          discrepancy_note: line.note.trim(),
        })),
      });
      onDone();
    } catch (err) {
      setError(parseApiError(err, 'Не удалось подтвердить приёмку.'));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="mt-4 flex justify-center py-4">
        <Loader2 className="h-6 w-6 animate-spin text-emerald-400" />
      </div>
    );
  }

  const inProgress = status === 'IN_PROGRESS';
  const canAccept = status === 'CREATED';
  const canComplete =
    inProgress &&
    !missingNotes &&
    (discrepancyLines.length === 0 || confirmDiscrepancies);

  return (
    <div className="mt-4 space-y-3 border-t border-slate-700 pt-4">
      {error ? (
        <p className="text-sm text-rose-300" role="alert">
          {error}
        </p>
      ) : null}
      <p className="text-xs text-slate-400">
        Заказ #{detail?.supply_order.id ?? task.supply_order_id}. Сверьте количество и даты
        производства.
      </p>
      {plannedDate ? (
        <p className="text-xs text-sky-300">
          Плановая дата приёмки:{' '}
          <strong className="text-sky-100">{formatPlannedDate(plannedDate)}</strong>
        </p>
      ) : null}

      {discrepancyLines.length > 0 ? (
        <div className="rounded-lg border border-amber-500/50 bg-amber-950/30 p-3">
          <h4 className="mb-2 text-sm font-medium text-amber-100">Сводка расхождений</h4>
          <table className="w-full text-left text-xs text-slate-300">
            <thead>
              <tr className="border-b border-amber-700/40 text-slate-500">
                <th className="py-1 pr-2">Товар</th>
                <th className="py-1 pr-2 text-right">Заказано</th>
                <th className="py-1 pr-2 text-right">Факт</th>
                <th className="py-1">Примечание</th>
              </tr>
            </thead>
            <tbody>
              {discrepancyLines.map((line) => (
                <tr key={line.item_id} className="border-b border-amber-900/30">
                  <td className="py-1.5 pr-2 text-slate-100">{line.product_name}</td>
                  <td className="py-1.5 pr-2 text-right">{line.quantity}</td>
                  <td className="py-1.5 pr-2 text-right text-amber-200">
                    {Math.floor(Number(line.actualQty) || 0)}
                  </td>
                  <td className="py-1.5">
                    <input
                      type="text"
                      disabled={!inProgress}
                      placeholder="Обязательно"
                      value={line.note}
                      onChange={(e) => {
                        const v = e.target.value;
                        setLines((prev) =>
                          prev.map((l) =>
                            l.item_id === line.item_id ? { ...l, note: v } : l,
                          ),
                        );
                      }}
                      className="w-full rounded border border-amber-600/40 bg-slate-900 px-2 py-1 text-white disabled:opacity-60"
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {missingNotes ? (
            <p className="mt-2 text-xs text-rose-300">
              Укажите причину для каждой позиции с расхождением.
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="space-y-3">
        {lines.map((line) => {
          const ordered = line.quantity;
          const actual = Math.floor(Number(line.actualQty) || 0);
          const mismatch = actual !== ordered;
          const needsDate = tracksExpiry(line.shelf_life_days);
          const expiryPreview =
            needsDate &&
            line.manufactureDate &&
            line.shelf_life_days != null &&
            line.shelf_life_days > 0
              ? previewExpirationDate(line.manufactureDate, line.shelf_life_days)
              : '';
          return (
            <div
              key={line.item_id}
              className={`rounded-lg border p-3 text-sm ${
                mismatch
                  ? 'border-amber-500/50 bg-amber-950/30'
                  : 'border-slate-700 bg-slate-950/50'
              }`}
            >
              <div className="font-medium text-slate-100">{line.product_name}</div>
              <div className="text-xs text-slate-500">SKU {line.sku}</div>
              <div className="mt-2 text-xs text-slate-400">
                Заказано: <strong className="text-slate-200">{ordered}</strong>
              </div>
              <div className="mt-2 grid gap-2">
                <label className="block text-xs text-slate-400">
                  Факт. кол-во
                  <input
                    type="number"
                    min={0}
                    disabled={!inProgress}
                    value={line.actualQty}
                    onChange={(e) => {
                      const v = e.target.value;
                      setLines((prev) =>
                        prev.map((l) =>
                          l.item_id === line.item_id ? { ...l, actualQty: v } : l,
                        ),
                      );
                    }}
                    className="mt-1 w-full rounded border border-slate-600 bg-slate-900 px-2 py-2 text-white disabled:opacity-60"
                  />
                </label>
                {needsDate ? (
                  <>
                    <label className="block text-xs text-slate-400">
                      Дата производства
                      <input
                        type="date"
                        disabled={!inProgress}
                        value={line.manufactureDate}
                        onChange={(e) => {
                          const v = e.target.value;
                          setLines((prev) =>
                            prev.map((l) =>
                              l.item_id === line.item_id
                                ? { ...l, manufactureDate: v }
                                : l,
                            ),
                          );
                        }}
                        className="mt-1 w-full rounded border border-slate-600 bg-slate-900 px-2 py-2 text-white disabled:opacity-60"
                      />
                    </label>
                    {expiryPreview ? (
                      <p className="text-xs text-sky-300">
                        Срок годности до:{' '}
                        <strong>{formatRuDate(expiryPreview)}</strong>
                        {line.shelf_life_days != null
                          ? ` (+${line.shelf_life_days} дн. из номенклатуры)`
                          : null}
                      </p>
                    ) : null}
                  </>
                ) : (
                  <p className="text-xs text-slate-500">Срок годности не контролируется</p>
                )}
                {mismatch ? (
                  <label className="block text-xs text-amber-200/90">
                    Примечание (расхождение)
                    <input
                      type="text"
                      disabled={!inProgress}
                      placeholder="Причина"
                      value={line.note}
                      onChange={(e) => {
                        const v = e.target.value;
                        setLines((prev) =>
                          prev.map((l) =>
                            l.item_id === line.item_id ? { ...l, note: v } : l,
                          ),
                        );
                      }}
                      className="mt-1 w-full rounded border border-amber-600/40 bg-slate-900 px-2 py-2 text-white disabled:opacity-60"
                    />
                  </label>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>

      {inProgress && discrepancyLines.length > 0 ? (
        <label className="flex items-start gap-2 text-sm text-amber-100">
          <input
            type="checkbox"
            checked={confirmDiscrepancies}
            onChange={(e) => setConfirmDiscrepancies(e.target.checked)}
            className="mt-1"
          />
          <span>Подтверждаю расхождения с заказом</span>
        </label>
      ) : null}

      {canAccept ? (
        <button
          type="button"
          disabled={saving}
          onClick={() => void accept()}
          className="w-full rounded-lg bg-sky-600 py-3 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50 min-h-[44px]"
        >
          Взять в работу
        </button>
      ) : null}
      {inProgress ? (
        <button
          type="button"
          disabled={saving || !canComplete}
          onClick={() => void complete()}
          className="w-full rounded-lg bg-emerald-600 py-3 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50 min-h-[44px]"
        >
          {saving ? (
            <Loader2 className="mx-auto h-5 w-5 animate-spin" />
          ) : (
            'Подтвердить приёмку'
          )}
        </button>
      ) : null}
      {inProgress && !canComplete && discrepancyLines.length > 0 ? (
        <p className="text-center text-xs text-slate-500">
          Заполните примечания и отметьте подтверждение расхождений.
        </p>
      ) : null}
    </div>
  );
}
