import React, { useState } from 'react';
import { AlertTriangle, CheckCircle2, Loader2, Send } from 'lucide-react';
import type { AxiosError } from 'axios';

import api from '../api';
import type { MapTaskHighlight, TaskPoolItem } from '../api/taskPool';
import { usePlacementTaskChat } from '../hooks/usePlacementTaskChat';
import { BarcodeScanner } from './scan/BarcodeScanner';

type Props = {
  task: TaskPoolItem;
  onDone: () => void;
  onShowOnMap?: (target: MapTaskHighlight) => void;
};

export function PlacementTaskWizard({
  task,
  onDone,
  onShowOnMap,
}: Props): React.ReactElement {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [localStatus, setLocalStatus] = useState(task.status);
  const [scansDone, setScansDone] = useState(task.scans_done ?? 0);
  const [chatText, setChatText] = useState('');
  const scansRequired = task.scans_required ?? task.quantity ?? 0;
  const { messages, send: sendChat } = usePlacementTaskChat({
    taskId: task.id,
    enabled: localStatus === 'IN_PROGRESS',
  });

  const extractErrorMessage = (err: unknown, fallback: string): string => {
    const ax = err as AxiosError<{ detail?: unknown }>;
    const data = ax.response?.data;
    if (!data) {
      return fallback;
    }
    const { detail } = data;
    if (typeof detail === 'string' && detail.trim()) {
      return detail;
    }
    return fallback;
  };

  const handleError = (err: unknown, fallback: string): void => {
    setError(extractErrorMessage(err, fallback));
  };

  const accept = async (): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.post<{ scans_done?: number }>(`/placement-tasks/${task.id}/accept/`);
      setLocalStatus('IN_PROGRESS');
      if (typeof r.data.scans_done === 'number') {
        setScansDone(r.data.scans_done);
      }
    } catch (err) {
      handleError(err, 'Не удалось взять задачу.');
    } finally {
      setBusy(false);
    }
  };

  const scanUnit = async (rawCode: string): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.post<{ scans_done?: number }>(`/placement-tasks/${task.id}/scan-unit/`, {
        raw_code: rawCode,
      });
      setScansDone(r.data.scans_done ?? scansDone + 1);
    } catch (err) {
      handleError(err, 'Скан не принят.');
    } finally {
      setBusy(false);
    }
  };

  const reportProblem = async (): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      await api.post(`/placement-tasks/${task.id}/fail/`, {
        reason: chatText.trim() || 'Проблема на складе',
      });
      onDone();
    } catch (err) {
      handleError(err, 'Не удалось отметить проблему.');
    } finally {
      setBusy(false);
    }
  };

  const complete = async (): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      await api.post(`/placement-tasks/${task.id}/complete/`);
      onDone();
    } catch (err) {
      handleError(err, 'Не удалось завершить задачу.');
    } finally {
      setBusy(false);
    }
  };

  const scansOk = scansDone >= scansRequired;

  return (
    <div className="mt-4 space-y-3 border-t border-slate-800 pt-4">
      {error ? (
        <p className="rounded-lg border border-rose-500/40 bg-rose-950/30 px-3 py-2 text-sm text-rose-100">
          {error}
        </p>
      ) : null}

      {localStatus === 'CREATED' || localStatus === 'PENDING' ? (
        <button
          type="button"
          disabled={busy}
          onClick={() => void accept()}
          className="flex w-full min-h-[44px] items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-3 text-sm font-semibold text-white disabled:opacity-60"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          Взять в работу
        </button>
      ) : null}

      {localStatus === 'IN_PROGRESS' ? (
        <>
          <div className="rounded-lg border border-slate-700 bg-slate-950/50 px-3 py-2 text-xs text-slate-300">
            Сканов товара: {scansDone} / {scansRequired}
            {task.product?.is_marked ? ' (каждая единица)' : ''}
          </div>

          {!scansOk ? (
            <BarcodeScanner
              onScan={(code) => void scanUnit(code)}
              disabled={busy}
              label={
                task.product?.is_marked
                  ? 'Скан маркировки (Data Matrix)'
                  : 'Скан GTIN/EAN товара'
              }
            />
          ) : null}

          <button
            type="button"
            disabled={busy || !scansOk}
            onClick={() => void complete()}
            className="flex w-full min-h-[44px] items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-3 text-sm font-semibold text-white disabled:opacity-60"
          >
            {busy ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <CheckCircle2 className="h-4 w-4" aria-hidden />
            )}
            Завершить выкладку
          </button>
          {task.equipment?.id && onShowOnMap ? (
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                onShowOnMap({
                  equipmentId: task.equipment!.id,
                  slotId: task.slot_info?.id ?? null,
                  taskId: task.id,
                })
              }
              className="w-full rounded-xl border border-sky-500/60 bg-sky-900/40 px-4 py-2 text-sm font-medium text-sky-100 disabled:opacity-50"
            >
              На карте
            </button>
          ) : null}
        </>
      ) : null}

      {localStatus === 'IN_PROGRESS' ? (
        <div className="space-y-2 rounded-xl border border-slate-700 bg-slate-900/50 p-3">
          <p className="text-xs font-medium text-slate-400">Чат с менеджером</p>
          <ul className="max-h-32 space-y-1 overflow-y-auto text-xs text-slate-300">
            {messages.map((m) => (
              <li key={m.id}>
                <span className="text-slate-500">{m.sender_username ?? '—'}: </span>
                {m.text}
              </li>
            ))}
          </ul>
          <div className="flex gap-2">
            <input
              value={chatText}
              onChange={(e) => setChatText(e.target.value)}
              placeholder="Сообщение…"
              className="min-h-[40px] flex-1 rounded-lg border border-slate-700 bg-slate-950 px-2 text-sm"
            />
            <button
              type="button"
              disabled={busy || !chatText.trim()}
              onClick={() => {
                void sendChat(chatText).then(() => setChatText(''));
              }}
              className="rounded-lg bg-slate-700 px-3 py-2 text-slate-100 disabled:opacity-50"
              aria-label="Отправить"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
          <button
            type="button"
            disabled={busy}
            onClick={() => void reportProblem()}
            className="flex w-full min-h-[44px] items-center justify-center gap-2 rounded-xl border border-amber-500/50 bg-amber-950/30 px-4 py-2 text-sm font-medium text-amber-100 disabled:opacity-60"
          >
            <AlertTriangle className="h-4 w-4" aria-hidden />
            Проблема
          </button>
        </div>
      ) : null}
    </div>
  );
}
