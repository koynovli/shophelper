import React, { useState } from 'react';
import { CheckCircle2, XCircle } from 'lucide-react';
import type { AxiosError } from 'axios';

import api from '../../api';
import { BarcodeScanner } from './BarcodeScanner';

type ScanCheckResponse = {
  matches_picking: boolean;
  message: string;
  product: { id: number; name: string; is_marked: boolean } | null;
  suggested_tasks: Array<{ id: number; quantity: number; destination: string }>;
  best_task?: { id: number; destination: string; quantity: number };
};

export function ScanVerifyPanel(): React.ReactElement {
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
      setError(ax.response?.data?.detail ?? 'Не удалось проверить код.');
      setResult(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <h3 className="text-sm font-semibold text-slate-200">Проверить товар на складе</h3>
      <p className="text-xs text-slate-500">
        Отсканируйте упаковку, чтобы понять — нужен ли товар для текущих задач выкладки.
      </p>
      <BarcodeScanner onScan={(code) => void handleScan(code)} disabled={busy} />
      {error ? <p className="text-sm text-rose-200">{error}</p> : null}
      {result ? (
        <div
          className={`rounded-lg border px-3 py-2 text-sm ${
            result.matches_picking
              ? 'border-emerald-500/40 bg-emerald-950/30 text-emerald-100'
              : 'border-amber-500/40 bg-amber-950/30 text-amber-100'
          }`}
        >
          <div className="flex items-start gap-2">
            {result.matches_picking ? (
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
            ) : (
              <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
            )}
            <div>
              <p>{result.message}</p>
              {result.suggested_tasks.length > 0 ? (
                <ul className="mt-2 space-y-1 text-xs opacity-90">
                  {result.suggested_tasks.map((t) => (
                    <li key={t.id}>
                      Задача #{t.id}: {t.quantity} шт. → {t.destination}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
