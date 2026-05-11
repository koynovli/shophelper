import React from 'react';
import { useNavigate } from 'react-router-dom';
import { LogOut, User } from 'lucide-react';

import { useAuth } from '../auth/AuthContext';

export function EmployeeDashboard(): React.ReactElement {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = (): void => {
    logout();
    navigate('/login', { replace: true });
  };

  return (
    <div className="min-h-screen bg-slate-950 px-4 py-6 text-slate-100">
      <header className="mx-auto mb-6 flex w-full max-w-lg items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2 text-sm text-slate-300">
          <User className="h-4 w-4 shrink-0 text-slate-500" />
          <span className="truncate">
            <span className="text-slate-500">Вы вошли как </span>
            <span className="font-medium text-slate-100">{user?.username ?? '—'}</span>
          </span>
        </div>
        <button
          type="button"
          onClick={handleLogout}
          className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-xs font-medium text-slate-200 transition hover:border-rose-500/50 hover:bg-rose-950/30 hover:text-rose-100"
        >
          <LogOut className="h-3.5 w-3.5" />
          Выйти
        </button>
      </header>

      <div className="mx-auto w-full max-w-lg rounded-2xl border border-slate-800 bg-slate-900/60 p-6 shadow-2xl">
        <h1 className="text-xl font-semibold">Рабочий экран</h1>
        <p className="mt-2 text-sm text-slate-400">
          Заготовка для мобильного интерфейса сотрудника. После выхода можно снова войти на странице входа.
        </p>
      </div>
    </div>
  );
}

