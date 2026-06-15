import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import type { AxiosError } from 'axios';
import { Loader2, Pencil, Plus, Trash2 } from 'lucide-react';

import api from '../api';
import {
  CATALOG_EQUIPMENT_PRESETS,
  EQUIPMENT_TYPE_OPTIONS,
  formatAllowedEquipmentTypes,
} from '../map/equipmentProfiles';
import type { FloorEquipmentType } from '../types/floorPlan';
import { normalizeEquipmentType } from '../types/floorPlan';

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
  shelf_life_days?: number | null;
  sale_unit?: 'piece' | 'weight';
  packing_coefficient?: number;
  bulk_density?: number | null;
};

type ProductFormState = {
  name: string;
  sku: string;
  gtin: string;
  categoryId: string;
  price: string;
  width: string;
  height: string;
  depth: string;
  weight: string;
  is_marked: boolean;
  is_stackable: boolean;
  allowedEquipmentTypes: FloorEquipmentType[];
  shelfLifeDays: string;
  saleUnit: 'piece' | 'weight';
  packingCoefficient: string;
  bulkDensity: string;
};

const VALID_EQUIPMENT_TYPES = new Set<FloorEquipmentType>(
  EQUIPMENT_TYPE_OPTIONS.map((o) => o.value),
);

const WEIGHT_BULK_FILL_FRACTION = 0.55;

function previewBulkDensityKgM3(form: ProductFormState): number | null {
  const w = Number(form.width);
  const h = Number(form.height);
  const d = Number(form.depth);
  const weightG = Number(form.weight);
  if (!w || !h || !d || !weightG) {
    return null;
  }
  const volM3 = (w / 1000) * (h / 1000) * (d / 1000);
  if (volM3 <= 0) {
    return null;
  }
  const particle = weightG / 1000 / volM3;
  return Math.round(particle * WEIGHT_BULK_FILL_FRACTION * 10) / 10;
}

