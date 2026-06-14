import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Loader2, X } from 'lucide-react';
import type { AxiosError } from 'axios';

import api from '../../api';

export type OccupiedSlotInfo = {
  slot_id: number;
  row_index: number;
  col_index: number;
  product_id: number | null;
  product_name: string | null;
  current_qty: number;
  has_clearing_task: boolean;
  planogram_id: number | null;
};

export type EquipmentModificationInfo = {
  can_modify_layout: boolean;
  can_delete: boolean;
  blockers: string[];
  occupied_slots: OccupiedSlotInfo[];
};

type Props = {
  open: boolean;
  mode: 'delete' | 'layout';
  equipmentName: string;
  info: EquipmentModificationInfo | null;
  onClose: () => void;
  onClearingTaskCreated: () => void;
};

function parseApiError(err: unknown, fallback: string): string {
  const ax = err as AxiosError<{ detail?: string }>;
  const detail = ax.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
}

export function EquipmentModificationModal({
  open,
  mode,
  equipmentName,
  info,
  onClose,
  onClearingTaskCreated,
}: Props): React.ReactElement | null {
  const [creatingSlotId, setCreatingSlotId] = useState<number | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [localOk, setLocalOk] = useState<string | null>(null);

  if (!open || !info) {
    return null;
  }

  const title =
    mode === 'delete'
      ? `Нельзя удалить «${equipmentName}»`
      : `Нельзя изменить конфигурацию «${equipmentName}»`;

  const createClearingTask = async (slotId: number): Promise<void> => {
    setCreatingSlotId(slotId);
    setLocalError(null);
    setLocalOk(null);
    try {
      await api.post('/shelf-clearing-tasks/', { slot_id: slotId });
      setLocalOk('Задание на уборку создано. Сотрудник уберёт товар на склад.');
      onClearingTaskCreated();
    } catch (err) {
      setLocalError(parseApiError(err, 'Не удалось создать задание на уборку.'));
    } finally {
      setCreatingSlotId(null);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4">
      <div
        role="dialog"
        aria-modal="true"
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl border border-slate-600 bg-slate-900 shadow-2xl"
      >
        <div className="flex items-start justify-between gap-2 border-b border-slate-700 px-4 py-3">
          <div>
            <h3 className="text-base font-semibold text-rose-100">{title}</h3>
            <p className="mt-1 text-sm text-slate-400">
              Сначала отмените задачи выкладки и уберите товар с полок.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-600 p-2 text-slate-300 hover:bg-slate-800"
            aria-label="Закрыть"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4 px-4 py-4">
          {info.blockers.length > 0 ? (
            <ul className="list-inside list-disc space-y-1 text-sm text-amber-100">
              {info.blockers.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          ) : null}

          {localError ? (
            <p className="rounded-md border border-rose-500/40 bg-rose-950/30 px-3 py-2 text-sm text-rose-100">
              {localError}
            </p>
          ) : null}
          {localOk ? (
            <p className="rounded-md border border-emerald-500/40 bg-emerald-950/30 px-3 py-2 text-sm text-emerald-100">
              {localOk}
            </p>
          ) : null}

          {info.occupied_slots.length > 0 ? (
            <div>
              <h4 className="mb-2 text-sm font-semibold text-slate-200">Слоты с товаром</h4>
              <ul className="space-y-2">
                {info.occupied_slots.map((slot) => (
                  <li
                    key={slot.slot_id}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-700 bg-slate-950/50 px-3 py-2 text-xs text-slate-300"
                  >
                    <span>
                      Полка {slot.row_index + 1}, яч. {slot.col_index + 1}
                      {slot.product_name ? `: ${slot.product_name}` : ''} — {slot.current_qty} шт.
                    </span>
                    {slot.has_clearing_task ? (
                      <span className="text-violet-300">Задание создано</span>
                    ) : (
                      <button
                        type="button"
                        disabled={creatingSlotId !== null}
                        onClick={() => void createClearingTask(slot.slot_id)}
                        className="rounded-md border border-violet-500/60 px-2 py-1 text-violet-100 disabled:opacity-50"
                      >
                        {creatingSlotId === slot.slot_id ? (
                          <Loader2 className="inline h-3 w-3 animate-spin" />
                        ) : (
                          'Задание на уборку'
                        )}
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <p className="text-xs text-slate-500">
            Отмените активные задачи выкладки в{' '}
            <Link to="/admin?tab=tasks" className="text-sky-300 underline">
              центре задач
            </Link>
            .
          </p>
        </div>

        <div className="border-t border-slate-700 px-4 py-3">
          <button
            type="button"
            onClick={onClose}
            className="w-full rounded-md border border-slate-600 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800"
          >
            Закрыть
          </button>
        </div>
      </div>
    </div>
  );
}
