import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { AxiosError } from 'axios';
import { Download, Loader2, MapPinned, Search, Trash2, X } from 'lucide-react';

import api from '../api';

type CategoryOpt = { id: number; name: string };

type TrackingRow = {
  id: number;
  name: string;
  category: { id: number; name: string } | null;
  total_quantity: number;
  warehouse_qty: number;
  hall_qty: number;
  pending_qty: number;
  planogram_target_sum: number;
  status: 'OK' | 'LOW_STOCK' | 'EXPIRING' | 'EXPIRED' | string;
  under_floor_target: boolean;
};

type BatchDetail =
  | {
      kind: 'batch';
      id: number;
      expiration_date: string;
      current_quantity: number;
      initial_quantity: number;
      is_active: boolean;
      days_to_expiry: number;
    }
  | {
      kind: 'marked_group';
      expiration_date: string;
      unit_count: number;
      days_to_expiry: number;
      serials: string[];
      serials_more?: number;
    };

function isRegularBatch(b: BatchDetail): b is Extract<BatchDetail, { kind: 'batch' }> {
  return b.kind === 'batch' || ('id' in b && b.kind !== 'marked_group');
}

function isMarkedGroup(b: BatchDetail): b is Extract<BatchDetail, { kind: 'marked_group' }> {
  return b.kind === 'marked_group';
}

type LocationDetail = {
  kind: string;
  planogram_id: number | null;
  equipment_id: number;
  equipment_name: string;
  slot_row: number;
  slot_col: number;
  label: string;
  target_quantity: number | null;
  quantity: number | null;
};

type ProductDetail = {
  id: number;
  name: string;
  sku: string;
  category: { id: number; name: string } | null;
  total_quantity: number;
  warehouse_qty: number;
  hall_qty: number;
  pending_qty: number;
  planogram_target_sum: number;
  status: string;
  batches: BatchDetail[];
  locations: LocationDetail[];
  map_equipment_ids: number[];
};

type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

function extractPaginated<T>(data: unknown): { rows: T[]; count: number } {
  if (data && typeof data === 'object' && 'results' in data) {
    const p = data as Paginated<T>;
    return { rows: Array.isArray(p.results) ? p.results : [], count: typeof p.count === 'number' ? p.count : 0 };
  }
  if (Array.isArray(data)) {
    return { rows: data as T[], count: (data as T[]).length };
  }
  return { rows: [], count: 0 };
}

const STATUS_UI: Record<string, { label: string; className: string }> = {
  OK: { label: 'Норма', className: 'border-slate-600 bg-slate-800 text-slate-200' },
  LOW_STOCK: { label: 'Дефицит', className: 'border-rose-500/60 bg-rose-950/40 text-rose-100' },
  EXPIRING: { label: 'Срок годности', className: 'border-amber-500/60 bg-amber-950/40 text-amber-100' },
  EXPIRED: { label: 'Просрочено', className: 'border-red-600/70 bg-red-950/50 text-red-100' },
};

