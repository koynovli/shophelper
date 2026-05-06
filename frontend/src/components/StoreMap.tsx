import React, { useEffect, useMemo, useState } from 'react';
import {
  MapPinned,
  Minus,
  Pencil,
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

/** Пикселей на 1 см координат из БД */
const PX_PER_CM = 10;

/** Шаг сетки на карте: 1 м = 100 см → 100 * PX_PER_CM пикселей */
const GRID_STEP_PX = 100 * PX_PER_CM;

const MIN_LABEL_WIDTH_PX = 72;
const MIN_LABEL_HEIGHT_PX = 28;

type WheelConfig = {
  step?: number;
  smoothStep?: number;
  disabled?: boolean;
};

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
  const [dimensions, setDimensions] = useState({ width: 20, height: 15 });
  const [editMode, setEditMode] = useState(false);

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

  const mapWidthPx = dimensions.width * 100 * PX_PER_CM;
  const mapHeightPx = dimensions.height * 100 * PX_PER_CM;

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

  const gridStyle = useMemo(
    (): React.CSSProperties => ({
      backgroundColor: '#0f172a',
      backgroundImage: `
        linear-gradient(to right, rgba(148, 163, 184, 0.22) 1px, transparent 1px),
        linear-gradient(to bottom, rgba(148, 163, 184, 0.22) 1px, transparent 1px),
        radial-gradient(circle at 0 0, rgba(56, 189, 248, 0.05), transparent 50%)
      `,
      backgroundSize: `${GRID_STEP_PX}px ${GRID_STEP_PX}px, ${GRID_STEP_PX}px ${GRID_STEP_PX}px, 100% 100%`,
      boxShadow:
        'inset 0 1px 0 rgba(255,255,255,0.04), 0 24px 48px rgba(0,0,0,0.45)',
    }),
    [],
  );

  const handleMapClick = (event: React.MouseEvent<HTMLDivElement>): void => {
    if (!editMode) {
      return;
    }
    const mapEl = event.currentTarget;
    const rect = mapEl.getBoundingClientRect();
    const offsetX = ((event.clientX - rect.left) / rect.width) * mapWidthPx;
    const offsetY = ((event.clientY - rect.top) / rect.height) * mapHeightPx;
    const x_cm = Math.round(offsetX / PX_PER_CM);
    const y_cm = Math.round(offsetY / PX_PER_CM);
    console.log('Клик в координатах (см):', x_cm, y_cm);
  };

  if (loading) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-slate-900 p-10 text-center text-slate-300 shadow-2xl">
        Loading...
      </div>
    );
  }

  return (
    <section className="flex min-h-0 w-full flex-col gap-3">
      {/* Панель администрирования */}
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-700/80 bg-slate-900/90 px-3 py-2 text-sm text-slate-300 shadow-lg backdrop-blur-sm">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Admin
        </span>
        <label className="flex items-center gap-2">
          <span className="text-slate-400">Ширина (м)</span>
          <input
            type="number"
            min={1}
            step={0.5}
            value={dimensions.width}
            onChange={(e) =>
              setDimensions((d) => ({
                ...d,
                width: Math.max(1, Number(e.target.value) || 1),
              }))
            }
            className="w-20 rounded-md border border-slate-600 bg-slate-950 px-2 py-1 text-slate-100 outline-none focus:border-emerald-500"
          />
        </label>
        <label className="flex items-center gap-2">
          <span className="text-slate-400">Длина (м)</span>
          <input
            type="number"
            min={1}
            step={0.5}
            value={dimensions.height}
            onChange={(e) =>
              setDimensions((d) => ({
                ...d,
                height: Math.max(1, Number(e.target.value) || 1),
              }))
            }
            className="w-20 rounded-md border border-slate-600 bg-slate-950 px-2 py-1 text-slate-100 outline-none focus:border-emerald-500"
          />
        </label>
        <button
          type="button"
          onClick={() => setEditMode((v) => !v)}
          className={`inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
            editMode
              ? 'border-amber-500/60 bg-amber-500/15 text-amber-200'
              : 'border-slate-600 bg-slate-800 text-slate-300 hover:border-slate-500'
          }`}
        >
          <Pencil className="h-3.5 w-3.5" />
          Режим редактирования
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
        <span className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900 px-3 py-1">
          <MapPinned className="h-3.5 w-3.5 text-emerald-300" />
          Digital Twin
        </span>
        <span className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900 px-3 py-1">
          <Ruler className="h-3.5 w-3.5 text-indigo-300" />
          {dimensions.width}×{dimensions.height} м · {PX_PER_CM} px/см · сетка 1 м ={' '}
          {GRID_STEP_PX}px
        </span>
        <span className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900 px-3 py-1">
          <Warehouse className="h-3.5 w-3.5 text-amber-300" />
          Объектов: {allEquipment.length}
        </span>
      </div>

      <div className="relative min-h-[calc(100dvh-280px)] w-full flex-1 overflow-hidden rounded-2xl border border-slate-800 bg-slate-950 shadow-2xl">
        <TransformWrapper
          key={`${dimensions.width}-${dimensions.height}-${mapWidthPx}-${mapHeightPx}`}
          initialScale={0.05}
          minScale={0.01}
          maxScale={2}
          limitToBounds={true}
          centerOnInit={true}
          wheel={
            {
              step: 0.05,
              smoothStep: 0.005,
            } as WheelConfig
          }
          doubleClick={{ disabled: true }}
        >
          <>
            <MapZoomToolbar />
            <TransformComponent
              wrapperClass="!h-full !w-full !max-h-full !max-w-full"
              wrapperStyle={{ width: '100%', height: '100%' }}
              contentClass="!flex !h-full !w-full !items-center !justify-center !shadow-none"
            >
              <div
                role={editMode ? 'presentation' : undefined}
                className={`relative shrink-0 rounded-lg ring-1 ring-slate-600/70 ${editMode ? 'cursor-crosshair' : ''}`}
                style={{
                  width: mapWidthPx,
                  height: mapHeightPx,
                  ...gridStyle,
                }}
                onClick={handleMapClick}
              >
                {zones.map((zone) =>
                  zone.equipment.map((eq) => {
                    const left = eq.pos_x * PX_PER_CM;
                    const top = eq.pos_y * PX_PER_CM;
                    const pixelWidth = Math.max(eq.width * PX_PER_CM, 8);
                    const pixelHeight = Math.max(eq.height * PX_PER_CM, 8);
                    const zoneColor = normalizeColor(zone.color);
                    const showInlineLabel =
                      pixelWidth >= MIN_LABEL_WIDTH_PX &&
                      pixelHeight >= MIN_LABEL_HEIGHT_PX;

                    return (
                      <button
                        key={eq.id}
                        type="button"
                        data-equipment
                        title={eq.name}
                        className={`group absolute overflow-hidden rounded-lg text-left outline-none ring-1 ring-white/10 transition hover:ring-emerald-400/70 hover:brightness-110 focus-visible:ring-2 focus-visible:ring-emerald-400 ${editMode ? 'pointer-events-none' : ''}`}
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
                        onClick={(e) => {
                          e.stopPropagation();
                          if (!editMode) {
                            console.log(
                              `Полки стеллажа "${eq.name}"`,
                              eq.shelves ?? [],
                            );
                          }
                        }}
                      >
                        <span
                          className="pointer-events-none absolute inset-0 opacity-[0.22]"
                          style={{
                            background: `linear-gradient(180deg, ${withAlpha(zoneColor, 0.9)} 0%, transparent 55%)`,
                          }}
                        />

                        <span className="pointer-events-none absolute left-1 top-1 z-10 rounded bg-black/55 px-1 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-slate-100 shadow-sm backdrop-blur-[2px]">
                          {eq.type}
                        </span>

                        {showInlineLabel ? (
                          <span className="pointer-events-none absolute inset-x-1 bottom-1 top-auto z-10 truncate text-center text-[10px] font-semibold leading-tight text-white drop-shadow-[0_1px_2px_rgba(0,0,0,0.85)]">
                            {eq.name}
                          </span>
                        ) : null}

                        <span
                          className={`pointer-events-none absolute left-1/2 z-20 max-w-[min(280px,calc(100vw-4rem))] -translate-x-1/2 whitespace-normal rounded-md border border-slate-600/90 bg-slate-950/95 px-2 py-1 text-left text-[10px] leading-snug text-slate-100 shadow-2xl backdrop-blur-sm transition-opacity duration-150 sm:whitespace-nowrap ${
                            showInlineLabel
                              ? 'bottom-full mb-1 opacity-0 group-hover:opacity-100'
                              : '-top-7 opacity-0 group-hover:opacity-100'
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

        <div className="pointer-events-none absolute bottom-3 left-4 z-20 max-w-[min(100%,24rem)] rounded-lg border border-slate-700/80 bg-slate-950/85 px-3 py-2 text-[11px] text-slate-400 backdrop-blur-sm">
          Колёсико — зум · перетаскивание — панорама
          {editMode ? (
            <span className="mt-1 block text-amber-200/90">
              Редактирование: клик по карте → координаты в консоли (см)
            </span>
          ) : null}
        </div>
      </div>
    </section>
  );
}

export default StoreMap;
