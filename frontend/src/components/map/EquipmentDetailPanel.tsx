import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Loader2, X } from 'lucide-react';

import api from '../../api';
import {
  EQUIPMENT_TYPE_SHORT_LABELS,
  getLayoutMode,
  slotRowLabel,
} from '../../map/equipmentProfiles';
import type { EquipmentSlot, FloorEquipment } from '../../types/floorPlan';
import { normalizeEquipmentType, slotFillMetrics } from '../../types/floorPlan';

type ProductBrief = { id: number; name: string; sku: string };

type MerchTaskRow = {
  id: number;
  quantity: number;
  status: string;
  product: { id: number; name: string; sku: string };
};

type Props = {
  open: boolean;
  equipment: FloorEquipment | null;
  equipmentName: string;
  slotsSorted: EquipmentSlot[];
  selectedSlotId: number | null;
  onSelectSlot: (id: number) => void;
  onClose: () => void;
  merchLoading: boolean;
  merchSaving: boolean;
  merchFeedback: { type: 'ok' | 'err'; text: string } | null;
  merchTasks: MerchTaskRow[];
  merchProducts: ProductBrief[];
  merchProductId: string;
  onMerchProductIdChange: (id: string) => void;
  merchTargetQty: number;
  onMerchTargetQtyChange: (qty: number) => void;
  merchSlotCapacity: number | null;
  onAutoCalculateTarget: () => void;
  onSavePlanogram: () => void;
  onSimulateSale: () => void;
  onDeletePlanogram: () => void;
  readOnly?: boolean;
  highlightTaskId?: number | string | null;
  focusedSlotId?: number | null;
};

