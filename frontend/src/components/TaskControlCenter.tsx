import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ImagePlus, Loader2, Send } from 'lucide-react';
import type { AxiosError } from 'axios';

import api, { resolveMediaUrl } from '../api';
import type { TaskPoolItem } from '../api/taskPool';
import { poolStatusLabel, taskTypeLabel } from '../api/taskPool';
import { usePlacementTaskChat } from '../hooks/usePlacementTaskChat';
import { useStaffTaskChat } from '../hooks/useStaffTaskChat';
import { useStoreNotifications } from '../hooks/useStoreNotifications';
import { useTaskPoolWebSocket } from '../hooks/useTaskPoolWebSocket';

type EquipmentRow = { id: number; name: string };
type ZoneRow = { id: number; name: string };

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
  const [tasks, setTasks] = useState<TaskPoolItem[]>([]);
  const [equipment, setEquipment] = useState<EquipmentRow[]>([]);
  const [zones, setZones] = useState<ZoneRow[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [selectedStaffId, setSelectedStaffId] = useState<string | null>(null);
  const [selectedPlacementId, setSelectedPlacementId] = useState<string | null>(null);
  const [chatDraft, setChatDraft] = useState('');
  const [toast, setToast] = useState<string | null>(null);
  const chatFileRef = useRef<HTMLInputElement>(null);
  const placementChatFileRef = useRef<HTMLInputElement>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [newZoneId, setNewZoneId] = useState('');
  const [newRequiresPhoto, setNewRequiresPhoto] = useState(false);

  const chat = useStaffTaskChat(selectedStaffId, Boolean(selectedStaffId));
  const placementChat = usePlacementTaskChat({
    taskId: selectedPlacementId ?? '',
    enabled: Boolean(selectedPlacementId),
  });

  const selectedPlacementTask = tasks.find(
    (t) => t.task_type === 'placement' && t.id === selectedPlacementId,
  );

  const loadData = useCallback(async (): Promise<void> => {
    setError(null);
    try {
      const params: Record<string, string> = {};
      if (statusFilter !== 'ALL') {
        params.status = statusFilter;
      }
      if (typeFilter !== 'all') {
        params.task_type = typeFilter;
      }
      const [tasksRes, eqRes, zonesRes] = await Promise.all([
        api.get('/task-pool/', { params }),
        api.get('/floor-equipment/'),
        api.get('/zones/'),
      ]);
      setTasks(Array.isArray(tasksRes.data) ? tasksRes.data : []);
      setEquipment(extractList<EquipmentRow>(eqRes.data));
      setZones(extractList<ZoneRow>(zonesRes.data));
    } catch {
      setError('Не удалось загрузить центр управления задачами.');
      setTasks([]);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, typeFilter]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  useTaskPoolWebSocket(() => {
    void loadData();
  });

  useStoreNotifications((ev) => {
    if (ev.event === 'placement_task.created') {
      const msg =
        typeof ev.data.message === 'string'
          ? ev.data.message
          : 'Новая задача на выкладку';
      setToast(msg);
      window.setTimeout(() => setToast(null), 6000);
      void loadData();
    }
  });

  const patchPlacement = async (id: string, payload: Record<string, unknown>): Promise<void> => {
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

  const cancelStaff = async (id: string): Promise<void> => {
    try {
      setSavingId(id);
      await api.post(`/staff-tasks/${id}/cancel/`);
      await loadData();
    } catch (err) {
      const ax = err as AxiosError<{ detail?: string }>;
      const detail = ax.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Не удалось отменить поручение.');
    } finally {
      setSavingId(null);
    }
  };

  const cancelClearing = async (id: string): Promise<void> => {
    try {
      setSavingId(id);
      await api.delete(`/shelf-clearing-tasks/${id}/`);
      await loadData();
    } catch (err) {
      const ax = err as AxiosError<{ detail?: string }>;
      const detail = ax.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Не удалось отменить задание на уборку.');
    } finally {
      setSavingId(null);
    }
  };

  const cancelWriteOff = async (id: string): Promise<void> => {
    try {
      setSavingId(id);
      await api.delete(`/write-off-tasks/${id}/`);
      await loadData();
    } catch (err) {
      const ax = err as AxiosError<{ detail?: string }>;
      const detail = ax.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Не удалось отменить задание на списание.');
    } finally {
      setSavingId(null);
    }
  };

  const createStaffTask = async (): Promise<void> => {
    setError(null);
    try {
      await api.post('/staff-tasks/', {
        title: newTitle.trim(),
        description: newDescription.trim(),
        zone: newZoneId ? Number(newZoneId) : null,
        requires_photo: newRequiresPhoto,
      });
      setCreateOpen(false);
      setNewTitle('');
      setNewDescription('');
      setNewZoneId('');
      setNewRequiresPhoto(false);
      await loadData();
    } catch (err) {
      const ax = err as AxiosError<{ detail?: string }>;
      const detail = ax.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Не удалось создать поручение.');
    }
  };

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-white">Центр управления задачами</h3>
          <p className="text-sm text-slate-400">
            Общий пул: автоматическая выкладка и ручные поручения.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <select
            value={typeFilter}
            onChange={(event) => setTypeFilter(event.target.value)}
            className="rounded-md border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-slate-100"
          >
            <option value="all">Все типы</option>
            <option value="placement">Выкладка</option>
            <option value="shelf_clearing">Уборка</option>
            <option value="write_off">Списание</option>
            <option value="staff">Поручения</option>
          </select>
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            className="rounded-md border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-slate-100"
          >
            <option value="ALL">Все статусы</option>
            <option value="CREATED">Создана</option>
            <option value="FAILED">Проблема</option>
            <option value="IN_PROGRESS">Выполняется</option>
            <option value="COMPLETED">Завершено</option>
            <option value="CANCELLED">Отменено</option>
          </select>
          <button
            type="button"
            onClick={() => setCreateOpen((v) => !v)}
            className="rounded-md border border-violet-500/60 bg-violet-900/30 px-3 py-2 text-sm text-violet-100"
          >
            Создать поручение
          </button>
        </div>
      </div>

      {createOpen ? (
        <div className="mb-4 rounded-xl border border-slate-700 bg-slate-950/60 p-4">
          <h4 className="mb-3 text-sm font-medium text-white">Новое поручение</h4>
          <div className="grid gap-2 sm:grid-cols-2">
            <input
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="Заголовок"
              className="rounded border border-slate-600 bg-slate-900 px-3 py-2 text-sm"
            />
            <select
              value={newZoneId}
              onChange={(e) => setNewZoneId(e.target.value)}
              className="rounded border border-slate-600 bg-slate-900 px-3 py-2 text-sm"
            >
              <option value="">Без зоны</option>
              {zones.map((z) => (
                <option key={z.id} value={z.id}>
                  {z.name}
                </option>
              ))}
            </select>
          </div>
          <textarea
            value={newDescription}
            onChange={(e) => setNewDescription(e.target.value)}
            placeholder="Описание"
            rows={2}
            className="mt-2 w-full rounded border border-slate-600 bg-slate-900 px-3 py-2 text-sm"
          />
          <label className="mt-2 flex items-center gap-2 text-sm text-slate-300">
            <input
              type="checkbox"
              checked={newRequiresPhoto}
              onChange={(e) => setNewRequiresPhoto(e.target.checked)}
            />
            Требуется фотоотчёт
          </label>
          <button
            type="button"
            onClick={() => void createStaffTask()}
            className="mt-3 rounded bg-violet-600 px-4 py-2 text-sm font-medium text-white"
          >
            Сохранить
          </button>
        </div>
      ) : null}

      {toast ? (
        <p
          role="status"
          className="mb-3 rounded-md border border-sky-500/50 bg-sky-950/40 px-3 py-2 text-sm text-sky-100"
        >
          {toast}
        </p>
      ) : null}

      {error ? (
        <p className="mb-3 rounded-md border border-rose-600/60 bg-rose-900/25 px-3 py-2 text-sm text-rose-100">
          {error}
        </p>
      ) : null}

      {loading ? (
        <p className="text-sm text-slate-400">Загрузка...</p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="overflow-x-auto lg:col-span-2">
            <table className="min-w-full text-sm">
              <thead className="text-left text-slate-400">
                <tr>
                  <th className="px-2 py-2">Тип</th>
                  <th className="px-2 py-2">Статус</th>
                  <th className="px-2 py-2">Задача</th>
                  <th className="px-2 py-2">Создана</th>
                  <th className="px-2 py-2">Действия</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((task) => (
                  <tr key={`${task.task_type}-${task.id}`} className="border-t border-slate-800">
                    <td className="px-2 py-2 text-slate-300">{taskTypeLabel(task.task_type)}</td>
                    <td className="px-2 py-2 text-slate-200">
                      {poolStatusLabel(task.status, task.task_type)}
                    </td>
                    <td className="px-2 py-2 text-slate-200">
                      <div>{task.title}</div>
                      {task.destination ? (
                        <div className="text-xs text-slate-500">{task.destination}</div>
                      ) : null}
                      {task.zone ? (
                        <div className="text-xs text-slate-500">Зона: {task.zone}</div>
                      ) : null}
                    </td>
                    <td className="px-2 py-2 text-slate-400">
                      {new Date(task.created_at).toLocaleString('ru-RU')}
                    </td>
                    <td className="px-2 py-2">
                      {task.task_type === 'placement' ? (
                        <div className="flex flex-wrap items-center gap-2">
                          <button
                            type="button"
                            onClick={() => {
                              setSelectedPlacementId(task.id);
                              setSelectedStaffId(null);
                            }}
                            className="rounded border border-sky-500/60 px-2 py-1 text-xs text-sky-100"
                          >
                            Чат
                          </button>
                          {task.status === 'FAILED' && task.photo_url ? (() => {
                            const photoHref = resolveMediaUrl(task.photo_url);
                            return photoHref ? (
                              <a
                                href={photoHref}
                                target="_blank"
                                rel="noreferrer"
                                className="text-xs text-amber-200 underline"
                              >
                                Фото
                              </a>
                            ) : null;
                          })() : null}
                          <button
                            type="button"
                            disabled={
                              savingId === task.id ||
                              task.status === 'CANCELLED' ||
                              task.status === 'COMPLETED'
                            }
                            onClick={() => void patchPlacement(task.id, { status: 'CANCELLED' })}
                            className="rounded border border-rose-500/70 bg-rose-900/25 px-2 py-1 text-xs text-rose-100 disabled:opacity-50"
                          >
                            Отменить
                          </button>
                          {task.equipment ? (
                            <select
                              disabled={
                                savingId === task.id ||
                                task.status === 'COMPLETED' ||
                                task.status === 'CANCELLED'
                              }
                              value={task.equipment.id}
                              onChange={(event) =>
                                void patchPlacement(task.id, {
                                  equipment: Number(event.target.value),
                                })
                              }
                              className="rounded border border-slate-600 bg-slate-950 px-2 py-1 text-xs text-slate-100"
                            >
                              {equipment.map((eq) => (
                                <option key={eq.id} value={eq.id}>
                                  {eq.name}
                                </option>
                              ))}
                            </select>
                          ) : null}
                        </div>
                      ) : task.task_type === 'shelf_clearing' ? (
                        <button
                          type="button"
                          disabled={
                            savingId === task.id ||
                            task.status === 'CANCELLED' ||
                            task.status === 'COMPLETED'
                          }
                          onClick={() => void cancelClearing(task.id)}
                          className="rounded border border-rose-500/70 bg-rose-900/25 px-2 py-1 text-xs text-rose-100 disabled:opacity-50"
                        >
                          Отменить
                        </button>
                      ) : task.task_type === 'write_off' ? (
                        <button
                          type="button"
                          disabled={
                            savingId === task.id ||
                            task.status === 'CANCELLED' ||
                            task.status === 'COMPLETED'
                          }
                          onClick={() => void cancelWriteOff(task.id)}
                          className="rounded border border-rose-500/70 bg-rose-900/25 px-2 py-1 text-xs text-rose-100 disabled:opacity-50"
                        >
                          Отменить
                        </button>
                      ) : task.task_type === 'staff' ? (
                        <div className="flex flex-wrap gap-2">
                          <button
                            type="button"
                            onClick={() => {
                              setSelectedStaffId(task.id);
                              setSelectedPlacementId(null);
                            }}
                            className="rounded border border-sky-500/60 px-2 py-1 text-xs text-sky-100"
                          >
                            Чат
                          </button>
                          <button
                            type="button"
                            disabled={
                              savingId === task.id ||
                              task.status === 'COMPLETED' ||
                              task.status === 'CANCELLED'
                            }
                            onClick={() => void cancelStaff(task.id)}
                            className="rounded border border-rose-500/70 bg-rose-900/25 px-2 py-1 text-xs text-rose-100 disabled:opacity-50"
                          >
                            Отменить
                          </button>
                        </div>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="space-y-3">
          <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
            <h4 className="mb-2 text-sm font-medium text-white">Чат выкладки</h4>
            {!selectedPlacementId ? (
              <p className="text-xs text-slate-500">
                Выберите задачу выкладки и нажмите «Чат» (проблема на складе).
              </p>
            ) : (
              <>
                {selectedPlacementTask ? (
                  <p className="mb-2 text-xs text-slate-400">{selectedPlacementTask.title}</p>
                ) : null}
                {placementChat.error ? (
                  <p className="mb-2 text-xs text-rose-300">{placementChat.error}</p>
                ) : null}
                <ul className="mb-2 max-h-40 space-y-2 overflow-y-auto text-xs text-slate-300">
                  {placementChat.messages.length === 0 ? (
                    <li className="text-slate-500">Сообщений пока нет</li>
                  ) : (
                    placementChat.messages.map((m) => (
                      <li key={m.id} className="rounded bg-slate-900/80 px-2 py-1">
                        <span className="font-medium">{m.sender_username ?? '—'}:</span>{' '}
                        {m.text}
                        {m.image_url ? (
                          <a
                            href={m.image_url}
                            target="_blank"
                            rel="noreferrer"
                            className="mt-1 block"
                          >
                            <img
                              src={m.image_url}
                              alt="Вложение"
                              className="max-h-28 rounded border border-slate-700 object-cover"
                            />
                          </a>
                        ) : null}
                      </li>
                    ))
                  )}
                </ul>
                <div className="flex gap-2">
                  <input
                    value={chatDraft}
                    onChange={(e) => setChatDraft(e.target.value)}
                    className="min-w-0 flex-1 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm"
                    placeholder="Написать…"
                  />
                  <button
                    type="button"
                    onClick={() => placementChatFileRef.current?.click()}
                    className="rounded border border-slate-600 px-2 text-slate-200"
                    title="Изображение"
                  >
                    <ImagePlus className="h-4 w-4" aria-hidden />
                  </button>
                  <button
                    type="button"
                    disabled={!chatDraft.trim()}
                    onClick={() => {
                      void placementChat.send(chatDraft).then(() => setChatDraft(''));
                    }}
                    className="rounded border border-slate-600 px-2 text-slate-200"
                  >
                    <Send className="h-4 w-4" aria-hidden />
                  </button>
                </div>
                <input
                  ref={placementChatFileRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) {
                      void placementChat.send(chatDraft, file).then(() => setChatDraft(''));
                      e.target.value = '';
                    }
                  }}
                />
              </>
            )}
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
            <h4 className="mb-2 text-sm font-medium text-white">Чат поручения</h4>
            {!selectedStaffId ? (
              <p className="text-xs text-slate-500">Выберите поручение и нажмите «Чат».</p>
            ) : (
              <>
                {chat.error ? (
                  <p className="mb-2 text-xs text-rose-300">{chat.error}</p>
                ) : null}
                <ul className="mb-2 max-h-48 space-y-2 overflow-y-auto text-xs text-slate-300">
                  {chat.messages.length === 0 ? (
                    <li className="text-slate-500">Сообщений пока нет</li>
                  ) : (
                    chat.messages.map((m) => (
                      <li key={m.id} className="rounded bg-slate-900/80 px-2 py-1">
                        <span className="font-medium">{m.sender_username}:</span>{' '}
                        {m.text ? <span>{m.text}</span> : null}
                        {m.image_url ? (
                          <a href={m.image_url} target="_blank" rel="noreferrer" className="mt-1 block">
                            <img
                              src={m.image_url}
                              alt="Вложение"
                              className="max-h-28 rounded border border-slate-700 object-cover"
                            />
                          </a>
                        ) : null}
                      </li>
                    ))
                  )}
                </ul>
                <div className="flex gap-2">
                  <input
                    value={chatDraft}
                    onChange={(e) => setChatDraft(e.target.value)}
                    className="min-w-0 flex-1 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm"
                    placeholder="Написать…"
                  />
                  <button
                    type="button"
                    disabled={chat.sending}
                    onClick={() => chatFileRef.current?.click()}
                    className="rounded border border-slate-600 px-2 text-slate-200"
                    title="Прикрепить изображение"
                  >
                    <ImagePlus className="h-4 w-4" aria-hidden />
                  </button>
                  <button
                    type="button"
                    disabled={chat.sending || !chatDraft.trim()}
                    onClick={() => {
                      void chat.sendMessage(chatDraft).then(() => setChatDraft(''));
                    }}
                    className="rounded border border-slate-600 px-2 text-slate-200"
                  >
                    {chat.sending ? (
                      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                    ) : (
                      <Send className="h-4 w-4" aria-hidden />
                    )}
                  </button>
                </div>
                <input
                  ref={chatFileRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) {
                      void chat.sendMessage(chatDraft, file).then(() => setChatDraft(''));
                      e.target.value = '';
                    }
                  }}
                />
              </>
            )}
          </div>
          </div>
        </div>
      )}
    </div>
  );
}
