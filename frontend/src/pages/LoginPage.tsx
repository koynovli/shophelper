import React, { useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Lock, User } from 'lucide-react';
import { isAxiosError } from 'axios';

import { useAuth } from '../auth/AuthContext';

export function LoginPage(): React.ReactElement {
  const { isAuthenticated, user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (isAuthenticated && user) {
    const to = user.role === 'admin' ? '/admin' : '/employee';
    return <Navigate to={to} replace />;
  }

  const onSubmit = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(username.trim(), password);
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from || '/', { replace: true });
    } catch (err) {
      if (isAxiosError(err)) {
        const status = err.response?.status;
        const detail = (err.response?.data as { detail?: string } | undefined)?.detail;
        if (status === 401 || status === 400) {
          setError(typeof detail === 'string' ? detail : 'Неверный логин или пароль.');
        } else if (!err.response) {
          setError('Сервер недоступен. Проверьте, что Django запущен на http://127.0.0.1:8000');
        } else {
          setError(detail || `Ошибка входа (${status ?? '?'})`);
        }
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Не удалось войти. Попробуйте ещё раз.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 px-4 py-10 text-slate-100">
      <div className="mx-auto w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900/60 p-6 shadow-2xl">
        <h1 className="mb-1 text-xl font-semibold">Вход</h1>
        <p className="mb-6 text-sm text-slate-400">ShopHelper</p>

        <form onSubmit={onSubmit} className="space-y-4">
          <label className="block text-sm text-slate-300">
            Логин
            <div className="mt-1 flex items-center gap-2 rounded-md border border-slate-700 bg-slate-950 px-3 py-2">
              <User className="h-4 w-4 text-slate-500" />
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full bg-transparent text-slate-100 outline-none"
                autoComplete="username"
              />
            </div>
          </label>

          <label className="block text-sm text-slate-300">
            Пароль
            <div className="mt-1 flex items-center gap-2 rounded-md border border-slate-700 bg-slate-950 px-3 py-2">
              <Lock className="h-4 w-4 text-slate-500" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full bg-transparent text-slate-100 outline-none"
                autoComplete="current-password"
              />
            </div>
          </label>

          {error ? (
            <div className="rounded-md border border-rose-700/60 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">
              {error}
            </div>
          ) : null}

          <button
            type="submit"
            disabled={loading || !username.trim() || !password}
            className="w-full rounded-md border border-emerald-500/70 bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading ? 'Входим...' : 'Войти'}
          </button>
        </form>
      </div>
    </div>
  );
}

