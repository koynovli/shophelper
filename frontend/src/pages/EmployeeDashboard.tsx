import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, LogOut, Package, User } from 'lucide-react';
import type { AxiosError } from 'axios';

import api from '../api';
import type { TaskPoolItem } from '../api/taskPool';
import { poolStatusLabel, taskTypeLabel } from '../api/taskPool';
import { useAuth } from '../auth/AuthContext';
import { PlacementTaskWizard } from '../components/PlacementTaskWizard';
import { StaffTaskWizard } from '../components/StaffTaskWizard';
import { SupplyReceivingWizard } from '../components/SupplyReceivingWizard';
import { useStoreNotifications } from '../hooks/useStoreNotifications';
import { useTaskPoolWebSocket } from '../hooks/useTaskPoolWebSocket';

export function EmployeeDashboard(): React.ReactElement {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<TaskPoolItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const loadPending = useCallback(async (): Promise<void> => {
    setError(null);
    try {
      const r = await api.get<TaskPoolItem[]>('/task-pool/');
      const list = Array.isArray(r.data) ? r.data : [];
      setTasks(list);
      setSelectedTaskId((prev) => prev ?? list[0]?.id ?? null);
    } catch (err) {
      const ax = err as AxiosError<{ detail?: string }>;
      const detail = ax.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Не удалось загрузить задачи.');
      setTasks([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadPending();
  }, [loadPending]);

  useTaskPoolWebSocket(() => {
    void loadPending();
  });

  useStoreNotifications((ev) => {
    if (ev.event === 'placement_task.created') {
      const msg =
        typeof ev.data.message === 'string'
          ? ev.data.message
          : 'Новая задача на выкладку';
      setToast(msg);
      window.setTimeout(() => setToast(null), 6000);
      void loadPending();
    }
  });

  const handleLogout = (): void => {
    logout();
    navigate('/login', { replace: true });
  };

  return (
    <div className="min-h-screen bg-slate-950 px-3 py-4 text-slate-100 sm:px-4 sm:py-6">
      <header className="mx-auto mb-4 flex w-full max-w-xl items-center justify-between gap-3 sm:mb-6">
        <div className="flex min-w-0 items-center gap-2 text-sm text-slate-300">
          <User className="h-4 w-4 shrink-0 text-slate-500" aria-hidden />
          <span className="truncate">
            <span className="text-slate-500">Вы вошли как </span>
            <span className="font-medium text-slate-100">{user?.username ?? '—'}</span>
          </span>
        </div>
        <button
          type="button"
          onClick={handleLogout}
          className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-slate-600 bg-slate-900 px-3 py-2.5 text-xs font-medium text-slate-200 transition hover:border-rose-500/50 hover:bg-rose-950/30 hover:text-rose-100 min-h-[44px] sm:py-2"
        >
          <LogOut className="h-3.5 w-3.5" aria-hidden />
          Выйти
        </button>
      </header>

      <main className="mx-auto w-full max-w-xl">
        {toast ? (
          <div
            role="status"
            className="mb-3 rounded-xl border border-sky-500/40 bg-sky-950/50 px-4 py-3 text-sm text-sky-100"
          >
            {toast}
          </div>
        ) : null}
        <div className="mb-4 flex items-center gap-2 sm:mb-5">
          <Package className="h-6 w-6 text-emerald-400" aria-hidden />
          <div>
            <h1 className="text-lg font-semibold leading-tight sm:text-xl">Мои задачи</h1>
            <p className="text-xs text-slate-400 sm:text-sm">
              Выкладка, приёмка заказов и поручения менеджера
            </p>
          </div>
        </div>

        {error ? (
          <div
            role="alert"
            className="mb-4 rounded-xl border border-rose-500/40 bg-rose-950/30 px-4 py-3 text-sm text-rose-100"
          >
            {error}
          </div>
        ) : null}

        {loading ? (
          <div className="flex items-center justify-center gap-2 py-16 text-slate-400">
            <Loader2 className="h-8 w-8 animate-spin" aria-hidden />
            <span className="text-sm">Загрузка…</span>
          </div>
        ) : tasks.length === 0 ? (
          <div className="rounded-2xl border border-slate-800 bg-slate-900/50 px-4 py-12 text-center text-sm text-slate-400">
            Нет активных задач.
          </div>
        ) : (
          <ul className="flex flex-col gap-3 sm:gap-4">
            {tasks.map((t) => (
              <li key={`${t.task_type}-${t.id}`}>
                <article
                  onClick={() => setSelectedTaskId(t.id)}
                  className={`cursor-pointer rounded-2xl border bg-slate-900/70 p-4 shadow-lg transition sm:p-5 ${
                    selectedTaskId === t.id
                      ? 'border-emerald-500/70 ring-1 ring-emerald-400/50'
                      : 'border-slate-800 hover:border-slate-700'
                  }`}
                >
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <span
                      className={`rounded px-2 py-0.5 text-[10px] font-semibold uppercase ${
                        t.task_type === 'placement'
                          ? 'bg-emerald-900/50 text-emerald-200'
                          : t.task_type === 'receiving'
                            ? 'bg-sky-900/50 text-sky-200'
                            : 'bg-violet-900/50 text-violet-200'
                      }`}
                    >
                      {taskTypeLabel(t.task_type)}
                    </span>
                    <span className="text-xs text-slate-500">
                      {poolStatusLabel(t.status, t.task_type)}
                    </span>
                  </div>
                  <h2 className="text-base font-semibold leading-snug text-slate-50 sm:text-lg">
                    {t.title}
                  </h2>
                  {t.task_type === 'receiving' && t.planned_receiving_date ? (
                    <p className="mt-1 text-xs text-sky-300">
                      Плановая приёмка:{' '}
                      {new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium' }).format(
                        new Date(t.planned_receiving_date),
                      )}
                    </p>
                  ) : null}
                  {t.destination ? (
                    <p className="mt-2 text-sm text-slate-300">{t.destination}</p>
                  ) : null}
                  {selectedTaskId === t.id && t.task_type === 'placement' ? (
                    <PlacementTaskWizard task={t} onDone={() => void loadPending()} />
                  ) : null}
                  {selectedTaskId === t.id && t.task_type === 'staff' ? (
                    <StaffTaskWizard task={t} onDone={() => void loadPending()} />
                  ) : null}
                  {selectedTaskId === t.id && t.task_type === 'receiving' ? (
                    <SupplyReceivingWizard task={t} onDone={() => void loadPending()} />
                  ) : null}
                </article>
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}
