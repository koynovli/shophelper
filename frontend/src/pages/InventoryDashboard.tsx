import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { AxiosError } from 'axios';
import { Download, Loader2, MapPinned, Search, X } from 'lucide-react';

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
  status: 'OK' | 'LOW_STOCK' | 'EXPIRING' | string;
  under_floor_target: boolean;
};

type BatchDetail = {
  id: number;
  expiration_date: string;
  current_quantity: number;
  initial_quantity: number;
  is_active: boolean;
  days_to_expiry: number;
};

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

  const openDetail = async (id: number): Promise<void> => {
    setDetailLoading(true);
    setDetailError(null);
    try {
      const r = await api.get<ProductDetail>(`/product-tracking/${id}/`);
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

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-white">Учёт товаров</h2>
          <p className="text-sm text-slate-400">
            Сводка по партиям, складу (StockItem), залу (остатки на полке) и активным задачам выкладки.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void exportCsv()}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-200 hover:border-emerald-500/50"
        >
          <Download className="h-4 w-4" />
          Экспорт CSV
        </button>
      </div>

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
                const expiring = row.status === 'EXPIRING';
                const rowClass = deficitRow
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
                            key={b.id}
                            className="rounded-md border border-slate-700 bg-slate-950/40 px-3 py-2 text-slate-200"
                          >
                            <span className="font-medium">до {b.expiration_date}</span>
                            <span className="mx-2 text-slate-500">·</span>
                            {b.current_quantity} шт.
                            <span className="ml-2 text-xs text-slate-500">
                              ({b.days_to_expiry >= 0 ? `осталось ${b.days_to_expiry} дн.` : `просрочка ${-b.days_to_expiry} дн.`})
                            </span>
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
                </div>
              ) : null}
            </div>
          </aside>
        </div>
      ) : null}
    </div>
  );
}
