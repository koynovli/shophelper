import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { CheckCircle2, Loader2, LogOut, Package, User } from 'lucide-react';
import type { AxiosError } from 'axios';

import api from '../api';
import { useAuth } from '../auth/AuthContext';

type PlacementTaskRow = {
  id: number;
  product: { id: number; name: string; sku: string };
  equipment: { id: number; name: string };
  quantity: number;
  status: string;
  created_at: string;
};

function extractList<T>(data: unknown): T[] {
  if (Array.isArray(data)) {
    return data as T[];
  }
  if (data && typeof data === 'object' && 'results' in data) {
    const r = (data as { results?: T[] }).results;
    return Array.isArray(r) ? r : [];
  }
  return [];
}

export function EmployeeDashboard(): React.ReactElement {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<PlacementTaskRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [completingId, setCompletingId] = useState<number | null>(null);

  const loadPending = useCallback(async (): Promise<void> => {
    setError(null);
    try {
      const r = await api.get<unknown>('/placement-tasks/', {
        params: { status: 'PENDING' },
      });
      setTasks(extractList<PlacementTaskRow>(r.data));
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

  const handleLogout = (): void => {
    logout();
    navigate('/login', { replace: true });
  };

  const handleComplete = async (id: number): Promise<void> => {
    setCompletingId(id);
    setError(null);
    try {
      await api.patch(`/placement-tasks/${id}/`, { status: 'COMPLETED' });
      setTasks((prev) => prev.filter((t) => t.id !== id));
    } catch (err) {
      const ax = err as AxiosError<{ detail?: string }>;
      const detail = ax.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Не удалось отметить задачу выполненной.');
    } finally {
      setCompletingId(null);
    }
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
        <div className="mb-4 flex items-center gap-2 sm:mb-5">
          <Package className="h-6 w-6 text-emerald-400" aria-hidden />
          <div>
            <h1 className="text-lg font-semibold leading-tight sm:text-xl">Задачи на выкладку</h1>
            <p className="text-xs text-slate-400 sm:text-sm">Только активные (ожидают выполнения)</p>
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
            Нет задач в статусе «Ожидает». Когда администратор назначит выкладку, она появится здесь.
          </div>
        ) : (
          <ul className="flex flex-col gap-3 sm:gap-4">
            {tasks.map((t) => (
              <li key={t.id}>
                <article className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4 shadow-lg sm:p-5">
                  <h2 className="text-base font-semibold leading-snug text-slate-50 sm:text-lg">
                    {t.product.name} — {t.quantity} шт.
                  </h2>
                  <p className="mt-2 text-sm text-slate-300 sm:text-base">
                    Отнести в:{' '}
                    <span className="font-medium text-emerald-200/95">{t.equipment.name}</span>
                  </p>
                  <p className="mt-1 text-xs text-slate-500">SKU: {t.product.sku}</p>
                  <button
                    type="button"
                    disabled={completingId === t.id}
                    onClick={() => void handleComplete(t.id)}
                    className="mt-4 flex w-full min-h-[48px] items-center justify-center gap-2 rounded-xl border border-emerald-500/60 bg-emerald-600/90 px-4 py-3 text-base font-semibold text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-60 sm:min-h-[52px] sm:text-lg"
                  >
                    {completingId === t.id ? (
                      <>
                        <Loader2 className="h-5 w-5 animate-spin" aria-hidden />
                        Сохранение…
                      </>
                    ) : (
                      <>
                        <CheckCircle2 className="h-5 w-5 shrink-0" aria-hidden />
                        Выполнено
                      </>
                    )}
                  </button>
                </article>
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}