export function EquipmentDetailPanel({
  open,
  equipment,
  equipmentName,
  slotsSorted,
  selectedSlotId,
  onSelectSlot,
  onClose,
  merchLoading,
  merchSaving,
  merchFeedback,
  merchTasks,
  merchProducts,
  merchProductId,
  onMerchProductIdChange,
  merchTargetQty,
  onMerchTargetQtyChange,
  merchSlotCapacity,
  onAutoCalculateTarget,
  onSavePlanogram,
  onSimulateSale,
  onDeletePlanogram,
  readOnly = false,
  highlightTaskId = null,
  focusedSlotId = null,
}: Props): React.ReactElement | null {
  const selectedSlot = slotsSorted.find((s) => s.id === selectedSlotId) ?? null;
  const [qrUrl, setQrUrl] = useState<string | null>(null);

  const eqType = equipment ? normalizeEquipmentType(String(equipment.type)) : 'shelf';
  const layoutMode = equipment ? getLayoutMode(String(equipment.type)) : 'grid';
  const isMannequin = eqType === 'mannequin';

  const rowGroups = useMemo(() => {
    const rows = new Map<number, EquipmentSlot[]>();
    for (const slot of slotsSorted) {
      const list = rows.get(slot.row_index) ?? [];
      list.push(slot);
      rows.set(slot.row_index, list);
    }
    return Array.from(rows.entries()).sort(([a], [b]) => a - b);
  }, [slotsSorted]);

  useEffect(() => {
    if (!selectedSlotId || !open || readOnly) {
      setQrUrl(null);
      return;
    }
    let cancelled = false;
    void api
      .get<{ qr_token?: string }>(`/slots/${selectedSlotId}/qr/`)
      .then((res) => {
        if (!cancelled) {
          setQrUrl(res.data.qr_token ?? null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setQrUrl(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selectedSlotId, open, readOnly]);

  if (!open || !equipment) {
    return null;
  }

  const equipmentTypeLabel = EQUIPMENT_TYPE_SHORT_LABELS[eqType] ?? eqType;

  return (
    <aside className="fixed right-0 top-0 z-40 flex h-full w-full max-w-md flex-col border-l border-slate-700 bg-slate-900 shadow-2xl">
      <div className="flex items-start justify-between gap-2 border-b border-slate-700 px-4 py-3">
        <div>
          <h3 className="text-base font-semibold text-slate-100">Оборудование</h3>
          <p className="text-sm text-slate-400">{equipmentName}</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg border border-slate-600 p-2 text-slate-300 hover:bg-slate-800"
          aria-label="Закрыть"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        {merchFeedback ? (
          <p
            className={`mb-3 rounded-md border px-3 py-2 text-xs ${
              merchFeedback.type === 'ok'
                ? 'border-emerald-600/50 bg-emerald-950/40 text-emerald-100'
                : 'border-amber-600/50 bg-amber-950/30 text-amber-100'
            }`}
          >
            {merchFeedback.text}
          </p>
        ) : null}

        <h4 className="mb-2 text-sm font-semibold text-slate-200">Матрица слотов</h4>
        {merchLoading ? (
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            Загрузка…
          </div>
        ) : (
          <div className="space-y-2">
            {rowGroups.map(([rowIndex, rowSlots]) => {
              const headerLabel = slotRowLabel(
                eqType,
                rowIndex,
                rowSlots[0]?.slot_label,
              );
              return (
                <div
                  key={rowIndex}
                  className="rounded-lg border border-slate-700 bg-slate-950/50 p-2"
                >
                  <p className="mb-2 text-[11px] uppercase tracking-wide text-slate-500">
                    {headerLabel}
                  </p>
                  <div
                    className={`flex min-h-[56px] gap-2 ${
                      layoutMode === 'grid' ? 'flex-wrap' : 'flex-col'
                    }`}
                  >
                    {rowSlots
                      .sort((a, b) => a.col_index - b.col_index)
                      .map((slot) => {
                        const isActive = slot.id === selectedSlotId;
                        const isFocused = slot.id === focusedSlotId;
                        const fill = slotFillMetrics(slot);
                        const replStatus = slot.planogram?.replenishment_status;
                        const statusClass =
                          fill.below30 || replStatus === 'DEFICIT'
                            ? 'border-rose-500/70 bg-rose-900/30'
                            : replStatus === 'IN_PROGRESS' || slot.active_placement_task
                              ? 'border-amber-500/70 bg-amber-900/25'
                              : fill.above70
                                ? 'border-emerald-600/60 bg-emerald-900/25'
                                : 'border-slate-600 bg-slate-800/70';
                        return (
                          <button
                            key={slot.id}
                            type="button"
                            onClick={() => onSelectSlot(slot.id)}
                            style={
                              layoutMode === 'grid'
                                ? { flex: `0 0 ${slot.width_percent}%` }
                                : { width: '100%' }
                            }
                            className={`min-h-[56px] rounded-md border px-2 py-1 text-left text-xs ${statusClass} ${
                              isFocused
                                ? 'ring-2 ring-violet-400 animate-pulse'
                                : isActive
                                  ? 'ring-2 ring-sky-400/80'
                                  : ''
                            }`}
                          >
                            {slot.planogram ? (
                              <>
                                <div className="truncate font-semibold">
                                  {slot.planogram.product.name}
                                </div>
                                <div className="text-[10px] text-sky-100">
                                  {fill.current}/{fill.cap || '—'}
                                </div>
                              </>
                            ) : (
                              <span className="text-slate-400">{readOnly ? 'Пусто' : '+ товар'}</span>
                            )}
                          </button>
                        );
                      })}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {selectedSlot ? (
          <div className="mt-4 rounded-lg border border-slate-700 bg-slate-950/50 p-3">
            <h5 className="text-sm font-semibold text-slate-200">
              {slotRowLabel(eqType, selectedSlot.row_index, selectedSlot.slot_label)}
              {layoutMode === 'grid'
                ? ` · ячейка ${selectedSlot.col_index}`
                : null}
            </h5>
            {readOnly ? (
              selectedSlot.planogram ? (
                <div className="mt-3 space-y-1 text-sm text-slate-300">
                  <p>
                    <span className="text-slate-500">Товар: </span>
                    {selectedSlot.planogram.product.name}
                  </p>
                  <p>
                    <span className="text-slate-500">Остаток: </span>
                    {slotFillMetrics(selectedSlot).current}/
                    {slotFillMetrics(selectedSlot).cap || '—'}
                  </p>
                </div>
              ) : (
                <p className="mt-3 text-sm text-slate-500">Слот без планограммы.</p>
              )
            ) : (
              <>
                {qrUrl ? (
                  <p className="mt-2 break-all font-mono text-[10px] text-slate-500">
                    QR-токен: {qrUrl}
                  </p>
                ) : null}
                {merchProducts.length === 0 ? (
                  <p className="mt-3 rounded-md border border-amber-600/40 bg-amber-950/20 px-3 py-2 text-xs text-amber-100">
                    Нет товаров для типа «{equipmentTypeLabel}» — настройте допустимые типы в
                    номенклатуре.
                  </p>
                ) : null}
                <div className="mt-3 flex flex-col gap-2">
                  <label className="text-sm text-slate-300">
                    Товар
                    <select
                      value={merchProductId}
                      onChange={(e) => onMerchProductIdChange(e.target.value)}
                      disabled={merchLoading || merchProducts.length === 0}
                      className="mt-1 w-full rounded-md border border-slate-600 bg-slate-900 px-2 py-2 text-white"
                    >
                      {merchProducts.map((p) => (
                        <option key={p.id} value={String(p.id)}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="flex flex-wrap items-end gap-2">
                    <label className="min-w-[8rem] flex-1 text-sm text-slate-300">
                      Цель, шт.
                      <input
                        type="number"
                        min={1}
                        max={isMannequin ? 1 : undefined}
                        value={merchTargetQty}
                        onChange={(e) =>
                          onMerchTargetQtyChange(
                            Math.max(1, isMannequin ? 1 : Number(e.target.value) || 1),
                          )
                        }
                        disabled={isMannequin}
                        className="mt-1 w-full rounded-md border border-slate-600 bg-slate-900 px-2 py-2 text-white disabled:opacity-60"
                      />
                    </label>
                    <button
                      type="button"
                      disabled={
                        merchSaving || merchLoading || !merchProductId || merchProducts.length === 0
                      }
                      onClick={onAutoCalculateTarget}
                      className="rounded-md border border-sky-500/60 px-3 py-2 text-xs text-sky-100 disabled:opacity-50"
                    >
                      Авторассчёт
                    </button>
                  </div>
                  <p className="text-[11px] text-slate-500">
                    Вместимость слота:{' '}
                    {merchSlotCapacity != null && merchSlotCapacity > 0 ? merchSlotCapacity : '—'}
                  </p>
                  {isMannequin ? (
                    <p className="text-[11px] text-slate-500">На зону экспозиции — максимум 1 ед.</p>
                  ) : null}
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={merchSaving || !merchProductId || merchProducts.length === 0}
                    onClick={onSavePlanogram}
                    className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs text-white disabled:opacity-50"
                  >
                    Сохранить
                  </button>
                  <button
                    type="button"
                    disabled={merchSaving || !selectedSlot.planogram}
                    onClick={onSimulateSale}
                    className="rounded-md border border-amber-500/60 px-3 py-1.5 text-xs text-amber-100 disabled:opacity-50"
                  >
                    Продажа −1
                  </button>
                  <button
                    type="button"
                    disabled={merchSaving || !selectedSlot.planogram}
                    onClick={onDeletePlanogram}
                    className="rounded-md border border-rose-500/60 px-3 py-1.5 text-xs text-rose-100 disabled:opacity-50"
                  >
                    Очистить
                  </button>
                  <Link
                    to="/admin?tab=catalog"
                    className="rounded-md border border-violet-500/50 px-3 py-1.5 text-xs text-violet-100"
                  >
                    Номенклатура
                  </Link>
                </div>
              </>
            )}
          </div>
        ) : null}

        <div className="mt-4">
          <h4 className="mb-2 text-sm font-semibold text-slate-200">Задачи выкладки</h4>
          {merchTasks.length === 0 ? (
            <p className="text-xs text-slate-500">Нет задач CREATED.</p>
          ) : (
            <ul className="space-y-1 text-xs text-slate-300">
              {merchTasks.map((t) => {
                const isHighlighted =
                  highlightTaskId != null && String(t.id) === String(highlightTaskId);
                return (
                <li
                  key={t.id}
                  className={`rounded border px-2 py-1 ${
                    isHighlighted
                      ? 'border-violet-500/70 bg-violet-900/40 ring-1 ring-violet-400/60'
                      : 'border-slate-700'
                  }`}
                >
                  {t.product.name}: {t.quantity} шт.
                  {isHighlighted ? (
                    <span className="ml-1 text-[10px] font-semibold uppercase text-violet-200">
                      ваша задача
                    </span>
                  ) : null}
                </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </aside>
  );
}
