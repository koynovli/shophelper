import React, { useState } from 'react';
import { CheckCircle2, Loader2 } from 'lucide-react';
import type { AxiosError } from 'axios';

import api from '../api';
import type { TaskPoolItem } from '../api/taskPool';
import { BarcodeScanner } from './scan/BarcodeScanner';

type Props = {
  task: TaskPoolItem;
  onDone: () => void;
};

export function ShelfClearingTaskWizard({ task, onDone }: Props): React.ReactElement {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [localStatus, setLocalStatus] = useState(task.status);
  const [lastScanCode, setLastScanCode] = useState('');

  const handleError = (err: unknown, fallback: string): void => {
    const ax = err as AxiosError<{ detail?: string }>;
    const detail = ax.response?.data?.detail;
    setError(typeof detail === 'string' ? detail : fallback);
  };

  const accept = async (): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      await api.post(`/shelf-clearing-tasks/${task.id}/accept/`);
      setLocalStatus('IN_PROGRESS');
    } catch (err) {
      handleError(err, 'Не удалось взять задание.');
    } finally {
      setBusy(false);
    }
  };

  const scanProduct = async (rawCode: string): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.post<{ product?: { id: number } | null }>(
        '/scan/resolve/',
        { raw_code: rawCode },
      );
      if (!r.data.product || r.data.product.id !== task.product?.id) {
        setError('Отсканирован другой товар или код не распознан.');
        return;
      }
      setLastScanCode(rawCode.trim());
    } catch (err) {
      handleError(err, 'Скан не принят.');
    } finally {
      setBusy(false);
    }
  };

  const complete = async (): Promise<void> => {
    if (!lastScanCode) {
      setError('Отсканируйте код товара на полке.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.post(`/shelf-clearing-tasks/${task.id}/complete/`, {
        raw_code: lastScanCode,
      });
      onDone();
    } catch (err) {
      handleError(err, 'Не удалось завершить задание.');
    } finally {
      setBusy(false);
    }
  };

  const productScanned = Boolean(lastScanCode);

  return (
    <div className="mt-4 space-y-3 border-t border-slate-800 pt-4">
      {task.destination ? (
        <p className="text-sm text-slate-300">{task.destination}</p>
      ) : null}
      {task.product ? (
        <p className="text-xs text-slate-500">
          {task.product.name} — {task.quantity ?? 0} шт.
        </p>
      ) : null}

      {error ? (
        <p className="rounded-lg border border-rose-500/40 bg-rose-950/30 px-3 py-2 text-sm text-rose-100">
          {error}
        </p>
      ) : null}

      {localStatus === 'CREATED' ? (
        <button
          type="button"
          disabled={busy}
          onClick={() => void accept()}
          className="flex w-full min-h-[44px] items-center justify-center gap-2 rounded-xl bg-violet-600 px-4 py-3 text-sm font-semibold text-white disabled:opacity-60"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          Взять задание
        </button>
      ) : null}

      {localStatus === 'IN_PROGRESS' ? (
        <>
          {!productScanned ? (
            <BarcodeScanner
              onScan={(code) => void scanProduct(code)}
              disabled={busy}
              label="Скан GTIN/EAN или SKU товара на полке"
            />
          ) : (
            <p className="text-xs text-emerald-300">Товар отсканирован</p>
          )}

          <button
            type="button"
            disabled={busy || !productScanned}
            onClick={() => void complete()}
            className="flex w-full min-h-[44px] items-center justify-center gap-2 rounded-xl bg-violet-600 px-4 py-3 text-sm font-semibold text-white disabled:opacity-60"
          >
            {busy ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <CheckCircle2 className="h-4 w-4" aria-hidden />
            )}
            Товар убран на склад
          </button>
        </>
      ) : null}
    </div>
  );
}
