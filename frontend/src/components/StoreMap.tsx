import React, { useEffect, useMemo, useState } from 'react';
import {
  MapPinned,
  Minus,
  Plus,
  RotateCcw,
  Ruler,
  Warehouse,
} from 'lucide-react';
import {
  TransformComponent,
  TransformWrapper,
  useControls,
} from 'react-zoom-pan-pinch';

import api from '../api';

type Shelf = {
  id: number;
  level: number;
  width: number;
  height: number;
  depth: number;
};

type Equipment = {
  id: number;
  name: string;
  type: string;
  pos_x: number;
  pos_y: number;
  width: number;
  height: number;
  orientation: number;
  shelves: Shelf[];
};

type Zone = {
  id: number;
  name: string;
  color: string;
  equipment: Equipment[];
};

/** Координаты из БД — сантиметры; на экране 1 см = 1 px */
const CM_TO_PX = 1;

/** Клетка сетки: 100×100 px ↔ 100×100 см ↔ 1×1 м */
const GRID_CELL_PX = 100;

const PADDING = 48;

const MIN_LABEL_WIDTH_PX = 72;
const MIN_LABEL_HEIGHT_PX = 28;

const normalizeColor = (value: string): string => {
  if (!value) {
    return '#475569';
  }
  return /^#([A-Fa-f0-9]{3}|[A-Fa-f0-9]{6})$/.test(value) ? value : '#475569';
};

const withAlpha = (hexColor: string, alpha: number): string => {
  const color = normalizeColor(hexColor).replace('#', '');
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
};

function MapZoomToolbar() {
  const { zoomIn, zoomOut, resetTransform } = useControls();

  return (
    <div className="pointer-events-none absolute right-4 top-4 z-30 flex flex-col gap-2">
      <div className="pointer-events-auto flex flex-col overflow-hidden rounded-xl border border-slate-600/80 bg-slate-950/90 shadow-xl backdrop-blur-sm">
        <button
          type="button"
          onClick={() => zoomIn()}
          className="flex h-11 w-11 items-center justify-center border-b border-slate-700/80 text-slate-100 transition hover:bg-emerald-500/20 hover:text-emerald-200"
          title="Увеличить"
          aria-label="Увеличить масштаб"
        >
          <Plus className="h-5 w-5" strokeWidth={2.25} />
        </button>
        <button
          type="button"
          onClick={() => zoomOut()}
          className="flex h-11 w-11 items-center justify-center border-b border-slate-700/80 text-slate-100 transition hover:bg-emerald-500/20 hover:text-emerald-200"
          title="Уменьшить"
          aria-label="Уменьшить масштаб"
        >
          <Minus className="h-5 w-5" strokeWidth={2.25} />
        </button>
        <button
          type="button"
          onClick={() => resetTransform()}
          className="flex h-11 w-11 items-center justify-center text-slate-100 transition hover:bg-indigo-500/20 hover:text-indigo-200"
          title="Сбросить вид"
          aria-label="Сбросить масштаб и позицию"
        >
          <RotateCcw className="h-5 w-5" strokeWidth={2} />
        </button>
      </div>
    </div>
  );
}

