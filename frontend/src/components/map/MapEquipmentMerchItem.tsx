import React, { useMemo } from 'react';

import { computeSlotRects } from '../../map/slotLayout';
import { getEquipmentShapeStyle } from '../../map/equipmentShapeConfig';
import { getSlotVisualState } from '../../map/slotVisualState';
import type { EquipmentSlot, FloorEquipment } from '../../types/floorPlan';
import { normalizeEquipmentType, slotFillMetrics } from '../../types/floorPlan';

type Props = {
  equipment: FloorEquipment;
  zoneColorHex: string;
  pxPerCm: number;
  pendingSlotIds: Set<number>;
  focusedSlotId?: number | null;
  selected: boolean;
  selectedSlotId: number | null;
  onEquipmentClick: (equipment: FloorEquipment) => void;
  onSlotClick: (equipment: FloorEquipment, slot: EquipmentSlot) => void;
  onDoubleClick: (equipment: FloorEquipment) => void;
};

function slotTooltip(slot: EquipmentSlot): string {
  const fill = slotFillMetrics(slot);
  const name = slot.planogram?.product.name ?? 'Без планограммы';
  const expiry = slot.nearest_batch_expiry
    ? new Date(slot.nearest_batch_expiry).toLocaleDateString('ru-RU')
    : '—';
  return `${name}\nОстаток: ${fill.current}/${fill.cap || '—'}\nСрок годности: ${expiry}`;
}

function TypeDecoration({ type }: { type: string }): React.ReactElement | null {
  const t = normalizeEquipmentType(type);
  if (t === 'hanger') {
    return (
      <div className="pointer-events-none absolute inset-x-2 top-1/2 z-[1] h-0.5 -translate-y-1/2 bg-slate-300/70" />
    );
  }
  if (t === 'fridge') {
    return (
      <div className="pointer-events-none absolute inset-0 z-[1] rounded-lg shadow-[inset_0_0_12px_rgba(56,189,248,0.35)] ring-1 ring-sky-400/40" />
    );
  }
  if (t === 'box') {
    return (
      <div
        className="pointer-events-none absolute inset-0 z-[1] opacity-40"
        style={{
          backgroundImage:
            'repeating-linear-gradient(90deg, rgba(180,83,9,0.6) 0 6px, transparent 6px 14px)',
        }}
      />
    );
  }
  if (t === 'mannequin') {
    return (
      <div className="pointer-events-none absolute inset-0 z-[1] rounded-full bg-indigo-400/10" />
    );
  }
  return null;
}

export function MapEquipmentMerchItem({
  equipment,
  zoneColorHex,
  pxPerCm,
  pendingSlotIds,
  focusedSlotId = null,
  selected,
  selectedSlotId,
  onEquipmentClick,
  onSlotClick,
  onDoubleClick,
}: Props): React.ReactElement {
  const left = equipment.pos_x * pxPerCm;
  const top = equipment.pos_y * pxPerCm;
  const w = Math.max(equipment.width * pxPerCm, 8);
  const h = Math.max(equipment.height * pxPerCm, 8);
  const displayType = normalizeEquipmentType(String(equipment.type));
  const style = getEquipmentShapeStyle(displayType, zoneColorHex);
  const slots = equipment.slots ?? [];
  const layouts = useMemo(() => computeSlotRects(equipment, slots, w, h), [equipment, slots, w, h]);
  const slotById = useMemo(() => new Map(slots.map((s) => [s.id, s])), [slots]);
  const roundedClass = displayType === 'mannequin' ? 'rounded-full' : 'rounded-lg';

  return (
    <div
      role="button"
      tabIndex={0}
      title={equipment.name}
      className={`absolute cursor-pointer overflow-hidden outline-none hover:brightness-110 focus-visible:ring-2 focus-visible:ring-emerald-400 ${roundedClass} ring-1 ring-white/15 ${
        selected ? 'ring-2 ring-sky-400/90' : ''
      }`}
      style={{
        left: `${left}px`,
        top: `${top}px`,
        width: `${w}px`,
        height: `${h}px`,
        transform: `rotate(${equipment.rotation ?? 0}deg)`,
        transformOrigin: 'center center',
        borderWidth: 2,
        borderStyle: 'solid',
        borderColor: selected ? '#38bdf8' : style.bodyStroke,
        background: style.bodyFill,
        boxShadow: style.showFridgeGlow
          ? '0 0 14px rgba(14, 165, 233, 0.45)'
          : '0 4px 12px rgba(0,0,0,0.35)',
      }}
      onClick={(e) => {
        e.stopPropagation();
        onEquipmentClick(equipment);
      }}
      onDoubleClick={(e) => {
        e.stopPropagation();
        onDoubleClick(equipment);
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          onEquipmentClick(equipment);
        }
      }}
    >
      <TypeDecoration type={displayType} />
      {style.showFridgeGlow ? (
        <span className="pointer-events-none absolute right-1 top-1 z-[2] text-xs text-sky-300">
          ❄
        </span>
      ) : null}

      <div className="absolute inset-0 z-[3]">
        {layouts.map((layout) => {
          const slot = slotById.get(layout.slotId);
          if (!slot) {
            return null;
          }
          const visual = getSlotVisualState(slot, pendingSlotIds);
          const isSlotSelected = selectedSlotId === slot.id;
          const isFocused = focusedSlotId === slot.id;
          return (
            <button
              key={slot.id}
              type="button"
              title={slotTooltip(slot)}
              className={`absolute box-border rounded-sm border transition hover:brightness-110 ${
                visual.pulse && !isFocused ? 'animate-pulse' : ''
              } ${isFocused ? 'animate-pulse ring-4 ring-violet-400 ring-offset-1 ring-offset-slate-900' : ''} ${
                isSlotSelected && !isFocused ? 'ring-2 ring-sky-300' : ''
              }`}
              style={{
                left: `${layout.x}px`,
                top: `${layout.y}px`,
                width: `${layout.width}px`,
                height: `${layout.height}px`,
                backgroundColor: visual.fillHex,
                borderColor: visual.strokeHex,
              }}
              onClick={(e) => {
                e.stopPropagation();
                onSlotClick(equipment, slot);
              }}
            >
              {visual.showAlert && !isFocused ? (
                <span className="flex h-full w-full items-center justify-center text-[10px] font-bold text-amber-100">
                  !
                </span>
              ) : null}
              {isFocused ? (
                <span className="flex h-full w-full items-center justify-center text-[10px] font-bold text-violet-100">
                  →
                </span>
              ) : null}
            </button>
          );
        })}
      </div>

      <span className="pointer-events-none absolute inset-x-1 bottom-0.5 z-[4] truncate text-center text-[9px] font-semibold text-white drop-shadow-md">
        {equipment.name}
      </span>
    </div>
  );
}
