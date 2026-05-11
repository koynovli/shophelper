import React from 'react';
import { Link } from 'react-router-dom';

export function NoAccess(): React.ReactElement {
  return (
    <div className="min-h-screen bg-slate-950 px-4 py-10 text-slate-100">
      <div className="mx-auto w-full max-w-lg rounded-2xl border border-slate-800 bg-slate-900/60 p-6 shadow-2xl">
        <h1 className="text-xl font-semibold">Нет доступа</h1>
        <p className="mt-2 text-sm text-slate-400">
          У вашей роли нет прав на просмотр этой страницы.
        </p>
        <div className="mt-6 flex items-center gap-3">
          <Link
            to="/"
            className="rounded-md border border-slate-700 bg-slate-950 px-4 py-2 text-sm text-slate-200 transition hover:border-slate-600"
          >
            На главную
          </Link>
          <Link
            to="/login"
            className="rounded-md border border-emerald-500/70 bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-emerald-500"
          >
            Войти другим пользователем
          </Link>
        </div>
      </div>
    </div>
  );
}

