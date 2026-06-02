import React, { useRef, useState } from 'react';
import { CheckCircle2, ImagePlus, Loader2, Send } from 'lucide-react';
import type { AxiosError } from 'axios';

import api from '../api';
import type { TaskPoolItem } from '../api/taskPool';
import { useStaffTaskChat } from '../hooks/useStaffTaskChat';

type Props = {
  task: TaskPoolItem;
  onDone: () => void;
};

export function StaffTaskWizard({ task, onDone }: Props): React.ReactElement {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [localStatus, setLocalStatus] = useState(task.status);
  const [chatText, setChatText] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const chatEnabled = localStatus === 'CREATED' || localStatus === 'IN_PROGRESS';
  const { messages, sendMessage, connected, sending, error: chatError } = useStaffTaskChat(
    task.id,
    chatEnabled,
  );

  const handleError = (err: unknown, fallback: string): void => {
    const ax = err as AxiosError<{ detail?: string }>;
    const detail = ax.response?.data?.detail;
    setError(typeof detail === 'string' ? detail : fallback);
  };

  const accept = async (): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      await api.post(`/staff-tasks/${task.id}/accept/`);
      setLocalStatus('IN_PROGRESS');
    } catch (err) {
      handleError(err, 'Не удалось взять поручение.');
    } finally {
      setBusy(false);
    }
  };

  const complete = async (file?: File): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      if (file) {
        const form = new FormData();
        form.append('photo', file);
        await api.post(`/staff-tasks/${task.id}/complete/`, form, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
      } else {
        await api.post(`/staff-tasks/${task.id}/complete/`);
      }
      onDone();
    } catch (err) {
      handleError(err, 'Не удалось завершить поручение.');
    } finally {
      setBusy(false);
    }
  };

  const submitChat = async (image?: File): Promise<void> => {
    await sendMessage(chatText, image);
    setChatText('');
  };

  return (
    <div className="mt-4 space-y-3 border-t border-slate-800 pt-4">
      {task.description ? (
        <p className="text-sm text-slate-300">{task.description}</p>
      ) : null}
      {task.zone ? <p className="text-xs text-slate-500">Зона: {task.zone}</p> : null}

      {(error || chatError) && (
        <p className="rounded-lg border border-rose-500/40 bg-rose-950/30 px-3 py-2 text-sm text-rose-100">
          {error ?? chatError}
        </p>
      )}

      {localStatus === 'CREATED' ? (
        <button
          type="button"
          disabled={busy}
          onClick={() => void accept()}
          className="flex w-full min-h-[44px] items-center justify-center gap-2 rounded-xl bg-violet-600 px-4 py-3 text-sm font-semibold text-white disabled:opacity-60"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          Взять поручение
        </button>
      ) : null}

      {chatEnabled ? (
        <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
          <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">
            Чат {connected ? '(online)' : '(REST)'}
          </p>
          <ul className="mb-2 max-h-40 space-y-2 overflow-y-auto text-xs text-slate-300">
            {messages.length === 0 ? (
              <li className="text-slate-500">Сообщений пока нет</li>
            ) : (
              messages.map((m) => (
                <li key={m.id} className="rounded-lg bg-slate-900/80 px-2 py-1.5">
                  <span className="font-medium text-slate-200">{m.sender_username}:</span>{' '}
                  {m.text ? <span>{m.text}</span> : null}
                  {m.image_url ? (
                    <a href={m.image_url} target="_blank" rel="noreferrer" className="mt-1 block">
                      <img
                        src={m.image_url}
                        alt="Вложение"
                        className="max-h-32 rounded-md border border-slate-700 object-cover"
                      />
                    </a>
                  ) : null}
                </li>
              ))
            )}
          </ul>
          <div className="flex gap-2">
            <input
              value={chatText}
              onChange={(e) => setChatText(e.target.value)}
              placeholder="Сообщение…"
              className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm"
            />
            <button
              type="button"
              disabled={sending}
              onClick={() => fileInputRef.current?.click()}
              className="rounded-lg border border-slate-600 px-2 text-slate-200"
              title="Прикрепить изображение"
            >
              <ImagePlus className="h-4 w-4" aria-hidden />
            </button>
            <button
              type="button"
              disabled={sending || !chatText.trim()}
              onClick={() => void submitChat()}
              className="rounded-lg border border-slate-600 px-2 text-slate-200"
            >
              {sending ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              ) : (
                <Send className="h-4 w-4" aria-hidden />
              )}
            </button>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) {
                void submitChat(file);
                e.target.value = '';
              }
            }}
          />
        </div>
      ) : null}

      {localStatus === 'IN_PROGRESS' ? (
        task.requires_photo ? (
          <label className="flex w-full cursor-pointer flex-col items-center gap-2 rounded-xl border border-dashed border-violet-500/50 bg-violet-950/20 px-4 py-4 text-sm text-violet-100">
            <CheckCircle2 className="h-5 w-5" aria-hidden />
            Фотоотчёт и завершение
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
        ) : (
          <button
            type="button"
            disabled={busy}
            onClick={() => void complete()}
            className="flex w-full min-h-[44px] items-center justify-center gap-2 rounded-xl bg-violet-600 px-4 py-3 text-sm font-semibold text-white disabled:opacity-60"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Выполнено
          </button>
        )
      ) : null}
    </div>
  );
}
