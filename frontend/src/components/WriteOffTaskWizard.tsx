import React, { useRef, useState } from 'react';
import { CheckCircle2, ImagePlus, Loader2 } from 'lucide-react';
import type { AxiosError } from 'axios';

import api from '../api';
import type { TaskPoolItem } from '../api/taskPool';
import { BarcodeScanner } from './scan/BarcodeScanner';

type Props = {
  task: TaskPoolItem;
  onDone: () => void;
};

export function WriteOffTaskWizard({ task, onDone }: Props): React.ReactElement {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [localStatus, setLocalStatus] = useState(task.status);
  const photoRef = useRef<HTMLInputElement>(null);
  const [photoFile, setPhotoFile] = useState<File | null>(null);
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
      await api.post(`/write-off-tasks/${task.id}/accept/`);
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
      const r = await api.post<{ product?: { id: number } | null; status: string }>(
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
      setError('Отсканируйте код товара.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (photoFile) {
        const form = new FormData();
        form.append('raw_code', lastScanCode);
        form.append('photo', photoFile);
        await api.post(`/write-off-tasks/${task.id}/complete/`, form, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
      } else {
        await api.post(`/write-off-tasks/${task.id}/complete/`, {
          raw_code: lastScanCode,
        });
      }
      onDone();
    } catch (err) {
      handleError(err, 'Не удалось завершить списание.');
    } finally {
      setBusy(false);
    }
  };

  const locationLabel = task.location === 'WAREHOUSE' ? 'Склад' : 'Полка';
  const productScanned = Boolean(lastScanCode);

  return (
    <div className="mt-4 space-y-3 border-t border-slate-800 pt-4">
      {task.destination ? (
        <p className="text-sm text-slate-300">
          <span className="text-slate-500">Куда: </span>
          {task.destination}
        </p>
      ) : (
        <p className="text-sm text-slate-300">
          <span className="text-slate-500">Куда: </span>
          {locationLabel}
        </p>
      )}
      {task.product ? (
        <p className="text-xs text-slate-500">
          {task.product.name} — {task.quantity ?? 0} шт.
          {task.product.is_marked ? ' (маркировка)' : ''}
        </p>
      ) : null}
      {task.batch_expiration ? (
        <p className="text-xs text-amber-300/90">Срок годности партии: {task.batch_expiration}</p>
      ) : null}
      {task.reason ? (
        <p className="text-xs text-slate-400">Причина: {task.reason}</p>
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
          className="flex w-full min-h-[44px] items-center justify-center gap-2 rounded-xl bg-rose-600 px-4 py-3 text-sm font-semibold text-white disabled:opacity-60"
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
              label={
                task.product?.is_marked
                  ? 'Скан Data Matrix (серийный номер)'
                  : 'Скан GTIN/EAN или SKU товара'
              }
            />
          ) : (
            <p className="text-xs text-emerald-300">Товар отсканирован</p>
          )}

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => photoRef.current?.click()}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-600 px-3 py-2 text-xs text-slate-300"
            >
              <ImagePlus className="h-4 w-4" />
              {photoFile ? photoFile.name : 'Фото (необязательно)'}
            </button>
            <input
              ref={photoRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => setPhotoFile(e.target.files?.[0] ?? null)}
            />
          </div>
          <button
            type="button"
            disabled={busy || !productScanned}
            onClick={() => void complete()}
            className="flex w-full min-h-[44px] items-center justify-center gap-2 rounded-xl bg-rose-600 px-4 py-3 text-sm font-semibold text-white disabled:opacity-60"
          >
            {busy ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <CheckCircle2 className="h-4 w-4" aria-hidden />
            )}
            Товар списан
          </button>
        </>
      ) : null}
    </div>
  );
}