const emptyForm: ProductFormState = {
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
  allowedEquipmentTypes: [],
  shelfLifeDays: '',
  saleUnit: 'piece',
  packingCoefficient: '0.6',
  bulkDensity: '',
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

function parseApiError(err: unknown, fallback: string): string {
  const ax = err as AxiosError<
    string | string[] | Record<string, string[] | string> & { detail?: string }
  >;
  const data = ax.response?.data;
  if (typeof data === 'string') {
    return data;
  }
  if (Array.isArray(data) && typeof data[0] === 'string') {
    return data[0];
  }
  if (data && typeof data === 'object' && !Array.isArray(data)) {
    if (typeof data.detail === 'string') {
      return data.detail;
    }
    const first = Object.values(data).flat()[0];
    if (typeof first === 'string') {
      return first;
    }
  }
  return fallback;
}

function productToForm(product: ProductRow): ProductFormState {
  const allowedEquipmentTypes = (product.allowed_equipment_types ?? [])
    .map((t) => normalizeEquipmentType(String(t)))
    .filter((t): t is FloorEquipmentType => VALID_EQUIPMENT_TYPES.has(t));
  return {
    name: product.name,
    sku: product.sku,
    gtin: product.gtin ?? '',
    categoryId: String(product.category.id),
    price: String(product.price),
    width: String(product.width),
    height: String(product.height),
    depth: String(product.depth),
    weight: String(product.weight),
    is_marked: product.is_marked,
    is_stackable: product.is_stackable,
    allowedEquipmentTypes,
    shelfLifeDays:
      product.shelf_life_days != null && product.shelf_life_days > 0
        ? String(product.shelf_life_days)
        : '',
    saleUnit: product.sale_unit === 'weight' ? 'weight' : 'piece',
    packingCoefficient:
      product.packing_coefficient != null ? String(product.packing_coefficient) : '0.6',
    bulkDensity:
      product.bulk_density != null && product.bulk_density > 0
        ? String(product.bulk_density)
        : '',
  };
}

function buildProductPayload(form: ProductFormState): Record<string, unknown> {
  const isWeight = form.saleUnit === 'weight';
  return {
    name: form.name.trim(),
    sku: form.sku.trim(),
    gtin: form.gtin.trim() || null,
    category: Number(form.categoryId),
    price: form.price,
    width: Number(form.width),
    height: Number(form.height),
    depth: Number(form.depth),
    weight: Number(form.weight),
    is_marked: isWeight ? false : form.is_marked,
    is_stackable: form.is_stackable,
    allowed_equipment_types: isWeight ? ['box'] : form.allowedEquipmentTypes,
    shelf_life_days: form.shelfLifeDays.trim()
      ? Math.max(1, Math.floor(Number(form.shelfLifeDays) || 0))
      : null,
    sale_unit: form.saleUnit,
    packing_coefficient: Number(form.packingCoefficient) || 0.6,
  };
}

export function ProductCatalogPage(): React.ReactElement {
  const [products, setProducts] = useState<ProductRow[]>([]);
  const [categories, setCategories] = useState<CategoryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [form, setForm] = useState<ProductFormState>(emptyForm);
  const [editingProductId, setEditingProductId] = useState<number | null>(null);
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
    if (editingProductId !== null || form.categoryId || categories.length === 0) {
      return;
    }
    setForm((f) => ({ ...f, categoryId: String(categories[0]?.id ?? '') }));
  }, [categories, form.categoryId, editingProductId]);

  const resetProductForm = (categoryId?: string): void => {
    setEditingProductId(null);
    setForm({
      ...emptyForm,
      categoryId: categoryId ?? String(categories[0]?.id ?? ''),
    });
  };

  const cancelEdit = (): void => {
    resetProductForm(form.categoryId);
    setSuccess(null);
  };

  const startEdit = (product: ProductRow): void => {
    setEditingProductId(product.id);
    setForm(productToForm(product));
    setError(null);
    setSuccess(null);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const deleteProduct = async (product: ProductRow): Promise<void> => {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const { data } = await api.get<{
        can_delete: boolean;
        blockers: string[];
        warnings: string[];
      }>(`/products/${product.id}/delete-info/`);

      if (!data.can_delete) {
        setError(
          data.blockers.length
            ? `Нельзя удалить: есть ${data.blockers.join(', ')}.`
            : 'Нельзя удалить этот товар.',
        );
        return;
      }

      let confirmMessage = `Удалить товар «${product.name}» (SKU: ${product.sku})? Действие необратимо.`;
      if (data.warnings.length > 0) {
        confirmMessage = `${data.warnings.join('\n\n')}\n\n${confirmMessage}`;
      }
      if (!window.confirm(confirmMessage)) {
        return;
      }

      await api.delete(`/products/${product.id}/`);
      setSuccess(`Товар «${product.name}» удалён.`);
      if (editingProductId === product.id) {
        resetProductForm(form.categoryId);
      }
      await load();
    } catch (err) {
      setError(parseApiError(err, 'Не удалось удалить товар.'));
    } finally {
      setSaving(false);
    }
  };

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
      setError(parseApiError(err, 'Не удалось создать категорию.'));
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
    const payload = buildProductPayload(form);
    try {
      if (editingProductId === null) {
        await api.post('/products/', payload);
        setSuccess(`Товар «${form.name.trim()}» зарегистрирован. Следующий шаг — приёмка на склад.`);
        resetProductForm(form.categoryId);
      } else {
        await api.patch(`/products/${editingProductId}/`, payload);
        setSuccess(`Товар «${form.name.trim()}» обновлён.`);
        resetProductForm(form.categoryId);
      }
      await load();
    } catch (err) {
      setError(
        parseApiError(
          err,
          editingProductId === null
            ? 'Не удалось зарегистрировать товар.'
            : 'Не удалось сохранить изменения.',
        ),
      );
    } finally {
      setSaving(false);
    }
  };

  const isEditing = editingProductId !== null;
  const editingProduct = products.find((p) => p.id === editingProductId);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-white">Номенклатура</h2>
        <p className="mt-1 text-sm text-slate-400">
          Шаг 1 жизненного цикла: регистрация и правка карточки товара (SKU, габариты для расчёта
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
          className={`rounded-xl border p-4 ${
            isEditing
              ? 'border-violet-500/50 bg-violet-950/20'
              : 'border-slate-800 bg-slate-900/60'
          }`}
        >
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
            {isEditing ? (
              <>
                <Pencil className="h-4 w-4 text-violet-400" />
                Редактирование: {editingProduct?.name ?? form.name}
              </>
            ) : (
              <>
                <Plus className="h-4 w-4 text-violet-400" />
                Добавить товар
              </>
            )}
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
              {form.saleUnit === 'weight' ? 'Цена, ₽/кг' : 'Цена, ₽'}
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
            <label className="text-sm text-slate-300">
              Срок годности, дней
              <input
                type="number"
                min="1"
                step="1"
                placeholder="Не контролируется"
                value={form.shelfLifeDays}
                onChange={(e) => setForm({ ...form, shelfLifeDays: e.target.value })}
                className="mt-1 w-full rounded-md border border-slate-600 bg-slate-950 px-3 py-2"
              />
            </label>
          </div>
          <div className="mt-3 flex flex-wrap gap-4 text-sm text-slate-300">
            <span className="font-medium text-slate-200">Единица продажи:</span>
            <label className="flex items-center gap-2">
              <input
                type="radio"
                name="saleUnit"
                checked={form.saleUnit === 'piece'}
                onChange={() =>
                  setForm((prev) => ({
                    ...prev,
                    saleUnit: 'piece',
                  }))
                }
              />
              Штучный
            </label>
            <label className="flex items-center gap-2">
              <input
                type="radio"
                name="saleUnit"
                checked={form.saleUnit === 'weight'}
                onChange={() =>
                  setForm((prev) => ({
                    ...prev,
                    saleUnit: 'weight',
                    is_marked: false,
                    allowedEquipmentTypes: ['box'],
                  }))
                }
              />
              На развес (корзина)
            </label>
          </div>
          <p className="mt-2 text-xs text-slate-500">
            {form.saleUnit === 'weight'
              ? 'Весовой товар учитывается в граммах: приёмка и выкладка — в килограммах. Только оборудование «корзина».'
              : 'Срок в днях от даты производства — при приёмке указывается только дата выпуска. Для одежды и товаров без контроля срока оставьте поле пустым.'}
          </p>
          {form.saleUnit === 'piece' ? (
            <p className="mt-3 text-xs text-slate-500">
              Габариты в мм — для расчёта max_capacity на слоте (3D-укладка). Для сложенной
              одежды на полке снимите «Можно штабелировать» и задайте размеры пачки, например
              300×50×250 (Ш×В×Г).
            </p>
          ) : null}
          {form.saleUnit === 'weight' ? (
            <p className="mt-3 text-xs text-slate-500">
              Габариты — средний условный куб одной единицы (мм). Насыпная плотность в корзине
              ≈ (вес / объём) × 0.55, пересчитывается автоматически при сохранении.
            </p>
          ) : null}
          <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {(['width', 'height', 'depth', 'weight'] as const).map((key) => (
              <label key={key} className="text-xs text-slate-300">
                {key === 'width'
                  ? 'Ширина'
                  : key === 'height'
                    ? 'Высота'
                    : key === 'depth'
                      ? 'Глубина'
                      : form.saleUnit === 'weight'
                        ? 'Вес единицы (г)'
                        : 'Вес упак.'}
                <input
                  required={form.saleUnit === 'piece' || key === 'weight'}
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
          {form.saleUnit === 'weight' ? (
            <p className="mt-3 text-xs text-slate-400">
              Насыпная плотность (расчёт):{' '}
              {previewBulkDensityKgM3(form) != null
                ? `${previewBulkDensityKgM3(form)} кг/м³`
                : editingProductId != null && form.bulkDensity
                  ? `${form.bulkDensity} кг/м³`
                  : '—'}
            </p>
          ) : (
            <label className="mt-3 block text-xs text-slate-300">
              Коэффициент укладки (0.1–1.0, для навала в корзине)
              <input
                type="number"
                min="0.1"
                max="1"
                step="0.05"
                value={form.packingCoefficient}
                onChange={(e) => setForm({ ...form, packingCoefficient: e.target.value })}
                className="mt-1 w-full max-w-xs rounded-md border border-slate-600 bg-slate-950 px-2 py-1.5"
              />
            </label>
          )}
          {form.saleUnit === 'piece' ? (
          <>
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
          </>
          ) : null}
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="submit"
              disabled={saving}
              className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-violet-600 py-2.5 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-50"
            >
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {isEditing ? 'Сохранить изменения' : 'Зарегистрировать товар'}
            </button>
            {isEditing ? (
              <button
                type="button"
                disabled={saving}
                onClick={cancelEdit}
                className="rounded-lg border border-slate-600 px-4 py-2.5 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-50"
              >
                Отмена
              </button>
            ) : null}
          </div>
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
            для оприходования партии (дата производства или без дат — по карточке товара).
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
                  <th className="px-2 py-2">Ед.</th>
                  <th className="px-2 py-2">Цена</th>
                  <th className="px-2 py-2">Ш×В×Г, мм</th>
                  <th className="px-2 py-2">Срок, дн.</th>
                  <th className="px-2 py-2">Оборудование</th>
                  <th className="px-2 py-2">Действия</th>
                </tr>
              </thead>
              <tbody>
                {products.map((p) => (
                  <tr
                    key={p.id}
                    className={`border-t border-slate-800 text-slate-200 ${
                      editingProductId === p.id ? 'bg-violet-950/30' : ''
                    }`}
                  >
                    <td className="px-2 py-2 font-medium">{p.name}</td>
                    <td className="px-2 py-2">{p.sku}</td>
                    <td className="px-2 py-2">{p.category.name}</td>
                    <td className="px-2 py-2 text-slate-400">
                      {p.sale_unit === 'weight' ? 'кг' : 'шт.'}
                    </td>
                    <td className="px-2 py-2">
                      {p.price}
                      {p.sale_unit === 'weight' ? ' /кг' : ''}
                    </td>
                    <td className="px-2 py-2 text-slate-400">
                      {p.width}×{p.height}×{p.depth}
                    </td>
                    <td className="px-2 py-2 text-slate-400">
                      {p.shelf_life_days != null && p.shelf_life_days > 0
                        ? `${p.shelf_life_days} дн.`
                        : '—'}
                    </td>
                    <td className="px-2 py-2 text-slate-400">
                      {formatAllowedEquipmentTypes(p.allowed_equipment_types)}
                    </td>
                    <td className="px-2 py-2">
                      <div className="flex flex-wrap gap-1">
                        <button
                          type="button"
                          disabled={saving}
                          onClick={() => startEdit(p)}
                          className="inline-flex items-center gap-1 rounded-md border border-slate-600 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800 disabled:opacity-50"
                        >
                          <Pencil className="h-3 w-3" />
                          Изменить
                        </button>
                        <button
                          type="button"
                          disabled={saving}
                          onClick={() => void deleteProduct(p)}
                          className="inline-flex items-center gap-1 rounded-md border border-rose-500/50 px-2 py-1 text-xs text-rose-100 hover:bg-rose-950/40 disabled:opacity-50"
                        >
                          <Trash2 className="h-3 w-3" />
                          Удалить
                        </button>
                      </div>
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
