import React, { useState } from 'react';
import { AlertTriangle, CheckCircle2, Loader2, QrCode, Send } from 'lucide-react';
import type { AxiosError } from 'axios';

import api from '../api';
import type { TaskPoolItem } from '../api/taskPool';
import { usePlacementTaskChat } from '../hooks/usePlacementTaskChat';

type Props = {
  task: TaskPoolItem;
  onDone: () => void;
};

export function PlacementTaskWizard({ task, onDone }: Props): React.ReactElement {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [qrInput, setQrInput] = useState('');
  const [localStatus, setLocalStatus] = useState(task.status);
  const [slotVerified, setSlotVerified] = useState(Boolean(task.slot_verified));
  const [chatText, setChatText] = useState('');
  const { messages, send: sendChat } = usePlacementTaskChat({
    taskId: task.id,
    enabled: localStatus === 'IN_PROGRESS',
  });

  const handleError = (err: unknown, fallback: string): void => {
    const ax = err as AxiosError<{ detail?: string }>;
    const detail = ax.response?.data?.detail;
    setError(typeof detail === 'string' ? detail : fallback);
  };

  const accept = async (): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      await api.post(`/placement-tasks/${task.id}/accept/`);
      setLocalStatus('IN_PROGRESS');
    } catch (err) {
      handleError(err, 'Не удалось взять задачу.');
    } finally {
      setBusy(false);
    }
  };

  const verifySlot = async (): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      await api.post(`/placement-tasks/${task.id}/verify-slot/`, {
        qr_token: qrInput.trim(),
      });
      setSlotVerified(true);
    } catch (err) {
      handleError(err, 'QR-код не принят.');
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

  const complete = async (file: File): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append('photo', file);
      await api.post(`/placement-tasks/${task.id}/complete/`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      onDone();
    } catch (err) {
      handleError(err, 'Не удалось завершить задачу.');
    } finally {
      setBusy(false);
    }
  };

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

      {localStatus === 'IN_PROGRESS' && !slotVerified ? (
        <div className="space-y-2">
          <label className="flex items-center gap-2 text-xs text-slate-400">
            <QrCode className="h-4 w-4" aria-hidden />
            UUID с QR-кода полки
          </label>
          <input
            value={qrInput}
            onChange={(e) => setQrInput(e.target.value)}
            placeholder="550e8400-e29b-41d4-a716-446655440000"
            className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
          />
          <button
            type="button"
            disabled={busy || !qrInput.trim()}
            onClick={() => void verifySlot()}
            className="w-full rounded-xl border border-sky-500/60 bg-sky-900/40 px-4 py-2 text-sm font-medium text-sky-100 disabled:opacity-50"
          >
            Подтвердить полку
          </button>
        </div>
      ) : null}

      {localStatus === 'IN_PROGRESS' && slotVerified ? (
        <label className="flex w-full cursor-pointer flex-col items-center gap-2 rounded-xl border border-dashed border-emerald-500/50 bg-emerald-950/20 px-4 py-4 text-sm text-emerald-100">
          <CheckCircle2 className="h-5 w-5" aria-hidden />
          Загрузить фотоотчёт
          <input
            type="file"
            accept="image/*"
            capture="environment"
            className="hidden"
            disabled={busy}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) {
                void complete(file);
              }
            }}
          />
        </label>
      ) : null}

      {localStatus === 'IN_PROGRESS' ? (
        <div className="space-y-2 rounded-xl border border-slate-700 bg-slate-900/50 p-3">
          <p className="text-xs font-medium text-slate-400">Чат с менеджером</p>
          <ul className="max-h-32 space-y-1 overflow-y-auto text-xs text-slate-300">
            {messages.map((m) => (
              <li key={m.id}>
                <span className="text-slate-500">{m.sender_username ?? '—'}: </span>
                {m.text}
                {m.image_url ? (
                  <img src={m.image_url} alt="" className="mt-1 max-h-20 rounded" />
                ) : null}
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
