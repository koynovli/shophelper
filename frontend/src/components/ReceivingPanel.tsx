import React, { useEffect, useState } from 'react';
import type { AxiosError } from 'axios';

import api from '../api';

type ProductRow = {
  id: number;
  name: string;
  sku: string;
};

type FeedbackState = { type: 'ok' | 'err'; text: string } | null;

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

export function ReceivingPanel(): React.ReactElement {
  const [products, setProducts] = useState<ProductRow[]>([]);
  const [productId, setProductId] = useState<string>('');
  const [quantity, setQuantity] = useState<number>(1);
  const [expiryDate, setExpiryDate] = useState<string>('');
  const [saving, setSaving] = useState<boolean>(false);
  const [feedback, setFeedback] = useState<FeedbackState>(null);

  useEffect(() => {
    const fetchProducts = async (): Promise<void> => {
      try {
        const response = await api.get('/products/');
        const rows = extractList<ProductRow>(response.data).sort((a, b) =>
          a.name.localeCompare(b.name, 'ru'),
        );
        setProducts(rows);
        setProductId(rows[0] ? String(rows[0].id) : '');
      } catch {
        setProducts([]);
      }
    };
    void fetchProducts();
  }, []);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    if (!productId) {
      setFeedback({ type: 'err', text: 'Выберите товар.' });
      return;
    }
    if (!expiryDate) {
      setFeedback({ type: 'err', text: 'Укажите срок годности.' });
      return;
    }
    try {
      setSaving(true);
      setFeedback(null);
      await api.post('/batches/', {
        product: Number(productId),
        quantity: Math.max(1, Math.floor(quantity)),
        expiry_date: expiryDate,
      });
      setFeedback({
        type: 'ok',
        text: 'Партия создана. Остатки обновлены, проверка планограмм запущена.',
      });
      setQuantity(1);
      setExpiryDate('');
    } catch (err) {
      const ax = err as AxiosError<{ detail?: string }>;
      const detail = ax.response?.data?.detail;
      setFeedback({
        type: 'err',
        text: typeof detail === 'string' ? detail : 'Не удалось сохранить партию.',
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
      <h3 className="mb-1 text-lg font-semibold text-white">Приемка поставки</h3>
      <p className="mb-4 text-sm text-slate-400">
        Создание партии с автоматическим обновлением склада и задач выкладки.
      </p>
      {feedback ? (
        <p
          className={`mb-3 rounded-md border px-3 py-2 text-sm ${
            feedback.type === 'ok'
              ? 'border-emerald-600/60 bg-emerald-900/25 text-emerald-100'
              : 'border-rose-600/60 bg-rose-900/25 text-rose-100'
          }`}
        >
          {feedback.text}
        </p>
      ) : null}
      <form className="grid gap-3 sm:grid-cols-2" onSubmit={(event) => void handleSubmit(event)}>
        <label className="text-sm text-slate-300 sm:col-span-2">
          Товар
          <select
            className="mt-1 w-full rounded-md border border-slate-600 bg-slate-950 px-3 py-2 text-slate-100"
            value={productId}
            onChange={(event) => setProductId(event.target.value)}
            disabled={products.length === 0}
          >
            {products.map((product) => (
              <option key={product.id} value={String(product.id)}>
                {product.name} ({product.sku})
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm text-slate-300">
          Количество
          <input
            type="number"
            min={1}
            value={quantity}
            onChange={(event) => setQuantity(Math.max(1, Number(event.target.value) || 1))}
            className="mt-1 w-full rounded-md border border-slate-600 bg-slate-950 px-3 py-2 text-slate-100"
          />
        </label>
        <label className="text-sm text-slate-300">
          Expiry Date
          <input
            type="date"
            value={expiryDate}
            onChange={(event) => setExpiryDate(event.target.value)}
            className="mt-1 w-full rounded-md border border-slate-600 bg-slate-950 px-3 py-2 text-slate-100"
          />
        </label>
        <div className="sm:col-span-2">
          <button
            type="submit"
            disabled={saving}
            className="rounded-md border border-emerald-500/70 bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-60"
          >
            {saving ? 'Сохранение...' : 'Зарегистрировать партию'}
          </button>
        </div>
      </form>
    </div>
  );
}
