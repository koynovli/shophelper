import React, { useCallback, useEffect, useState } from 'react';
import type { AxiosError } from 'axios';
import { Loader2, Plus, ReceiptText, Trash2 } from 'lucide-react';

import api from '../api';
import { DiscrepancyPanel } from '../components/DiscrepancyPanel';

type SupplierRow = { id: number; name: string; inn: string; contact_info?: string };

type ProductRow = { id: number; name: string; sku: string };

type OrderItemRow = {
  id: number;
  product: number;
  product_detail?: { id: number; name: string; sku: string };
  quantity: number;
  actual_quantity: number;
  purchase_price: string;
  discrepancy_note?: string;
};

type ReceivingTaskBrief = {
  id: number;
  status: string;
  assigned_to: number | null;
  assigned_to_username: string | null;
};

type EmployeeRow = { id: number; username: string };

type SupplyOrderRow = {
  id: number;
  status: string;
  created_at: string;
  received_at: string | null;
  planned_receiving_date?: string | null;
  supplier: number | null;
  supplier_detail?: SupplierRow | null;
  store_name?: string;
  total_amount: string;
  total_cost: string;
  has_discrepancies?: boolean;
  receiving_task?: ReceivingTaskBrief | null;
  items: OrderItemRow[];
};

type LineDraft = {
  key: string;
  productId: string;
  quantity: string;
  purchasePrice: string;
};

type OrderFilter = 'all' | 'draft' | 'ordered' | 'received' | 'discrepancies';

const STATUS_LABELS: Record<string, string> = {
  draft: 'Черновик',
  ordered: 'В пути',
  received: 'Принят',
  cancelled: 'Отменен',
};

