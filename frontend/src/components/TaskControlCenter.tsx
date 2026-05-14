import React, { useEffect, useState } from 'react';
import type { AxiosError } from 'axios';

import api from '../api';

type TaskRow = {
  id: number;
  status: 'PENDING' | 'IN_PROGRESS' | 'COMPLETED' | 'CANCELLED' | string;
  quantity: number;
  created_at: string;
  product: { id: number; name: string; sku: string };
  equipment: { id: number; name: string };
  destination_text: string;
};

type EquipmentRow = { id: number; name: string };

const STATUS_LABELS: Record<string, string> = {
  PENDING: 'Ожидает',
  IN_PROGRESS: 'Выполняется',
  COMPLETED: 'Завершено',
  CANCELLED: 'Отменено',
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

export function TaskControlCenter(): React.ReactElement {
  const [tasks, setTasks] = useState<TaskRow[]>([]);
  const [equipment, setEquipment] = useState<EquipmentRow[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<number | null>(null);

  const loadData = async (): Promise<void> => {
    setError(null);
    try {
      const [tasksRes, eqRes] = await Promise.all([api.get('/placement-tasks/'), api.get('/floor-equipment/')]);
      setTasks(extractList<TaskRow>(tasksRes.data));
      setEquipment(extractList<EquipmentRow>(eqRes.data));
    } catch {
      setError('Не удалось загрузить центр управления задачами.');
      setTasks([]);
      setEquipment([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  const patchTask = async (id: number, payload: Record<string, unknown>): Promise<void> => {
    try {
      setSavingId(id);
      await api.patch(`/placement-tasks/${id}/`, payload);
      await loadData();
    } catch (err) {
      const ax = err as AxiosError<{ detail?: string }>;
      const detail = ax.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Не удалось обновить задачу.');
    } finally {
      setSavingId(null);
    }
  };

  const filtered = statusFilter === 'ALL' ? tasks : tasks.filter((task) => task.status === statusFilter);

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-white">Центр управления задачами</h3>
          <p className="text-sm text-slate-400">Мониторинг, отмена и переназначение задач выкладки.</p>
        </div>
        <select
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value)}
          className="rounded-md border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-slate-100"
        >
          <option value="ALL">Все статусы</option>
          <option value="PENDING">Ожидает</option>
          <option value="IN_PROGRESS">Выполняется</option>
          <option value="COMPLETED">Завершено</option>
          <option value="CANCELLED">Отменено</option>
        </select>
      </div>
      {error ? <p className="mb-3 rounded-md border border-rose-600/60 bg-rose-900/25 px-3 py-2 text-sm text-rose-100">{error}</p> : null}
      {loading ? (
        <p className="text-sm text-slate-400">Загрузка...</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="text-left text-slate-400">
              <tr>
                <th className="px-2 py-2">Статус</th>
                <th className="px-2 py-2">Товар</th>
                <th className="px-2 py-2">Кол-во</th>
                <th className="px-2 py-2">Место назначения</th>
                <th className="px-2 py-2">Создана</th>
                <th className="px-2 py-2">Действия</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((task) => (
                <tr key={task.id} className="border-t border-slate-800">
                  <td className="px-2 py-2 text-slate-200">{STATUS_LABELS[task.status] ?? task.status}</td>
                  <td className="px-2 py-2 text-slate-200">{task.product.name}</td>
                  <td className="px-2 py-2 text-slate-200">{task.quantity}</td>
                  <td className="px-2 py-2 text-slate-300">{task.destination_text}</td>
                  <td className="px-2 py-2 text-slate-400">
                    {new Date(task.created_at).toLocaleString('ru-RU')}
                  </td>
                  <td className="px-2 py-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        disabled={savingId === task.id || task.status === 'CANCELLED'}
                        onClick={() => void patchTask(task.id, { status: 'CANCELLED' })}
                        className="rounded border border-rose-500/70 bg-rose-900/25 px-2 py-1 text-xs text-rose-100 disabled:opacity-50"
                      >
                        Отменить
                      </button>
                      <select
                        disabled={savingId === task.id}
                        value={task.equipment.id}
                        onChange={(event) => void patchTask(task.id, { equipment: Number(event.target.value) })}
                        className="rounded border border-slate-600 bg-slate-950 px-2 py-1 text-xs text-slate-100"
                      >
                        {equipment.map((eq) => (
                          <option key={eq.id} value={eq.id}>
                            {eq.name}
                          </option>
                        ))}
                      </select>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
