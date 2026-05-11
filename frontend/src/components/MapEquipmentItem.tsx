import React from 'react';

import type { FloorEquipment } from '../types/floorPlan';

type Props = {
  equipment: FloorEquipment;
  zoneColorHex: string;
  pxPerCm: number;
  /** Режим выделения и геометрического редактирования на карте */
  editMode: boolean;
  /** Режим мерчандайзинга: без перетаскивания, курсор pointer */
  layoutLocked: boolean;
  selected: boolean;
  dragging: boolean;
  collision: boolean;
  onPointerDown: (event: React.PointerEvent<HTMLButtonElement>) => void;
  onClick: (event: React.MouseEvent<HTMLButtonElement>) => void;
  onDoubleClick: (event: React.MouseEvent<HTMLButtonElement>) => void;
};

function withAlpha(hexColor: string, alpha: number): string {
  const color = hexColor.replace('#', '');
  const normalized =
    color.length === 3
      ? color
          .split('')
          .map((c) => `${c}${c}`)
          .join('')
      : color;
  const a = Math.max(0, Math.min(255, Math.round(alpha * 255)))
    .toString(16)
    .padStart(2, '0');
  return `#${normalized}${a}`;
}

function normalizeHex(value: string): string {
  if (!value) {
    return '#475569';
  }
  return /^#([A-Fa-f0-9]{3}|[A-Fa-f0-9]{6})$/.test(value) ? value : '#475569';
}

function TypeDecoration({ type }: { type: string }): React.ReactElement | null {
  const t = type === 'shelf' ? 'shelving' : type;

  if (t === 'pegboard') {
    return (
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.35]"
        style={{
          backgroundImage:
            'radial-gradient(circle, rgba(148,163,184,0.55) 1px, transparent 1px)',
          backgroundSize: '8px 8px',
        }}
      />
    );
  }

  if (t === 'fridge') {
    return (
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-sky-400/15 via-sky-500/10 to-slate-900/40" />
    );
  }

  if (t === 'pallet') {
    return (
      <div
        className="pointer-events-none absolute inset-0 opacity-40"
        style={{
          backgroundImage:
            'repeating-linear-gradient(90deg, rgba(180,83,9,0.6) 0 6px, transparent 6px 14px)',
        }}
      />
    );
  }

  if (t === 'display') {
    return (
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-white/18 via-indigo-400/10 to-transparent" />
    );
  }

  return null;
}

export function MapEquipmentItem({
  equipment,
  zoneColorHex,
  pxPerCm,
  editMode,
  layoutLocked,
  selected,
  dragging,
  collision,
  onPointerDown,
  onClick,
  onDoubleClick,
}: Props): React.ReactElement {
  const zoneColor = normalizeHex(zoneColorHex);
  const left = equipment.pos_x * pxPerCm;
  const top = equipment.pos_y * pxPerCm;
  const pixelWidth = Math.max(equipment.width * pxPerCm, 8);
  const pixelHeight = Math.max(equipment.height * pxPerCm, 8);

  const displayType = equipment.type === 'shelf' ? 'shelving' : equipment.type;
  const shelfLines =
    (displayType === 'shelving' || displayType === 'fridge' || displayType === 'pegboard') &&
    equipment.rows_count > 0
      ? equipment.rows_count
      : 0;

  let borderColor = withAlpha(zoneColor, 0.92);
  if (collision) {
    borderColor = '#f87171';
  } else if (dragging) {
    borderColor = '#34d399';
  } else if (selected && editMode && !layoutLocked) {
    borderColor = '#38bdf8';
  }

  const allowDrag = editMode && !layoutLocked;
  const ringClass =
    selected && editMode && !layoutLocked
      ? 'ring-2 ring-sky-400/90 ring-offset-1 ring-offset-slate-950'
      : 'ring-1 ring-white/10';

  const cursorClass = layoutLocked
    ? 'cursor-pointer'
    : allowDrag
      ? dragging
        ? 'cursor-grabbing'
        : 'cursor-grab'
      : '';

  return (
    <button
      type="button"
      data-equipment
      title={equipment.name}
      className={`group absolute overflow-hidden rounded-lg text-left outline-none hover:brightness-110 focus-visible:ring-2 focus-visible:ring-emerald-400 ${ringClass} ${cursorClass} ${
        collision ? 'ring-2 ring-red-500/90' : ''
      }`}
      style={{
        left: `${left}px`,
        top: `${top}px`,
        width: `${pixelWidth}px`,
        height: `${pixelHeight}px`,
        transform: `rotate(${equipment.rotation ?? 0}deg)`,
        transformOrigin: 'center center',
        borderWidth: 2,
        borderStyle: 'solid',
        borderColor,
        boxShadow: dragging
          ? `0 18px 42px rgba(16, 185, 129, 0.55), 0 6px 16px rgba(0,0,0,0.45),
            inset 0 1px 0 rgba(255, 255, 255, 0.14)`
          : collision
            ? `0 12px 28px rgba(248, 113, 113, 0.35), 0 2px 8px rgba(0,0,0,0.45),
              inset 0 1px 0 rgba(255,255,255,0.08)`
            : `0 10px 28px rgba(0, 0, 0, 0.55),
              0 2px 8px rgba(0, 0, 0, 0.35),
              inset 0 1px 0 rgba(255, 255, 255, 0.12)`,
        background: `
          linear-gradient(145deg,
            ${withAlpha(zoneColor, 0.55)} 0%,
            rgba(15, 23, 42, 0.92) 48%,
            ${withAlpha(zoneColor, 0.35)} 100%
          )
        `,
      }}
      onClick={onClick}
      onDoubleClick={onDoubleClick}
      onPointerDown={onPointerDown}
    >
      <span
        className="pointer-events-none absolute inset-0 opacity-[0.22]"
        style={{
          background: `linear-gradient(180deg, ${withAlpha(zoneColor, 0.9)} 0%, transparent 55%)`,
        }}
      />

      <TypeDecoration type={displayType} />

      {shelfLines > 0 ? (
        <div className="pointer-events-none absolute inset-1">
          {Array.from({ length: shelfLines }).map((_, idx) => (
            <div
              key={idx}
              className="absolute left-0 right-0 border-t border-white/25"
              style={{
                top: `${((idx + 1) / (shelfLines + 1)) * 100}%`,
              }}
            />
          ))}
        </div>
      ) : null}

      <span className="pointer-events-none absolute left-1 top-1 z-10 rounded bg-black/55 px-1 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-slate-100 shadow-sm backdrop-blur-[2px]">
        {displayType}
      </span>

      <span className="pointer-events-none absolute inset-x-1 bottom-1 top-auto z-10 truncate text-center text-[10px] font-semibold leading-tight text-white drop-shadow-[0_1px_2px_rgba(0,0,0,0.85)]">
        {equipment.name}
      </span>
      <span className="pointer-events-none absolute right-1 top-1 z-10 rounded bg-black/50 px-1 py-0.5 text-[9px] font-semibold text-slate-100">
        {Math.round(equipment.rotation ?? 0)}°
      </span>

      <span className="pointer-events-none absolute left-1/2 top-full z-20 mt-1 hidden max-w-[min(280px,calc(100vw-4rem))] -translate-x-1/2 whitespace-normal rounded-md border border-slate-600/90 bg-slate-950/95 px-2 py-1 text-left text-[10px] leading-snug text-slate-100 shadow-2xl backdrop-blur-sm group-hover:block sm:whitespace-nowrap">
        {equipment.name}
      </span>
    </button>
  );
}