export function InventoryDashboard(): React.ReactElement {
  const navigate = useNavigate();
  const [rows, setRows] = useState<TrackingRow[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [searchDebounced, setSearchDebounced] = useState('');
  const [categoryId, setCategoryId] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [categories, setCategories] = useState<CategoryOpt[]>([]);
  const [detail, setDetail] = useState<ProductDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [writeOffBusy, setWriteOffBusy] = useState(false);
  const [writeOffMsg, setWriteOffMsg] = useState<string | null>(null);
  const [manualBatchId, setManualBatchId] = useState<string>('');
  const [manualQty, setManualQty] = useState<string>('1');
  const [manualReason, setManualReason] = useState('');
  const [manualBusy, setManualBusy] = useState(false);
  const [manualMsg, setManualMsg] = useState<string | null>(null);
  const [expandedMarked, setExpandedMarked] = useState<Set<string>>(new Set());

  useEffect(() => {
    const t = window.setTimeout(() => setSearchDebounced(search.trim()), 350);
    return () => window.clearTimeout(t);
  }, [search]);

  const loadCategories = useCallback(async (): Promise<void> => {
    try {
      const r = await api.get<CategoryOpt[]>('/product-tracking/categories/');
      setCategories(Array.isArray(r.data) ? r.data : []);
    } catch {
      setCategories([]);
    }
  }, []);

  const loadRows = useCallback(async (): Promise<void> => {
    setError(null);
    setLoading(true);
    try {
      const params: Record<string, string | number> = { page, page_size: pageSize };
      if (searchDebounced) {
        params.search = searchDebounced;
      }
      if (categoryId) {
        params.category = categoryId;
      }
      if (statusFilter === 'deficit') {
        params.status = 'LOW_STOCK';
      } else if (statusFilter === 'normal') {
        params.status = 'OK';
      } else if (statusFilter === 'expiring') {
        params.status = 'EXPIRING';
      } else if (statusFilter === 'expired') {
        params.status = 'EXPIRED';
      }
      const r = await api.get<unknown>('/product-tracking/', { params });
      const { rows: list, count: c } = extractPaginated<TrackingRow>(r.data);
      setRows(list);
      setCount(c);
    } catch (err) {
      const ax = err as AxiosError<{ detail?: string }>;
      const d = ax.response?.data?.detail;
      setError(typeof d === 'string' ? d : 'Не удалось загрузить учёт товаров.');
      setRows([]);
      setCount(0);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, searchDebounced, categoryId, statusFilter]);

  useEffect(() => {
    void loadCategories();
  }, [loadCategories]);

  useEffect(() => {
    void loadRows();
  }, [loadRows]);

  const totalPages = useMemo(() => Math.max(1, Math.ceil(count / pageSize)), [count, pageSize]);

  const openDetail = async (id: number, expandMarked = false): Promise<void> => {
    setDetailLoading(true);
    setDetailError(null);
    try {
      const r = await api.get<ProductDetail>(`/product-tracking/${id}/`, {
        params: expandMarked ? { expand: '1' } : {},
      });
      setDetail(r.data);
    } catch (err) {
      const ax = err as AxiosError<{ detail?: string }>;
      const d = ax.response?.data?.detail;
      setDetailError(typeof d === 'string' ? d : 'Не удалось загрузить карточку товара.');
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const closeDetail = (): void => {
    setDetail(null);
    setDetailError(null);
    setExpandedMarked(new Set());
  };

  const expandMarkedGroup = async (productId: number, expirationDate: string): Promise<void> => {
    setExpandedMarked((prev) => new Set(prev).add(expirationDate));
    await openDetail(productId, true);
  };

  const exportCsv = async (): Promise<void> => {
    try {
      const params: Record<string, string> = { format: 'csv' };
      if (searchDebounced) {
        params.search = searchDebounced;
      }
      if (categoryId) {
        params.category = categoryId;
      }
      if (statusFilter === 'deficit') {
        params.status = 'LOW_STOCK';
      } else if (statusFilter === 'normal') {
        params.status = 'OK';
      } else if (statusFilter === 'expiring') {
        params.status = 'EXPIRING';
      } else if (statusFilter === 'expired') {
        params.status = 'EXPIRED';
      }
      const r = await api.get<Blob>('/product-tracking/', {
        params,
        responseType: 'blob',
      });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'product_tracking.csv';
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setError('Не удалось выгрузить CSV.');
    }
  };

  const goToMap = (equipmentId: number): void => {
    navigate(`/admin?tab=map&equipmentId=${equipmentId}`);
  };

  const runScanWriteOffTasks = async (dryRun: boolean): Promise<void> => {
    setWriteOffBusy(true);
    setWriteOffMsg(null);
    setError(null);
    try {
      const r = await api.post<{
        dry_run: boolean;
        tasks_total: number;
        warehouse_tasks: number;
        shelf_tasks: number;
      }>('/inventory/scan-write-off-tasks/', null, {
        params: dryRun ? { dry_run: 'true' } : {},
      });
      const prefix = r.data.dry_run ? '[Пробный прогон] ' : '';
      if (r.data.dry_run) {
        setWriteOffMsg(
          `${prefix}Будет создано ${r.data.tasks_total} заданий: ${r.data.warehouse_tasks} со склада, ${r.data.shelf_tasks} с полок`,
        );
      } else {
        setWriteOffMsg(`Создано ${r.data.tasks_total} заданий на списание`);
        void loadRows();
      }
    } catch (err) {
      const ax = err as AxiosError<{ detail?: string }>;
      const d = ax.response?.data?.detail;
      setError(typeof d === 'string' ? d : 'Не удалось выполнить сканирование.');
    } finally {
      setWriteOffBusy(false);
    }
  };

  const submitManualWriteOff = async (): Promise<void> => {
    if (!detail) {
      return;
    }
    const batchId = Number(manualBatchId);
    const qty = Number(manualQty);
    if (!batchId || qty < 1) {
      setManualMsg('Выберите партию и укажите количество.');
      return;
    }
    setManualBusy(true);
    setManualMsg(null);
    try {
      await api.post('/write-off-tasks/', {
        batch_id: batchId,
        quantity: qty,
        reason: manualReason.trim(),
      });
      setManualMsg('Задание на списание создано. Сотрудник утилизирует товар и подтвердит в приложении.');
      setManualBatchId('');
      setManualQty('1');
      setManualReason('');
      void loadRows();
    } catch (err) {
      const ax = err as AxiosError<{ detail?: string }>;
      const d = ax.response?.data?.detail;
      setManualMsg(typeof d === 'string' ? d : 'Не удалось создать задание.');
    } finally {
      setManualBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-white">Учёт товаров</h2>
          <p className="text-sm text-slate-400">
            Сводка по партиям, складу (StockItem), залу (остатки на полке) и активным задачам выкладки.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={writeOffBusy}
            onClick={() => void runScanWriteOffTasks(true)}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-200 hover:border-amber-500/50 disabled:opacity-50"
          >
            {writeOffBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Проверить просрочку
          </button>
          <button
            type="button"
            disabled={writeOffBusy}
            onClick={() => void runScanWriteOffTasks(false)}
            className="inline-flex items-center gap-2 rounded-lg border border-rose-500/60 bg-rose-950/40 px-3 py-2 text-sm text-rose-100 hover:bg-rose-900/50 disabled:opacity-50"
          >
            <Trash2 className="h-4 w-4" />
            Создать задания на списание
          </button>
          <button
            type="button"
            onClick={() => void exportCsv()}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-200 hover:border-emerald-500/50"
          >
            <Download className="h-4 w-4" />
            Экспорт CSV
          </button>
        </div>
      </div>

      {writeOffMsg ? (
        <div className="rounded-lg border border-sky-500/40 bg-sky-950/30 px-3 py-2 text-sm text-sky-100">
          {writeOffMsg}
        </div>
      ) : null}

      {error ? (
        <div className="rounded-lg border border-rose-500/40 bg-rose-950/30 px-3 py-2 text-sm text-rose-100">{error}</div>
      ) : null}

      <div className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-800 bg-slate-900/60 p-4">
        <label className="min-w-[12rem] flex-1 text-sm text-slate-300">
          Поиск по названию
          <span className="mt-1 flex items-center gap-2 rounded-md border border-slate-600 bg-slate-950 px-2">
            <Search className="h-4 w-4 text-slate-500" />
            <input
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              className="w-full bg-transparent py-2 text-slate-100 outline-none"
              placeholder="Например, Молоко"
            />
          </span>
        </label>
        <label className="text-sm text-slate-300">
          Категория
          <select
            value={categoryId}
            onChange={(e) => {
              setCategoryId(e.target.value);
              setPage(1);
            }}
            className="mt-1 block w-48 rounded-md border border-slate-600 bg-slate-950 px-3 py-2 text-slate-100"
          >
            <option value="">Все</option>
            {categories.map((c) => (
              <option key={c.id} value={String(c.id)}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm text-slate-300">
          Статус
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
            className="mt-1 block w-44 rounded-md border border-slate-600 bg-slate-950 px-3 py-2 text-slate-100"
          >
            <option value="">Все</option>
            <option value="normal">Норма</option>
            <option value="deficit">Дефицит</option>
            <option value="expiring">Срок годности</option>
            <option value="expired">Просрочено</option>
          </select>
        </label>
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/40">
        {loading ? (
          <div className="flex items-center justify-center gap-2 py-16 text-slate-400">
            <Loader2 className="h-6 w-6 animate-spin" />
            Загрузка…
          </div>
        ) : (
          <table className="min-w-full text-sm">
            <thead className="border-b border-slate-800 text-left text-slate-400">
              <tr>
                <th className="px-3 py-2">Название</th>
                <th className="px-3 py-2">Категория</th>
                <th className="px-3 py-2">Общий остаток</th>
                <th className="px-3 py-2">Склад</th>
                <th className="px-3 py-2">Зал</th>
                <th className="px-3 py-2">В пути</th>
                <th className="px-3 py-2">Цель (план.)</th>
                <th className="px-3 py-2">Статус</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const deficitRow = row.under_floor_target;
                const expired = row.status === 'EXPIRED';
                const expiring = row.status === 'EXPIRING';
                const rowClass = expired
                  ? 'bg-red-950/30 border-l-4 border-l-red-600'
                  : deficitRow
                    ? 'bg-rose-950/35 border-l-4 border-l-rose-500'
                    : expiring
                      ? 'bg-amber-950/25 border-l-4 border-l-amber-500'
                      : '';
                const st = STATUS_UI[row.status] ?? STATUS_UI.OK;
                return (
                  <tr
                    key={row.id}
                    className={`cursor-pointer border-t border-slate-800 hover:bg-slate-800/50 ${rowClass}`}
                    onClick={() => void openDetail(row.id)}
                  >
                    <td className="px-3 py-2 font-medium text-slate-100">{row.name}</td>
                    <td className="px-3 py-2 text-slate-300">{row.category?.name ?? '—'}</td>
                    <td className="px-3 py-2 text-slate-200">{row.total_quantity}</td>
                    <td className="px-3 py-2 text-slate-200">{row.warehouse_qty}</td>
                    <td className="px-3 py-2 text-slate-200">{row.hall_qty}</td>
                    <td className="px-3 py-2 text-slate-200">{row.pending_qty}</td>
                    <td className="px-3 py-2 text-slate-400">{row.planogram_target_sum}</td>
                    <td className="px-3 py-2">
                      <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs ${st.className}`}>
                        {st.label}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {!loading && count > pageSize ? (
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-slate-400">
          <span>
            Стр. {page} из {totalPages} ({count} записей)
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="rounded-md border border-slate-600 px-3 py-1 disabled:opacity-40"
            >
              Назад
            </button>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
              className="rounded-md border border-slate-600 px-3 py-1 disabled:opacity-40"
            >
              Вперёд
            </button>
          </div>
        </div>
      ) : null}

      {detail !== null || detailLoading || detailError ? (
        <div
          className="fixed inset-0 z-[60] flex justify-end bg-slate-950/70 backdrop-blur-sm"
          role="presentation"
          onClick={closeDetail}
        >
          <aside
            className="relative flex h-full w-full max-w-lg flex-col border-l border-slate-700 bg-slate-900 shadow-2xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby="inv-detail-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-2 border-b border-slate-800 p-4">
              <div>
                <h3 id="inv-detail-title" className="text-lg font-semibold text-white">
                  {detail?.name ?? 'Товар'}
                </h3>
                {detail ? <p className="text-xs text-slate-500">SKU: {detail.sku}</p> : null}
              </div>
              <button
                type="button"
                onClick={closeDetail}
                className="rounded-md border border-slate-600 p-2 text-slate-300 hover:bg-slate-800"
                aria-label="Закрыть"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-4">
              {detailLoading ? (
                <div className="flex items-center gap-2 py-8 text-slate-400">
                  <Loader2 className="h-5 w-5 animate-spin" />
                  Загрузка…
                </div>
              ) : null}
              {detailError ? <p className="text-sm text-rose-200">{detailError}</p> : null}
              {detail ? (
                <div className="space-y-6 text-sm">
                  <div className="grid grid-cols-2 gap-2 rounded-lg border border-slate-800 bg-slate-950/50 p-3 text-slate-300">
                    <div>Склад</div>
                    <div className="text-right font-medium text-slate-100">{detail.warehouse_qty}</div>
                    <div>Зал (учёт)</div>
                    <div className="text-right font-medium text-slate-100">{detail.hall_qty}</div>
                    <div>В задачах</div>
                    <div className="text-right font-medium text-slate-100">{detail.pending_qty}</div>
                    <div>Цель планограммы</div>
                    <div className="text-right font-medium text-slate-100">{detail.planogram_target_sum}</div>
                  </div>

                  <section>
                    <h4 className="mb-2 font-semibold text-slate-200">Партии и сроки годности</h4>
                    {detail.batches.length === 0 ? (
                      <p className="text-slate-500">Нет партий по этому магазину.</p>
                    ) : (
                      <ul className="space-y-2">
                        {detail.batches.map((b) => (
                          <li
                            key={
                              isRegularBatch(b)
                                ? String(b.id)
                                : `marked-${b.expiration_date}`
                            }
                            className="rounded-md border border-slate-700 bg-slate-950/40 px-3 py-2 text-slate-200"
                          >
                            {isMarkedGroup(b) ? (
                              <>
                                <span className="font-medium">до {b.expiration_date}</span>
                                <span className="mx-2 text-slate-500">·</span>
                                {b.unit_count} шт. (маркированные единицы)
                                <span className="ml-2 text-xs text-slate-500">
                                  (
                                  {b.days_to_expiry >= 0
                                    ? `осталось ${b.days_to_expiry} дн.`
                                    : `просрочка ${-b.days_to_expiry} дн.`}
                                  )
                                </span>
                                {expandedMarked.has(b.expiration_date) && b.serials.length > 0 ? (
                                  <ul className="mt-2 space-y-1 border-t border-slate-800 pt-2 text-xs text-slate-400">
                                    {b.serials.map((sn) => (
                                      <li key={sn}>{sn}</li>
                                    ))}
                                  </ul>
                                ) : null}
                                {!expandedMarked.has(b.expiration_date) &&
                                (b.serials.length > 0 || (b.serials_more ?? 0) > 0) ? (
                                  <button
                                    type="button"
                                    onClick={() =>
                                      void expandMarkedGroup(detail.id, b.expiration_date)
                                    }
                                    className="mt-2 block text-xs text-indigo-300 hover:text-indigo-200"
                                  >
                                    Показать серии
                                    {(b.serials_more ?? 0) > 0
                                      ? ` (ещё ${b.serials_more})`
                                      : ''}
                                  </button>
                                ) : null}
                              </>
                            ) : (
                              <>
                                <span className="font-medium">до {b.expiration_date}</span>
                                <span className="mx-2 text-slate-500">·</span>
                                {b.current_quantity} шт.
                                <span className="ml-2 text-xs text-slate-500">
                                  (
                                  {b.days_to_expiry >= 0
                                    ? `осталось ${b.days_to_expiry} дн.`
                                    : `просрочка ${-b.days_to_expiry} дн.`}
                                  )
                                </span>
                              </>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </section>

                  <section>
                    <h4 className="mb-2 font-semibold text-slate-200">Расположение в зале</h4>
                    {detail.locations.length === 0 ? (
                      <p className="text-slate-500">Нет привязки к слотам планограммы.</p>
                    ) : (
                      <ul className="space-y-2">
                        {detail.locations.map((loc, idx) => (
                          <li
                            key={`${loc.kind}-${loc.equipment_id}-${loc.slot_row}-${loc.slot_col}-${idx}`}
                            className="rounded-md border border-slate-700 bg-slate-950/40 px-3 py-2 text-slate-200"
                          >
                            {loc.label}
                            {loc.target_quantity != null ? (
                              <span className="ml-2 text-xs text-slate-500">цель: {loc.target_quantity}</span>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    )}
                    {detail.map_equipment_ids.length > 0 ? (
                      <button
                        type="button"
                        onClick={() => goToMap(detail.map_equipment_ids[0])}
                        className="mt-3 inline-flex items-center gap-2 rounded-lg border border-indigo-500/60 bg-indigo-900/30 px-3 py-2 text-sm font-medium text-indigo-100 hover:bg-indigo-900/50"
                      >
                        <MapPinned className="h-4 w-4" />
                        Показать на карте
                      </button>
                    ) : null}
                  </section>

                  <section>
                    <h4 className="mb-2 font-semibold text-slate-200">Списать со склада</h4>
                    <p className="mb-3 text-xs text-slate-500">
                      Создаёт задание сотруднику — списание в учёте после подтверждения.
                    </p>
                    {detail.batches.filter((b) => isRegularBatch(b) && b.current_quantity > 0)
                      .length === 0 ? (
                      <p className="text-slate-500">Нет партий с остатком на складе.</p>
                    ) : (
                      <div className="space-y-2 rounded-md border border-slate-700 bg-slate-950/40 p-3">
                        <label className="block text-xs text-slate-400">
                          Партия
                          <select
                            value={manualBatchId}
                            onChange={(e) => setManualBatchId(e.target.value)}
                            className="mt-1 block w-full rounded border border-slate-600 bg-slate-950 px-2 py-2 text-sm text-slate-100"
                          >
                            <option value="">Выберите…</option>
                            {detail.batches
                              .filter(isRegularBatch)
                              .filter((b) => b.current_quantity > 0)
                              .map((b) => (
                                <option key={b.id} value={String(b.id)}>
                                  до {b.expiration_date} — {b.current_quantity} шт.
                                </option>
                              ))}
                          </select>
                        </label>
                        <label className="block text-xs text-slate-400">
                          Количество
                          <input
                            type="number"
                            min={1}
                            value={manualQty}
                            onChange={(e) => setManualQty(e.target.value)}
                            className="mt-1 block w-full rounded border border-slate-600 bg-slate-950 px-2 py-2 text-sm text-slate-100"
                          />
                        </label>
                        <label className="block text-xs text-slate-400">
                          Причина
                          <input
                            value={manualReason}
                            onChange={(e) => setManualReason(e.target.value)}
                            placeholder="Например: бой, порча"
                            className="mt-1 block w-full rounded border border-slate-600 bg-slate-950 px-2 py-2 text-sm text-slate-100"
                          />
                        </label>
                        <button
                          type="button"
                          disabled={manualBusy}
                          onClick={() => void submitManualWriteOff()}
                          className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-rose-500/60 bg-rose-950/40 px-3 py-2 text-sm text-rose-100 hover:bg-rose-900/50 disabled:opacity-50"
                        >
                          {manualBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                          Создать задание на списание
                        </button>
                        {manualMsg ? (
                          <p className="text-xs text-sky-200">{manualMsg}</p>
                        ) : null}
                      </div>
                    )}
                  </section>
                </div>
              ) : null}
            </div>
          </aside>
        </div>
      ) : null}
    </div>
  );
}
