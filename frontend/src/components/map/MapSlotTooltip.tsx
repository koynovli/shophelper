import React from 'react';

import type { EquipmentSlot } from '../../types/floorPlan';
import { slotFillMetrics } from '../../types/floorPlan';

type Props = {
  slot: EquipmentSlot | null;
  stageRect: DOMRect | null;
  pointerX: number;
  pointerY: number;
};

function formatExpiry(iso: string | null | undefined): string {
  if (!iso) {
    return '—';
  }
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) {
    return iso;
  }
  return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium' }).format(d);
}

export function MapSlotTooltip({
  slot,
  stageRect,
  pointerX,
  pointerY,
}: Props): React.ReactElement | null {
  if (!slot || !stageRect) {
    return null;
  }

  const fill = slotFillMetrics(slot);
  const productName = slot.planogram?.product.name ?? 'Слот без планограммы';
  const left = stageRect.left + pointerX + 12;
  const top = stageRect.top + pointerY + 12;

  return (
    <div
      className="pointer-events-none fixed z-[60] max-w-xs rounded-lg border border-slate-600 bg-slate-950/95 px-3 py-2 text-xs text-slate-100 shadow-xl"
      style={{ left, top }}
      role="tooltip"
    >
      <div className="font-semibold text-slate-50">{productName}</div>
      <div className="mt-1 text-slate-300">
        Остаток: {fill.current} / {fill.cap || '—'}
        {fill.percent !== null ? ` (${fill.percent}%)` : ''}
      </div>
      <div className="mt-1 text-sky-200">
        Срок годности ближайшей партии: {formatExpiry(slot.nearest_batch_expiry)}
      </div>
      {slot.active_placement_task ? (
        <div className="mt-1 text-amber-200">Активная задача на выкладку</div>
      ) : null}
    </div>
  );
}