function StoreMap() {
  const [zones, setZones] = useState<Zone[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    const fetchZones = async (): Promise<void> => {
      try {
        const response = await api.get('/zones/');
        const payload = Array.isArray(response.data)
          ? response.data
          : response.data.results ?? [];
        setZones(payload as Zone[]);
      } catch (error) {
        console.error('Не удалось загрузить карту зала:', error);
        setZones([]);
      } finally {
        setLoading(false);
      }
    };

    fetchZones();
  }, []);

  const allEquipment = useMemo(
    () =>
      zones.flatMap((zone) =>
        zone.equipment.map((eq) => ({
          ...eq,
          zoneName: zone.name,
          zoneColor: zone.color,
        })),
      ),
    [zones],
  );

  const bounds = useMemo(() => {
    if (allEquipment.length === 0) {
      return {
        minX: 0,
        minY: 0,
        width: Math.max(1000 + PADDING * 2, 900),
        height: Math.max(600 + PADDING * 2, 520),
      };
    }

    const minX = Math.min(
      ...allEquipment.map((eq) => eq.pos_x - eq.width / 2),
    );
    const maxX = Math.max(
      ...allEquipment.map((eq) => eq.pos_x + eq.width / 2),
    );
    const minY = Math.min(
      ...allEquipment.map((eq) => eq.pos_y - eq.height / 2),
    );
    const maxY = Math.max(
      ...allEquipment.map((eq) => eq.pos_y + eq.height / 2),
    );

    const spanX = maxX - minX;
    const spanY = maxY - minY;

    return {
      minX,
      minY,
      width: Math.max(spanX * CM_TO_PX + PADDING * 2, 900),
      height: Math.max(spanY * CM_TO_PX + PADDING * 2, 520),
    };
  }, [allEquipment]);

  const gridStyle = useMemo((): React.CSSProperties => {
    const phaseX =
      (((-bounds.minX * CM_TO_PX + PADDING) % GRID_CELL_PX) + GRID_CELL_PX) %
      GRID_CELL_PX;
    const phaseY =
      (((-bounds.minY * CM_TO_PX + PADDING) % GRID_CELL_PX) + GRID_CELL_PX) %
      GRID_CELL_PX;

    return {
      backgroundColor: '#0f172a',
      backgroundImage: `
        linear-gradient(to right, rgba(148, 163, 184, 0.14) 1px, transparent 1px),
        linear-gradient(to bottom, rgba(148, 163, 184, 0.14) 1px, transparent 1px),
        radial-gradient(circle at 0 0, rgba(56, 189, 248, 0.06), transparent 55%)
      `,
      backgroundSize: `${GRID_CELL_PX}px ${GRID_CELL_PX}px, ${GRID_CELL_PX}px ${GRID_CELL_PX}px, 100% 100%`,
      backgroundPosition: `${phaseX}px ${phaseY}px, ${phaseX}px ${phaseY}px, 0 0`,
    };
  }, [bounds.minX, bounds.minY]);

  if (loading) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-slate-900 p-10 text-center text-slate-300 shadow-2xl">
        Loading...
      </div>
    );
  }

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 text-sm text-slate-400">
        <span className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900 px-3 py-1.5">
          <MapPinned className="h-4 w-4 text-emerald-300" />
          Digital Twin
        </span>
        <span className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900 px-3 py-1.5">
          <Ruler className="h-4 w-4 text-indigo-300" />
          1 см в данных = 1 px · клетка {GRID_CELL_PX}×{GRID_CELL_PX} px = 1×1 м
        </span>
        <span className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900 px-3 py-1.5">
          <Warehouse className="h-4 w-4 text-amber-300" />
          Объектов: {allEquipment.length}
        </span>
      </div>

      <div className="relative h-[min(72vh,820px)] min-h-[440px] w-full overflow-hidden rounded-2xl border border-slate-800 bg-slate-950 shadow-2xl">
        <TransformWrapper
          initialScale={1}
          minScale={0.15}
          maxScale={8}
          limitToBounds={false}
          centerOnInit
          wheel={{
            step: 0.12,
          }}
          pinch={{
            step: 5,
          }}
          doubleClick={{ disabled: true }}
        >
          <>
            <MapZoomToolbar />
            <TransformComponent
              wrapperClass="!w-full !h-full !flex !items-center !justify-center"
              contentClass="!shadow-none"
            >
              <div
                className="relative rounded-xl ring-1 ring-slate-700/60"
                style={{
                  width: `${bounds.width}px`,
                  height: `${bounds.height}px`,
                  ...gridStyle,
                  boxShadow:
                    'inset 0 1px 0 rgba(255,255,255,0.04), 0 24px 48px rgba(0,0,0,0.45)',
                }}
              >
                {zones.map((zone) =>
                  zone.equipment.map((eq) => {
                    const left =
                      (eq.pos_x - eq.width / 2 - bounds.minX) * CM_TO_PX +
                      PADDING;
                    const top =
                      (eq.pos_y - eq.height / 2 - bounds.minY) * CM_TO_PX +
                      PADDING;
                    const pixelWidth = Math.max(eq.width * CM_TO_PX, 12);
                    const pixelHeight = Math.max(eq.height * CM_TO_PX, 12);
                    const zoneColor = normalizeColor(zone.color);
                    const showInlineLabel =
                      pixelWidth >= MIN_LABEL_WIDTH_PX &&
                      pixelHeight >= MIN_LABEL_HEIGHT_PX;

                    return (
                      <button
                        key={eq.id}
                        type="button"
                        title={eq.name}
                        className="group absolute overflow-hidden rounded-lg text-left outline-none ring-1 ring-white/10 transition hover:ring-emerald-400/70 hover:brightness-110 focus-visible:ring-2 focus-visible:ring-emerald-400"
                        style={{
                          left: `${left}px`,
                          top: `${top}px`,
                          width: `${pixelWidth}px`,
                          height: `${pixelHeight}px`,
                          transform: `rotate(${eq.orientation || 0}deg)`,
                          transformOrigin: 'center center',
                          borderWidth: 2,
                          borderStyle: 'solid',
                          borderColor: withAlpha(zoneColor, 0.92),
                          boxShadow: `
                            0 10px 28px rgba(0, 0, 0, 0.55),
                            0 2px 8px rgba(0, 0, 0, 0.35),
                            inset 0 1px 0 rgba(255, 255, 255, 0.12)
                          `,
                          background: `
                            linear-gradient(145deg,
                              ${withAlpha(zoneColor, 0.55)} 0%,
                              rgba(15, 23, 42, 0.92) 48%,
                              ${withAlpha(zoneColor, 0.35)} 100%
                            )
                          `,
                        }}
                        onClick={() => {
                          console.log(
                            `Полки стеллажа "${eq.name}"`,
                            eq.shelves ?? [],
                          );
                        }}
                      >
                        <span
                          className="pointer-events-none absolute inset-0 opacity-[0.22]"
                          style={{
                            background: `linear-gradient(180deg, ${withAlpha(zoneColor, 0.9)} 0%, transparent 55%)`,
                          }}
                        />

                        <span className="pointer-events-none absolute left-1.5 top-1.5 z-10 rounded bg-black/55 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-100 shadow-sm backdrop-blur-[2px]">
                          {eq.type}
                        </span>

                        {showInlineLabel ? (
                          <span className="pointer-events-none absolute inset-x-1.5 bottom-1.5 top-auto z-10 truncate text-center text-[11px] font-semibold leading-tight text-white drop-shadow-[0_1px_2px_rgba(0,0,0,0.85)]">
                            {eq.name}
                          </span>
                        ) : null}

                        <span
                          className={`pointer-events-none absolute left-1/2 z-20 max-w-[min(280px,calc(100vw-4rem))] -translate-x-1/2 whitespace-normal rounded-lg border border-slate-600/90 bg-slate-950/95 px-2.5 py-1.5 text-left text-xs leading-snug text-slate-100 shadow-2xl backdrop-blur-sm transition-opacity duration-150 sm:whitespace-nowrap ${
                            showInlineLabel
                              ? 'bottom-full mb-2 opacity-0 group-hover:opacity-100'
                              : '-top-9 opacity-0 group-hover:opacity-100'
                          }`}
                        >
                          {eq.name}
                        </span>
                      </button>
                    );
                  }),
                )}
              </div>
            </TransformComponent>
          </>
        </TransformWrapper>

        <div className="pointer-events-none absolute bottom-3 left-4 z-20 rounded-lg border border-slate-700/80 bg-slate-950/85 px-3 py-2 text-[11px] text-slate-400 backdrop-blur-sm">
          Колёсико мыши — масштаб · перетаскивание — панорама
        </div>
      </div>
    </section>
  );
}

export default StoreMap;
