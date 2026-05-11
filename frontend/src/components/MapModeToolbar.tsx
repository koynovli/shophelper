import React from 'react';
import { Layers, Pencil } from 'lucide-react';

import { useMapEditMode } from '../map/MapEditModeContext';

type Props = {
  className?: string;
};

export function MapModeToolbar({ className = '' }: Props): React.ReactElement {
  const { isEditMode, setEditMode } = useMapEditMode();

  return (
    <div
      className={`flex flex-col gap-3 rounded-xl border border-indigo-500/35 bg-slate-900/95 px-3 py-3 shadow-lg sm:flex-row sm:items-center sm:justify-between sm:px-4 ${className}`}
    >
      <div className="min-w-0">
        <p className="text-xs font-semibold uppercase tracking-wide text-indigo-300/95">
          Режим работы с картой
        </p>
        <p className="mt-0.5 text-sm text-slate-400">
          {isEditMode ? (
            <>
              <span className="font-medium text-slate-200">Конструктор</span> — перенос, поворот,
              создание и параметры оборудования
            </>
          ) : (
            <>
              <span className="font-medium text-slate-200">Мерчандайзинг</span> — план зафиксирован;
              двойной клик по объекту — планограмма и задачи
            </>
          )}
        </p>
      </div>

      <div
        className="flex shrink-0 rounded-xl border border-slate-600 bg-slate-950 p-1"
        role="group"
        aria-label="Переключение режима карты"
      >
        <button
          type="button"
          onClick={() => setEditMode(false)}
          className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition sm:px-4 ${
            !isEditMode
              ? 'bg-indigo-600 text-white shadow'
              : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
          }`}
        >
          <Layers className="h-4 w-4 shrink-0" aria-hidden />
          Мерчандайзинг
        </button>
        <button
          type="button"
          onClick={() => setEditMode(true)}
          className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition sm:px-4 ${
            isEditMode
              ? 'bg-emerald-600 text-white shadow'
              : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
          }`}
        >
          <Pencil className="h-4 w-4 shrink-0" aria-hidden />
          Конструктор
        </button>
      </div>
    </div>
  );
}