const STATUS_STYLES: Record<string, string> = {
  draft: 'bg-slate-700/60 text-slate-200 border-slate-600',
  ordered: 'bg-blue-900/40 text-blue-200 border-blue-700/50',
  received: 'bg-emerald-900/40 text-emerald-200 border-emerald-700/50',
  cancelled: 'bg-rose-900/40 text-rose-200 border-rose-700/50',
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

function newLine(): LineDraft {
  return {
    key: String(Date.now()) + Math.random(),
    productId: '',
    quantity: '1',
    purchasePrice: '0',
  };
}

function formatDate(dateString: string | null): string {
  if (!dateString) {
    return '—';
  }
  const parsed = new Date(dateString);
  if (Number.isNaN(parsed.getTime())) {
    return dateString;
  }
  return new Intl.DateTimeFormat('ru-RU', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(parsed);
}

function formatDateOnly(dateString: string | null | undefined): string {
  if (!dateString) {
    return '—';
  }
  const parsed = new Date(dateString);
  if (Number.isNaN(parsed.getTime())) {
    return dateString;
  }
  return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium' }).format(parsed);
}

function isPlannedOverdue(
  planned: string | null | undefined,
  receivedAt: string | null,
): boolean {
  if (!planned || !receivedAt) {
    return false;
  }
  const p = new Date(planned);
  const r = new Date(receivedAt);
  if (Number.isNaN(p.getTime()) || Number.isNaN(r.getTime())) {
    return false;
  }
  const plannedDay = Date.UTC(p.getFullYear(), p.getMonth(), p.getDate());
  const receivedDay = Date.UTC(r.getFullYear(), r.getMonth(), r.getDate());
  return receivedDay > plannedDay;
}

function parseApiError(err: unknown, fallback: string): string {
  const ax = err as AxiosError<Record<string, string[] | string> & { detail?: string }>;
  const data = ax.response?.data;
  if (data?.detail && typeof data.detail === 'string') {
    return data.detail;
  }
  if (data) {
    const first = Object.values(data).flat()[0];
    if (typeof first === 'string') {
      return first;
    }
  }
  return fallback;
}

export function SupplyOrdersPage(): React.ReactElement {
  const [orders, setOrders] = useState<SupplyOrderRow[]>([]);
  const [suppliers, setSuppliers] = useState<SupplierRow[]>([]);
  const [products, setProducts] = useState<ProductRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [supplierId, setSupplierId] = useState('');
  const [newSupplierName, setNewSupplierName] = useState('');
  const [newSupplierInn, setNewSupplierInn] = useState('');
  const [newSupplierContact, setNewSupplierContact] = useState('');
  const [lines, setLines] = useState<LineDraft[]>([newLine()]);
  const [editingOrderId, setEditingOrderId] = useState<number | null>(null);
  const [orderFilter, setOrderFilter] = useState<OrderFilter>('all');
  const [employees, setEmployees] = useState<EmployeeRow[]>([]);
  const [receivingAssigneeId, setReceivingAssigneeId] = useState('');
  const [plannedReceivingDate, setPlannedReceivingDate] = useState('');

  const load = useCallback(async (): Promise<void> => {
    setError(null);
    try {
      const [ordRes, supRes, prodRes, empRes] = await Promise.all([
        api.get('/supply-orders/'),
        api.get('/suppliers/'),
        api.get('/products/'),
        api.get('/employees/'),
      ]);
      setEmployees(extractList<EmployeeRow>(empRes.data));
      setOrders(extractList<SupplyOrderRow>(ordRes.data));
      const sups = extractList<SupplierRow>(supRes.data).sort((a, b) =>
        a.name.localeCompare(b.name, 'ru'),
      );
      setSuppliers(sups);
      setProducts(
        extractList<ProductRow>(prodRes.data).sort((a, b) =>
          a.name.localeCompare(b.name, 'ru'),
        ),
      );
      setSupplierId((prev) => prev || (sups[0] ? String(sups[0].id) : ''));
    } catch {
      setError('Не удалось загрузить данные.');
      setOrders([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (lines[0]?.productId || products.length === 0) {
      return;
    }
    setLines([{ ...lines[0], productId: String(products[0]?.id ?? '') }]);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only when products first load
  }, [products]);

  const resetOrderForm = (): void => {
    setEditingOrderId(null);
    setLines([newLine()]);
    setPlannedReceivingDate('');
  };

  const cancelEdit = (): void => {
    resetOrderForm();
    setSuccess(null);
  };

  const startEditOrder = (order: SupplyOrderRow): void => {
    setEditingOrderId(order.id);
    setSupplierId(order.supplier !== null ? String(order.supplier) : '');
    setPlannedReceivingDate(order.planned_receiving_date ?? '');
    setLines(
      order.items.map((item) => ({
        key: String(item.id),
        productId: String(item.product),
        quantity: String(item.quantity),
        purchasePrice: String(item.purchase_price),
      })),
    );
    setSuccess(null);
    setError(null);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const addSupplier = async (): Promise<void> => {
    const name = newSupplierName.trim();
    const inn = newSupplierInn.trim();
    if (!name || !inn) {
      setError('Укажите название и ИНН поставщика.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const { data } = await api.post<SupplierRow>('/suppliers/', {
        name,
        inn,
        contact_info: newSupplierContact.trim(),
      });
      setSuppliers((prev) => [...prev, data].sort((a, b) => a.name.localeCompare(b.name, 'ru')));
      setSupplierId(String(data.id));
      setNewSupplierName('');
      setNewSupplierInn('');
      setNewSupplierContact('');
      setSuccess(`Поставщик «${data.name}» зарегистрирован.`);
    } catch (err) {
      setError(parseApiError(err, 'Не удалось зарегистрировать поставщика.'));
    } finally {
      setSaving(false);
    }
  };

  const buildItemsPayload = (): { product: number; quantity: number; purchase_price: string }[] | null => {
    const items: { product: number; quantity: number; purchase_price: string }[] = [];
    for (const line of lines) {
      if (!line.productId) {
        continue;
      }
      const qty = Math.max(1, Math.floor(Number(line.quantity) || 0));
      const price = line.purchasePrice.trim() || '0';
      items.push({
        product: Number(line.productId),
        quantity: qty,
        purchase_price: price,
      });
    }
    if (items.length === 0) {
      return null;
    }
    return items;
  };

  const buildOrderBody = (
    items: { product: number; quantity: number; purchase_price: string }[],
  ): {
    items: typeof items;
    supplier?: number;
    assigned_to?: number;
    planned_receiving_date?: string | null;
  } => {
    const body: {
      items: typeof items;
      supplier?: number;
      assigned_to?: number;
      planned_receiving_date?: string | null;
    } = { items };
    if (supplierId) {
      body.supplier = Number(supplierId);
    }
    if (receivingAssigneeId) {
      body.assigned_to = Number(receivingAssigneeId);
    }
    if (plannedReceivingDate) {
      body.planned_receiving_date = plannedReceivingDate;
    } else if (editingOrderId !== null) {
      body.planned_receiving_date = null;
    }
    return body;
  };

  const submitAssignBody = (): { assigned_to?: number; planned_receiving_date?: string | null } => {
    const body: { assigned_to?: number; planned_receiving_date?: string | null } = {};
    if (receivingAssigneeId) {
      body.assigned_to = Number(receivingAssigneeId);
    }
    if (plannedReceivingDate) {
      body.planned_receiving_date = plannedReceivingDate;
    }
    return body;
  };

  const receivingStatusHint = (order: SupplyOrderRow): string => {
    const rt = order.receiving_task;
    if (!rt) {
      return 'Задача приёмки создаётся…';
    }
    if (rt.status === 'COMPLETED') {
      return 'Приёмка завершена';
    }
    if (rt.assigned_to_username) {
      return `Исполнитель: ${rt.assigned_to_username}`;
    }
    return 'В общем пуле задач сотрудника';
  };

  const saveDraft = async (): Promise<void> => {
    const items = buildItemsPayload();
    if (!items) {
      setError('Добавьте хотя бы одну позицию с выбранным товаром.');
      return;
    }
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const body = buildOrderBody(items);
      if (editingOrderId !== null) {
        await api.patch(`/supply-orders/${editingOrderId}/`, body);
        setSuccess(`Черновик #${editingOrderId} обновлён.`);
      } else {
        await api.post('/supply-orders/', { ...body, status: 'draft' });
        setSuccess('Черновик заказа сохранён.');
      }
      resetOrderForm();
      await load();
    } catch (err) {
      setError(parseApiError(err, 'Не удалось сохранить черновик.'));
    } finally {
      setSaving(false);
    }
  };

  const submitOrderFromForm = async (): Promise<void> => {
    const items = buildItemsPayload();
    if (!items) {
      setError('Добавьте хотя бы одну позицию с выбранным товаром.');
      return;
    }
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const body = buildOrderBody(items);
      if (editingOrderId !== null) {
        await api.patch(`/supply-orders/${editingOrderId}/`, body);
        await api.post(`/supply-orders/${editingOrderId}/submit/`, submitAssignBody());
        setSuccess(
          `Заказ #${editingOrderId} оформлен. Сотрудник выполнит приёмку в PWA.`,
        );
      } else {
        await api.post('/supply-orders/', { ...body, status: 'ordered' });
        setSuccess('Заказ оформлен. Создана задача приёмки для сотрудника.');
      }
      resetOrderForm();
      await load();
    } catch (err) {
      setError(parseApiError(err, 'Не удалось оформить заказ.'));
    } finally {
      setSaving(false);
    }
  };

  const submitDraftCard = async (orderId: number): Promise<void> => {
    setSaving(true);
    setError(null);
    try {
      await api.post(`/supply-orders/${orderId}/submit/`, submitAssignBody());
      setSuccess(`Заказ #${orderId} оформлен. Задача приёмки в PWA сотрудника.`);
      if (editingOrderId === orderId) {
        resetOrderForm();
      }
      await load();
    } catch (err) {
      setError(parseApiError(err, 'Не удалось оформить заказ.'));
    } finally {
      setSaving(false);
    }
  };

  const deleteDraft = async (orderId: number): Promise<void> => {
    if (!window.confirm(`Удалить черновик заказа #${orderId}?`)) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.delete(`/supply-orders/${orderId}/`);
      setSuccess(`Черновик #${orderId} удалён.`);
      if (editingOrderId === orderId) {
        resetOrderForm();
      }
      await load();
    } catch (err) {
      setError(parseApiError(err, 'Не удалось удалить черновик.'));
    } finally {
      setSaving(false);
    }
  };

  const getSupplierName = (order: SupplyOrderRow): string =>
    order.supplier_detail?.name ??
    (order.supplier !== null ? `Поставщик #${order.supplier}` : 'Не указан');

  const filteredOrders = orders.filter((o) => {
    if (orderFilter === 'all') {
      return true;
    }
    if (orderFilter === 'discrepancies') {
      return o.status === 'received' && Boolean(o.has_discrepancies);
    }
    return o.status === orderFilter;
  });

  const filterButtons: { key: OrderFilter; label: string }[] = [
    { key: 'all', label: 'Все' },
    { key: 'draft', label: 'Черновики' },
    { key: 'ordered', label: 'В пути' },
    { key: 'received', label: 'Приняты' },
    { key: 'discrepancies', label: 'С расхождениями' },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-white">Заказы поставщику</h2>
        <p className="mt-1 text-sm text-slate-400">
          Оформление заказа и приёмка на склад с созданием FEFO-партий по строкам заказа.
        </p>
      </div>

      {error ? (
        <div className="rounded-lg border border-rose-500/40 bg-rose-950/30 px-4 py-2 text-sm text-rose-100">
          {error}
        </div>
      ) : null}
      {success ? (
        <div className="rounded-lg border border-emerald-500/40 bg-emerald-950/30 px-4 py-2 text-sm text-emerald-100">
          {success}
        </div>
      ) : null}

      <section className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
        <h3 className="mb-2 text-base font-medium text-white">Справочник поставщиков</h3>
        <p className="mb-4 text-sm text-slate-400">
          Регистрация контрагентов для заказов (ИНН — 10 или 12 цифр).
        </p>

        {suppliers.length > 0 ? (
          <div className="mb-4 overflow-x-auto rounded-lg border border-slate-800">
            <table className="w-full min-w-[480px] text-left text-sm text-slate-300">
              <thead>
                <tr className="border-b border-slate-700 bg-slate-950/50 text-slate-500">
                  <th className="px-3 py-2">Название</th>
                  <th className="px-3 py-2">ИНН</th>
                  <th className="px-3 py-2">Контакты</th>
                </tr>
              </thead>
              <tbody>
                {suppliers.map((s) => (
                  <tr key={s.id} className="border-b border-slate-800/80">
                    <td className="px-3 py-2 text-slate-100">{s.name}</td>
                    <td className="px-3 py-2 font-mono text-xs">{s.inn}</td>
                    <td className="px-3 py-2 text-slate-400">{s.contact_info || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="mb-4 text-sm text-slate-500">Поставщиков пока нет.</p>
        )}

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <input
            type="text"
            placeholder="Название организации"
            value={newSupplierName}
            onChange={(e) => setNewSupplierName(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
          />
          <input
            type="text"
            placeholder="ИНН (10 или 12 цифр)"
            value={newSupplierInn}
            onChange={(e) => setNewSupplierInn(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
          />
          <input
            type="text"
            placeholder="Телефон / email"
            value={newSupplierContact}
            onChange={(e) => setNewSupplierContact(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white sm:col-span-2 lg:col-span-1"
          />
          <button
            type="button"
            disabled={saving}
            onClick={() => void addSupplier()}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
          >
            Зарегистрировать
          </button>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
        <h3 className="mb-4 text-base font-medium text-white">
          {editingOrderId !== null ? `Редактирование черновика #${editingOrderId}` : 'Новый заказ'}
        </h3>
        {editingOrderId !== null ? (
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-500/30 bg-amber-950/20 px-3 py-2 text-sm text-amber-100">
            <span>Изменения сохраняются в черновик или оформляют заказ.</span>
            <button
              type="button"
              onClick={cancelEdit}
              className="text-amber-200 underline hover:text-white"
            >
              Отмена
            </button>
          </div>
        ) : null}

        <div className="mb-4 grid gap-4 sm:grid-cols-2">
          <label className="block text-sm text-slate-300">
            Поставщик
            <select
              value={supplierId}
              onChange={(e) => setSupplierId(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
            >
              <option value="">— не выбран —</option>
              {suppliers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} (ИНН {s.inn})
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm text-slate-300">
            Исполнитель приёмки
            <select
              value={receivingAssigneeId}
              onChange={(e) => setReceivingAssigneeId(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
            >
              <option value="">Общий пул (любой сотрудник)</option>
              {employees.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.username}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm text-slate-300 sm:col-span-2">
            Плановая дата приёмки
            <input
              type="date"
              value={plannedReceivingDate}
              onChange={(e) => setPlannedReceivingDate(e.target.value)}
              className="mt-1 w-full max-w-xs rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
            />
            <span className="mt-1 block text-xs text-slate-500">Необязательно</span>
          </label>
        </div>
        <p className="mb-4 text-xs text-slate-500">
          После оформления заказа сотрудник выполняет приёмку в PWA («Мои задачи»).
        </p>

        <div className="space-y-3">
          {lines.map((line, idx) => (
            <div
              key={line.key}
              className="grid gap-2 rounded-lg border border-slate-800 bg-slate-950/50 p-3 sm:grid-cols-[1fr_100px_120px_auto]"
            >
              <select
                value={line.productId}
                onChange={(e) => {
                  const v = e.target.value;
                  setLines((prev) =>
                    prev.map((l, i) => (i === idx ? { ...l, productId: v } : l)),
                  );
                }}
                className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
              >
                <option value="">Товар…</option>
                {products.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.sku})
                  </option>
                ))}
              </select>
              <input
                type="number"
                min={1}
                placeholder="Кол-во"
                value={line.quantity}
                onChange={(e) => {
                  const v = e.target.value;
                  setLines((prev) =>
                    prev.map((l, i) => (i === idx ? { ...l, quantity: v } : l)),
                  );
                }}
                className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
              />
              <input
                type="text"
                placeholder="Цена закупки"
                value={line.purchasePrice}
                onChange={(e) => {
                  const v = e.target.value;
                  setLines((prev) =>
                    prev.map((l, i) => (i === idx ? { ...l, purchasePrice: v } : l)),
                  );
                }}
                className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
              />
              <button
                type="button"
                disabled={lines.length <= 1}
                onClick={() => setLines((prev) => prev.filter((_, i) => i !== idx))}
                className="flex items-center justify-center rounded-lg border border-slate-700 p-2 text-slate-400 hover:text-rose-300 disabled:opacity-30"
                title="Удалить строку"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setLines((prev) => [...prev, newLine()])}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-600 px-3 py-2 text-sm text-slate-200 hover:bg-slate-800"
          >
            <Plus className="h-4 w-4" />
            Строка
          </button>
          <button
            type="button"
            disabled={saving}
            onClick={() => void saveDraft()}
            className="rounded-lg border border-slate-500 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-50"
          >
            {editingOrderId !== null ? 'Сохранить изменения' : 'Сохранить черновик'}
          </button>
          <button
            type="button"
            disabled={saving}
            onClick={() => void submitOrderFromForm()}
            className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Оформить заказ
          </button>
        </div>
      </section>

      <div className="flex flex-wrap gap-2">
        {filterButtons.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            onClick={() => setOrderFilter(key)}
            className={`rounded-lg px-3 py-1.5 text-sm transition ${
              orderFilter === key
                ? 'bg-slate-700 text-white'
                : 'border border-slate-700 text-slate-400 hover:bg-slate-800'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-10 text-center text-slate-300">
          <Loader2 className="mx-auto h-8 w-8 animate-spin text-emerald-400" />
        </div>
      ) : filteredOrders.length === 0 ? (
        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-10 text-center text-slate-300">
          {orders.length === 0
            ? 'Заказов пока нет — создайте первый выше.'
            : 'Нет заказов в выбранном фильтре.'}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          {filteredOrders.map((order) => (
            <article
              key={order.id}
              className="rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-xl"
            >
              <div className="mb-4 flex items-start justify-between gap-3">
                <div className="flex items-center gap-2">
                  <ReceiptText className="h-5 w-5 text-emerald-400" />
                  <h3 className="text-lg font-semibold text-white">Заказ #{order.id}</h3>
                </div>
                <span
                  className={`rounded-full border px-3 py-1 text-xs font-medium uppercase ${STATUS_STYLES[order.status] ?? STATUS_STYLES.draft}`}
                >
                  {STATUS_LABELS[order.status] ?? order.status}
                </span>
              </div>

              <dl className="mb-4 space-y-1 text-sm text-slate-300">
                <div>
                  Поставщик:{' '}
                  <strong className="text-slate-100">{getSupplierName(order)}</strong>
                </div>
                <div>
                  Магазин: <strong className="text-slate-100">{order.store_name ?? '—'}</strong>
                </div>
                <div>
                  Создан: <strong className="text-slate-100">{formatDate(order.created_at)}</strong>
                </div>
                {order.status === 'received' ? (
                  <>
                    <div>
                      Принят:{' '}
                      <strong className="text-slate-100">{formatDate(order.received_at)}</strong>
                    </div>
                    {order.planned_receiving_date ? (
                      <div
                        className={
                          isPlannedOverdue(order.planned_receiving_date, order.received_at)
                            ? 'text-rose-300'
                            : 'text-slate-400'
                        }
                      >
                        Плановая дата:{' '}
                        <strong>{formatDateOnly(order.planned_receiving_date)}</strong>
                        {isPlannedOverdue(order.planned_receiving_date, order.received_at)
                          ? ' — позже плана'
                          : null}
                      </div>
                    ) : null}
                    <div>
                      Сумма приёмки:{' '}
                      <strong className="text-slate-100">{order.total_cost} ₽</strong>
                    </div>
                  </>
                ) : order.status === 'ordered' ? (
                  <>
                    <div>
                      Сумма заказа:{' '}
                      <strong className="text-slate-100">{order.total_amount} ₽</strong>
                    </div>
                    {order.planned_receiving_date ? (
                      <div className="text-sky-300">
                        Плановая приёмка:{' '}
                        <strong>{formatDateOnly(order.planned_receiving_date)}</strong>
                      </div>
                    ) : null}
                    <div className="text-sky-300">
                      Ожидает приёмки: {receivingStatusHint(order)}
                      {order.receiving_task ? (
                        <span className="text-slate-500">
                          {' '}
                          (задача #{order.receiving_task.id})
                        </span>
                      ) : null}
                    </div>
                  </>
                ) : (
                  <div>
                    Сумма заказа:{' '}
                    <strong className="text-slate-100">{order.total_amount} ₽</strong>
                  </div>
                )}
                {order.status === 'received' && order.has_discrepancies ? (
                  <div className="text-amber-300">Есть расхождения по количеству</div>
                ) : null}
              </dl>

              {order.status === 'received' && order.has_discrepancies ? (
                <div className="mb-4">
                  <DiscrepancyPanel items={order.items} />
                </div>
              ) : null}

              <table className="mb-4 w-full text-left text-xs text-slate-300">
                <thead>
                  <tr className="border-b border-slate-700 text-slate-500">
                    <th className="py-1 pr-2">Товар</th>
                    <th className="py-1 pr-2">SKU</th>
                    {order.status === 'received' && !order.has_discrepancies ? (
                      <>
                        <th className="py-1 pr-2 text-right">Заказано</th>
                        <th className="py-1 pr-2 text-right">Принято</th>
                      </>
                    ) : order.status === 'received' ? (
                      <th className="py-1 pr-2 text-right">Кол-во</th>
                    ) : (
                      <th className="py-1 pr-2 text-right">Кол-во</th>
                    )}
                    <th className="py-1 text-right">Цена</th>
                  </tr>
                </thead>
                <tbody>
                  {order.items.map((item) => (
                    <tr key={item.id} className="border-b border-slate-800/80">
                      <td className="py-1.5 pr-2 text-slate-100">
                        {item.product_detail?.name ?? `#${item.product}`}
                      </td>
                      <td className="py-1.5 pr-2">{item.product_detail?.sku ?? '—'}</td>
                      {order.status === 'received' && !order.has_discrepancies ? (
                        <>
                          <td className="py-1.5 pr-2 text-right">{item.quantity}</td>
                          <td className="py-1.5 pr-2 text-right">{item.actual_quantity}</td>
                        </>
                      ) : order.status === 'received' ? (
                        <td className="py-1.5 pr-2 text-right">
                          {item.quantity} → {item.actual_quantity}
                        </td>
                      ) : (
                        <td className="py-1.5 pr-2 text-right">{item.quantity}</td>
                      )}
                      <td className="py-1.5 text-right">{item.purchase_price}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {order.status === 'draft' ? (
                <div className="mb-4 flex flex-wrap gap-2 border-t border-slate-800 pt-4">
                  <button
                    type="button"
                    disabled={saving}
                    onClick={() => startEditOrder(order)}
                    className="rounded-lg border border-slate-600 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-50"
                  >
                    Редактировать
                  </button>
                  <button
                    type="button"
                    disabled={saving}
                    onClick={() => void submitDraftCard(order.id)}
                    className="rounded-lg bg-emerald-600/90 px-3 py-1.5 text-sm text-white hover:bg-emerald-500 disabled:opacity-50"
                  >
                    Оформить заказ
                  </button>
                  <button
                    type="button"
                    disabled={saving}
                    onClick={() => void deleteDraft(order.id)}
                    className="rounded-lg border border-rose-600/50 px-3 py-1.5 text-sm text-rose-200 hover:bg-rose-950/40 disabled:opacity-50"
                  >
                    Удалить
                  </button>
                </div>
              ) : null}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
