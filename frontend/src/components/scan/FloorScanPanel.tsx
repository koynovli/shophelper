import React, { useState } from 'react';
import { MapPinned } from 'lucide-react';
import type { AxiosError } from 'axios';

import api from '../../api';
import { BarcodeScanner } from './BarcodeScanner';

type ScanCheckResponse = {
  matches_picking: boolean;
  message: string;
  best_task?: {
    id: number;
    destination: string;
    quantity: number;
    quantity_display?: string;
    scans_done?: number;
    scans_required?: number;
    scans_done_display?: string;
    scans_required_display?: string;
  };
};

export function FloorScanPanel(): React.ReactElement {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ScanCheckResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleScan = async (rawCode: string): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.post<ScanCheckResponse>('/placement-tasks/scan-check/', {
        raw_code: rawCode,
      });
      setResult(r.data);
    } catch (err) {
      const ax = err as AxiosError<{ detail?: string }>;
      setError(ax.response?.data?.detail ?? 'Не удалось определить место выкладки.');
      setResult(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3 rounded-xl border border-indigo-500/30 bg-indigo-950/20 p-4">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-indigo-100">
        <MapPinned className="h-4 w-4" />
        Скан → куда выложить
      </h3>
      <p className="text-xs text-slate-400">
        Сканируйте товар из тележки — система подскажет целевой слот на полке.
      </p>
      <BarcodeScanner
        onScan={(code) => void handleScan(code)}
        disabled={busy}
        label="Скан товара в зале"
      />
      {error ? <p className="text-sm text-rose-200">{error}</p> : null}
      {result?.best_task ? (
        <div className="rounded-lg border border-indigo-400/40 bg-indigo-900/30 px-3 py-3 text-sm text-indigo-50">
          <p className="font-medium">{result.message}</p>
          <p className="mt-1 text-xs text-indigo-200/80">
            Задача #{result.best_task.id} ·{' '}
            {result.best_task.quantity_display ?? `${result.best_task.quantity} шт.`}
          </p>
        </div>
      ) : null}
      {result && !result.matches_picking ? (
        <p className="text-sm text-amber-200">{result.message}</p>
      ) : null}
    </div>
  );
}
