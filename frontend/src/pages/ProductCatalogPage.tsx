import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import type { AxiosError } from 'axios';
import { Loader2, Plus } from 'lucide-react';

import api from '../api';
import {
  CATALOG_EQUIPMENT_PRESETS,
  EQUIPMENT_TYPE_OPTIONS,
  formatAllowedEquipmentTypes,
} from '../map/equipmentProfiles';
import type { FloorEquipmentType } from '../types/floorPlan';

type CategoryRow = { id: number; name: string };

type ProductRow = {
  id: number;
  name: string;
  sku: string;
  gtin: string | null;
  category: CategoryRow;
  price: string;
  width: number;
  height: number;
  depth: number;
  weight: number;
  is_marked: boolean;
  is_stackable: boolean;
  allowed_equipment_types?: string[];
};

const emptyForm = {
  name: '',
  sku: '',
  gtin: '',
  categoryId: '',
  price: '',
  width: '50',
  height: '100',
  depth: '50',
  weight: '500',
  is_marked: false,
  is_stackable: true,
  allowedEquipmentTypes: [] as FloorEquipmentType[],
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

export function ProductCatalogPage(): React.ReactElement {
  const [products, setProducts] = useState<ProductRow[]>([]);
  const [categories, setCategories] = useState<CategoryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [newCategoryName, setNewCategoryName] = useState('');

  const load = useCallback(async (): Promise<void> => {
    setError(null);
    try {
      const [prodRes, catRes] = await Promise.all([
        api.get('/products/'),
        api.get('/categories/'),
      ]);
      setProducts(
        extractList<ProductRow>(prodRes.data).sort((a, b) =>
          a.name.localeCompare(b.name, 'ru'),
        ),
      );
      setCategories(extractList<CategoryRow>(catRes.data).sort((a, b) =>
        a.name.localeCompare(b.name, 'ru'),
      ));
    } catch {
      setError('Не удалось загрузить каталог.');
      setProducts([]);
      setCategories([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (form.categoryId || categories.length === 0) {
      return;
    }
    setForm((f) => ({ ...f, categoryId: String(categories[0]?.id ?? '') }));
  }, [categories, form.categoryId]);

  const addCategory = async (): Promise<void> => {
    const name = newCategoryName.trim();
    if (!name) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const { data } = await api.post<CategoryRow>('/categories/', { name });
      setCategories((prev) => [...prev, data].sort((a, b) => a.name.localeCompare(b.name, 'ru')));
      setForm((f) => ({ ...f, categoryId: String(data.id) }));
      setNewCategoryName('');
      setSuccess(`Категория «${data.name}» добавлена.`);
    } catch (err) {
      const ax = err as AxiosError<{ detail?: string; name?: string[] }>;
      const detail = ax.response?.data?.detail;
      const nameErr = ax.response?.data?.name?.[0];
      setError(typeof detail === 'string' ? detail : nameErr ?? 'Не удалось создать категорию.');
    } finally {
      setSaving(false);
    }
  };

  const submitProduct = async (event: React.FormEvent): Promise<void> => {
    event.preventDefault();
    if (!form.categoryId) {
      setError('Выберите категорию.');
      return;
    }
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      await api.post('/products/', {
        name: form.name.trim(),
        sku: form.sku.trim(),
        gtin: form.gtin.trim() || null,
        category: Number(form.categoryId),
        price: form.price,
        width: Number(form.width),
        height: Number(form.height),
        depth: Number(form.depth),
        weight: Number(form.weight),
        is_marked: form.is_marked,
        is_stackable: form.is_stackable,
        allowed_equipment_types: form.allowedEquipmentTypes,
      });
      setSuccess(`Товар «${form.name.trim()}» зарегистрирован. Следующий шаг — приёмка на склад.`);
      setForm({ ...emptyForm, categoryId: form.categoryId });
      await load();
    } catch (err) {
      const ax = err as AxiosError<Record<string, string[] | string> & { detail?: string }>;
      const data = ax.response?.data;
      if (data?.detail && typeof data.detail === 'string') {
        setError(data.detail);
      } else if (data) {
        const first = Object.values(data).flat()[0];
        setError(typeof first === 'string' ? first : 'Проверьте поля формы.');
      } else {
        setError('Не удалось зарегистрировать товар.');
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-white">Номенклатура</h2>
        <p className="mt-1 text-sm text-slate-400">
          Шаг 1 жизненного цикла: регистрация карточки товара (SKU, габариты для расчёта
          вместимости слота). Склад и партии — на вкладке «Приёмка».
        </p>
      </div>

      <ol className="flex flex-wrap gap-2 text-xs">
        <li className="rounded-full border border-violet-500/60 bg-violet-950/40 px-3 py-1 text-violet-100">
          1. Номенклатура
        </li>
        <li className="rounded-full border border-slate-700 px-3 py-1 text-slate-500">
          2. Приёмка
        </li>
        <li className="rounded-full border border-slate-700 px-3 py-1 text-slate-500">
          3. Планограмма
        </li>
        <li className="rounded-full border border-slate-700 px-3 py-1 text-slate-500">
          4. Выкладка
        </li>
      </ol>

      {error ? (
        <div className="rounded-lg border border-rose-500/40 bg-rose-950/30 px-3 py-2 text-sm text-rose-100">
          {error}
        </div>
      ) : null}
      {success ? (
        <div className="rounded-lg border border-emerald-500/40 bg-emerald-950/30 px-3 py-2 text-sm text-emerald-100">
          {success}
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        <form
          onSubmit={(e) => void submitProduct(e)}
          className="rounded-xl border border-slate-800 bg-slate-900/60 p-4"
        >
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
            <Plus className="h-4 w-4 text-violet-400" />
            Добавить товар
          </h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="sm:col-span-2 text-sm text-slate-300">
              Название
              <input
                required
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="mt-1 w-full rounded-md border border-slate-600 bg-slate-950 px-3 py-2"
              />
            </label>
            <label className="text-sm text-slate-300">
              SKU (артикул)
              <input
                required
                value={form.sku}
                onChange={(e) => setForm({ ...form, sku: e.target.value })}
                className="mt-1 w-full rounded-md border border-slate-600 bg-slate-950 px-3 py-2"
              />
            </label>
            <label className="text-sm text-slate-300">
              GTIN (опционально)
              <input
                value={form.gtin}
                onChange={(e) => setForm({ ...form, gtin: e.target.value })}
                className="mt-1 w-full rounded-md border border-slate-600 bg-slate-950 px-3 py-2"
              />
            </label>
            <label className="text-sm text-slate-300">
              Категория
              <select
                required
                value={form.categoryId}
                onChange={(e) => setForm({ ...form, categoryId: e.target.value })}
                className="mt-1 w-full rounded-md border border-slate-600 bg-slate-950 px-3 py-2"
              >
                <option value="">—</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm text-slate-300">
              Цена, ₽
              <input
                required
                type="number"
                min="0"
                step="0.01"
                value={form.price}
                onChange={(e) => setForm({ ...form, price: e.target.value })}
                className="mt-1 w-full rounded-md border border-slate-600 bg-slate-950 px-3 py-2"
              />
            </label>
          </div>
          <p className="mt-3 text-xs text-slate-500">
            Габариты в мм — для расчёта max_capacity на слоте (3D-укладка).
          </p>
          <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {(['width', 'height', 'depth', 'weight'] as const).map((key) => (
              <label key={key} className="text-xs text-slate-300">
                {key === 'width'
                  ? 'Ширина'
                  : key === 'height'
                    ? 'Высота'
                    : key === 'depth'
                      ? 'Глубина'
                      : 'Вес'}
                <input
                  required
                  type="number"
                  min="0.1"
                  step="0.1"
                  value={form[key]}
                  onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                  className="mt-1 w-full rounded-md border border-slate-600 bg-slate-950 px-2 py-1.5"
                />
              </label>
            ))}
          </div>
          <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/40 p-3">
            <p className="text-sm font-medium text-slate-200">Тип выкладки</p>
            <p className="mt-1 text-xs text-slate-500">
              Пустой выбор — товар доступен на любом оборудовании. Иначе только на отмеченных
              типах.
            </p>
            <div className="mt-3 flex flex-wrap gap-3">
              {EQUIPMENT_TYPE_OPTIONS.map((opt) => (
                <label key={opt.value} className="flex items-center gap-2 text-sm text-slate-300">
                  <input
                    type="checkbox"
                    checked={form.allowedEquipmentTypes.includes(opt.value)}
                    onChange={(e) => {
                      setForm((prev) => {
                        const next = e.target.checked
                          ? [...prev.allowedEquipmentTypes, opt.value]
                          : prev.allowedEquipmentTypes.filter((t) => t !== opt.value);
                        const needsNonStackable =
                          next.includes('hanger') || next.includes('mannequin');
                        return {
                          ...prev,
                          allowedEquipmentTypes: next,
                          is_stackable: needsNonStackable ? false : prev.is_stackable,
                        };
                      });
                    }}
                  />
                  {opt.label}
                </label>
              ))}
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {CATALOG_EQUIPMENT_PRESETS.map((preset) => (
                <button
                  key={preset.id}
                  type="button"
                  onClick={() =>
                    setForm((prev) => ({
                      ...prev,
                      allowedEquipmentTypes: [...preset.types],
                      is_stackable:
                        preset.stackable === false ? false : prev.is_stackable,
                    }))
                  }
                  className="rounded-full border border-slate-600 px-3 py-1 text-xs text-slate-200 hover:bg-slate-800"
                  title={preset.hint}
                >
                  {preset.label}
                </button>
              ))}
            </div>
            {form.allowedEquipmentTypes.length === 1 &&
            form.allowedEquipmentTypes[0] === 'mannequin' ? (
              <p className="mt-2 text-xs text-indigo-300">
                Макс. 1 ед. на зону экспозиции на манекене.
              </p>
            ) : null}
          </div>
          <div className="mt-3 flex flex-wrap gap-4 text-sm text-slate-300">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={form.is_stackable}
                onChange={(e) => setForm({ ...form, is_stackable: e.target.checked })}
              />
              Можно штабелировать
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={form.is_marked}
                onChange={(e) => setForm({ ...form, is_marked: e.target.checked })}
              />
              Маркировка (Честный ЗНАК)
            </label>
          </div>
          <button
            type="submit"
            disabled={saving}
            className="mt-4 flex w-full items-center justify-center gap-2 rounded-lg bg-violet-600 py-2.5 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-50"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Зарегистрировать товар
          </button>
        </form>

        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <h3 className="mb-2 text-sm font-semibold text-white">Новая категория</h3>
          <div className="flex gap-2">
            <input
              value={newCategoryName}
              onChange={(e) => setNewCategoryName(e.target.value)}
              placeholder="Например, Молочные"
              className="min-w-0 flex-1 rounded-md border border-slate-600 bg-slate-950 px-3 py-2 text-sm"
            />
            <button
              type="button"
              disabled={saving || !newCategoryName.trim()}
              onClick={() => void addCategory()}
              className="rounded-md border border-slate-600 px-3 py-2 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-50"
            >
              Добавить
            </button>
          </div>
          <p className="mt-4 text-xs text-slate-500">
            После регистрации перейдите на{' '}
            <Link to="/admin?tab=receiving" className="text-sky-300 underline">
              Приёмку
            </Link>{' '}
            для создания партии со сроком годности.
          </p>
        </div>
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
        <h3 className="mb-3 text-sm font-semibold text-white">Каталог ({products.length})</h3>
        {loading ? (
          <p className="text-sm text-slate-500">Загрузка…</p>
        ) : products.length === 0 ? (
          <p className="text-sm text-slate-500">Товаров пока нет. Добавьте первую позицию выше.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="text-left text-slate-400">
                <tr>
                  <th className="px-2 py-2">Название</th>
                  <th className="px-2 py-2">SKU</th>
                  <th className="px-2 py-2">Категория</th>
                  <th className="px-2 py-2">Цена</th>
                  <th className="px-2 py-2">Ш×В×Г, мм</th>
                  <th className="px-2 py-2">Оборудование</th>
                </tr>
              </thead>
              <tbody>
                {products.map((p) => (
                  <tr key={p.id} className="border-t border-slate-800 text-slate-200">
                    <td className="px-2 py-2 font-medium">{p.name}</td>
                    <td className="px-2 py-2">{p.sku}</td>
                    <td className="px-2 py-2">{p.category.name}</td>
                    <td className="px-2 py-2">{p.price}</td>
                    <td className="px-2 py-2 text-slate-400">
                      {p.width}×{p.height}×{p.depth}
                    </td>
                    <td className="px-2 py-2 text-slate-400">
                      {formatAllowedEquipmentTypes(p.allowed_equipment_types)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
