import React, {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
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
import type { FloorEquipment, FloorEquipmentType, FloorZone } from '../types/floorPlan';
import { normalizeFloorEquipment } from '../types/floorPlan';
import {
  magneticSnapTopLeftPx,
  obbIntersectPx,
  snapCoordPx,
  snapRotationDeg,
  SNAP_GRID_PX,
} from '../utils/floorPlanGeometry';
import { MapEquipmentItem } from './MapEquipmentItem';

/** Пикселей на 1 см координат из БД (10 px = 1 см на карте) */
const PX_PER_CM = 10;

const MAGNETIC_THRESHOLD_PX = 5;
const CLONE_OFFSET_PX = 20;
const MAX_HISTORY = 50;

type WheelConfig = {
  step?: number;
  smoothStep?: number;
  disabled?: boolean;
};

type TransformWrapperExtras = {
  alignmentAnimation?: { size?: number };
};

function cloneZones(zones: FloorZone[]): FloorZone[] {
  return JSON.parse(JSON.stringify(zones)) as FloorZone[];
}

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
  const [zones, setZones] = useState<FloorZone[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [dimensions, setDimensions] = useState({ width: 20, height: 15 });
  const [editMode, setEditMode] = useState(false);
  const [draggingItem, setDraggingItem] = useState<number | null>(null);
  const [selectedEquipmentId, setSelectedEquipmentId] = useState<number | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newObjCoords, setNewObjCoords] = useState({ x: 0, y: 0 });
  const [newEquipmentForm, setNewEquipmentForm] = useState({
    name: '',
    widthCm: 120,
    lengthCm: 60,
    rotation: 0,
    type: 'shelving' as FloorEquipmentType,
    shelfCount: 4,
  });
  const [isSaving, setIsSaving] = useState(false);
  const [minScale, setMinScale] = useState(0.05);

  const viewportRef = useRef<HTMLDivElement>(null);
  const suppressNextMapClickRef = useRef(false);
  const zonesRef = useRef<FloorZone[]>([]);
  const undoStackRef = useRef<FloorZone[][]>([]);
  const redoStackRef = useRef<FloorZone[][]>([]);

  useEffect(() => {
    zonesRef.current = zones;
  }, [zones]);

  useEffect(() => {
    const fetchZones = async (): Promise<void> => {
      try {
        const response = await api.get('/zones/');
        const payload = Array.isArray(response.data)
          ? response.data
          : response.data.results ?? [];
        const normalized = (payload as Record<string, unknown>[]).map((z) => ({
          ...z,
          equipment: Array.isArray(z.equipment)
            ? (z.equipment as Record<string, unknown>[]).map((eq) =>
                normalizeFloorEquipment(eq),
              )
            : [],
        })) as FloorZone[];
        setZones(normalized);
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

  useLayoutEffect(() => {
    const el = viewportRef.current;
    if (!el || mapWidthPx <= 0 || mapHeightPx <= 0) {
      return;
    }

    const recalc = (): void => {
      const w = el.clientWidth;
      const h = el.clientHeight;
      if (w <= 0 || h <= 0) {
        return;
      }
      const scale = Math.min(w / mapWidthPx, h / mapHeightPx);
      const next = Math.min(Math.max(scale, 1e-5), 2);
      setMinScale(next);
    };

    recalc();
    const ro = new ResizeObserver(recalc);
    ro.observe(el);
    window.addEventListener('resize', recalc);
    return () => {
      ro.disconnect();
      window.removeEventListener('resize', recalc);
    };
  }, [mapWidthPx, mapHeightPx]);

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

  const equipmentLayoutsPx = useMemo(
    () =>
      allEquipment.map((eq) => ({
        id: eq.id,
        left: eq.pos_x * PX_PER_CM,
        top: eq.pos_y * PX_PER_CM,
        width: Math.max(eq.width * PX_PER_CM, 8),
        height: Math.max(eq.height * PX_PER_CM, 8),
        rotation: eq.rotation ?? 0,
      })),
    [allEquipment],
  );

  const collisionIds = useMemo(() => {
    const hit = new Set<number>();
    const layouts = equipmentLayoutsPx;
    for (let i = 0; i < layouts.length; i++) {
      for (let j = i + 1; j < layouts.length; j++) {
        const a = layouts[i];
        const b = layouts[j];
        if (
          obbIntersectPx(
            a.left,
            a.top,
            a.width,
            a.height,
            a.rotation,
            b.left,
            b.top,
            b.width,
            b.height,
            b.rotation,
          )
        ) {
          hit.add(a.id);
          hit.add(b.id);
        }
      }
    }
    return hit;
  }, [equipmentLayoutsPx]);

  const meterGridPx = 100 * PX_PER_CM;
  const defaultZoneId = zones[0]?.id ?? null;

  const pushUndoSnapshot = useCallback((): void => {
    undoStackRef.current.push(cloneZones(zonesRef.current));
    if (undoStackRef.current.length > MAX_HISTORY) {
      undoStackRef.current.shift();
    }
    redoStackRef.current = [];
  }, []);

  const undo = useCallback((): void => {
    setZones((current) => {
      const snap = undoStackRef.current.pop();
      if (!snap) {
        return current;
      }
      redoStackRef.current.push(cloneZones(current));
      return snap;
    });
  }, []);

  const redo = useCallback((): void => {
    setZones((current) => {
      const snap = redoStackRef.current.pop();
      if (!snap) {
        return current;
      }
      undoStackRef.current.push(cloneZones(current));
      return snap;
    });
  }, []);

  const gridStyle = useMemo(
    (): React.CSSProperties => ({
      backgroundColor: '#0f172a',
      backgroundImage: `
        linear-gradient(to right, rgba(148, 163, 184, 0.22) 1px, transparent 1px),
        linear-gradient(to bottom, rgba(148, 163, 184, 0.22) 1px, transparent 1px),
        radial-gradient(circle at 0 0, rgba(56, 189, 248, 0.05), transparent 50%)
      `,
      backgroundSize: `${meterGridPx}px ${meterGridPx}px, ${meterGridPx}px ${meterGridPx}px, 100% 100%`,
      boxShadow:
        'inset 0 1px 0 rgba(255,255,255,0.04), 0 24px 48px rgba(0,0,0,0.45)',
    }),
    [meterGridPx],
  );

  const clampEquipmentTopLeftCm = useCallback(
    (eq: FloorEquipment, xCm: number, yCm: number): { x: number; y: number } => {
      const maxX = Math.max(0, dimensions.width * 100 - eq.width);
      const maxY = Math.max(0, dimensions.height * 100 - eq.height);
      return {
        x: Math.min(Math.max(xCm, 0), maxX),
        y: Math.min(Math.max(yCm, 0), maxY),
      };
    },
    [dimensions.height, dimensions.width],
  );

  const updateEquipmentPositionInState = (
    equipmentId: number,
    posX: number,
    posY: number,
  ): void => {
    setZones((prevZones) =>
      prevZones.map((zone) => ({
        ...zone,
        equipment: zone.equipment.map((eq) =>
          eq.id === equipmentId ? { ...eq, pos_x: posX, pos_y: posY } : eq,
        ),
      })),
    );
  };

  const handleMapClick = (event: React.MouseEvent<HTMLDivElement>): void => {
    if (!editMode) {
      return;
    }
    if (suppressNextMapClickRef.current) {
      suppressNextMapClickRef.current = false;
      return;
    }
    if (draggingItem !== null) {
      return;
    }
    setSelectedEquipmentId(null);
    const mapEl = event.currentTarget;
    const rect = mapEl.getBoundingClientRect();
    const offsetX = ((event.clientX - rect.left) / rect.width) * mapWidthPx;
    const offsetY = ((event.clientY - rect.top) / rect.height) * mapHeightPx;
    const xCm = Math.round(offsetX / PX_PER_CM);
    const yCm = Math.round(offsetY / PX_PER_CM);
    setNewObjCoords({ x: xCm, y: yCm });
    setIsModalOpen(true);
  };

  const handleMapPointerMove = (event: React.PointerEvent<HTMLDivElement>): void => {
    if (draggingItem === null) {
      return;
    }
    event.preventDefault();
    const dragged = zonesRef.current
      .flatMap((z) => z.equipment)
      .find((eq) => eq.id === draggingItem);
    if (!dragged) {
      return;
    }

    const mapEl = event.currentTarget;
    const rect = mapEl.getBoundingClientRect();
    const rawLeftPx = ((event.clientX - rect.left) / rect.width) * mapWidthPx;
    const rawTopPx = ((event.clientY - rect.top) / rect.height) * mapHeightPx;

    let leftPx = snapCoordPx(rawLeftPx);
    let topPx = snapCoordPx(rawTopPx);

    const widthPx = Math.max(dragged.width * PX_PER_CM, 8);
    const heightPx = Math.max(dragged.height * PX_PER_CM, 8);
    const rotation = dragged.rotation ?? 0;

    const snappedMag = magneticSnapTopLeftPx(
      leftPx,
      topPx,
      widthPx,
      heightPx,
      rotation,
      equipmentLayoutsPx,
      draggingItem,
      MAGNETIC_THRESHOLD_PX,
    );
    leftPx = snapCoordPx(snappedMag.left);
    topPx = snapCoordPx(snappedMag.top);

    let xCm = leftPx / PX_PER_CM;
    let yCm = topPx / PX_PER_CM;
    const clamped = clampEquipmentTopLeftCm(dragged, xCm, yCm);
    xCm = clamped.x;
    yCm = clamped.y;

    leftPx = snapCoordPx(xCm * PX_PER_CM);
    topPx = snapCoordPx(yCm * PX_PER_CM);
    const reclamped = clampEquipmentTopLeftCm(dragged, leftPx / PX_PER_CM, topPx / PX_PER_CM);

    updateEquipmentPositionInState(draggingItem, reclamped.x, reclamped.y);
  };

  const persistDraggedEquipment = async (): Promise<void> => {
    if (draggingItem === null) {
      return;
    }
    const dragged = zonesRef.current
      .flatMap((z) => z.equipment)
      .find((eq) => eq.id === draggingItem);
    if (!dragged) {
      setDraggingItem(null);
      return;
    }
    try {
      await api.patch(`/floor-equipment/${draggingItem}/`, {
        pos_x: dragged.pos_x,
        pos_y: dragged.pos_y,
      });
    } catch (error) {
      console.error('Ошибка сохранения позиции оборудования:', error);
      alert('Не удалось сохранить новую позицию оборудования.');
    } finally {
      suppressNextMapClickRef.current = true;
      setDraggingItem(null);
    }
  };

  const handleMapPointerUp = (): void => {
    if (draggingItem === null) {
      return;
    }
    void persistDraggedEquipment();
  };

  const resetNewEquipmentForm = (): void => {
    setNewEquipmentForm({
      name: '',
      widthCm: 120,
      lengthCm: 60,
      rotation: 0,
      type: 'shelving',
      shelfCount: 4,
    });
  };

  const handleSaveEquipment = async (): Promise<void> => {
    if (!defaultZoneId) {
      alert('Нет доступной зоны для добавления оборудования.');
      return;
    }
    if (!newEquipmentForm.name.trim()) {
      alert('Введите название оборудования.');
      return;
    }

    const payload = {
      name: newEquipmentForm.name.trim(),
      zone: defaultZoneId,
      type: newEquipmentForm.type,
      pos_x: newObjCoords.x,
      pos_y: newObjCoords.y,
      width: newEquipmentForm.widthCm,
      height: newEquipmentForm.lengthCm,
      rotation: snapRotationDeg(newEquipmentForm.rotation),
      shelf_count: newEquipmentForm.shelfCount,
    };

    try {
      setIsSaving(true);
      pushUndoSnapshot();
      const response = await api.post('/floor-equipment/', payload);
      if (response.status === 201) {
        const createdEquipment = normalizeFloorEquipment(
          response.data as Record<string, unknown>,
        );
        setZones((prevZones) =>
          prevZones.map((zone) =>
            zone.id === defaultZoneId
              ? { ...zone, equipment: [...zone.equipment, createdEquipment] }
              : zone,
          ),
        );
        setIsModalOpen(false);
        resetNewEquipmentForm();
      }
    } catch (error) {
      console.error('Ошибка при сохранении оборудования:', error);
      alert('Не удалось сохранить оборудование. Проверьте консоль.');
    } finally {
      setIsSaving(false);
    }
  };

  const rotateSelected = useCallback(
    async (deltaDeg: number): Promise<void> => {
      if (!selectedEquipmentId) {
        return;
      }
      const sel = zonesRef.current
        .flatMap((z) => z.equipment)
        .find((eq) => eq.id === selectedEquipmentId);
      if (!sel) {
        return;
      }
      const nextRotation = snapRotationDeg(sel.rotation + deltaDeg);
      pushUndoSnapshot();
      setZones((prevZones) =>
        prevZones.map((zone) => ({
          ...zone,
          equipment: zone.equipment.map((eq) =>
            eq.id === selectedEquipmentId ? { ...eq, rotation: nextRotation } : eq,
          ),
        })),
      );
      try {
        await api.patch(`/floor-equipment/${selectedEquipmentId}/`, {
          rotation: nextRotation,
        });
      } catch (error) {
        console.error('Ошибка сохранения поворота:', error);
        alert('Не удалось сохранить поворот на сервере.');
      }
    },
    [pushUndoSnapshot, selectedEquipmentId],
  );

  const cloneSelected = useCallback(async (): Promise<void> => {
    if (!selectedEquipmentId) {
      return;
    }
    const sel = zonesRef.current
      .flatMap((z) => z.equipment)
      .find((eq) => eq.id === selectedEquipmentId);
    if (!sel) {
      return;
    }

    const deltaCm = CLONE_OFFSET_PX / PX_PER_CM;
    const payload = {
      name: `${sel.name} (копия)`,
      zone: sel.zone,
      type: sel.type === 'shelf' ? 'shelving' : sel.type,
      pos_x: sel.pos_x + deltaCm,
      pos_y: sel.pos_y + deltaCm,
      width: sel.width,
      height: sel.height,
      rotation: snapRotationDeg(sel.rotation),
      shelf_count: sel.shelf_count ?? 0,
    };

    try {
      pushUndoSnapshot();
      const response = await api.post('/floor-equipment/', payload);
      if (response.status === 201) {
        const created = normalizeFloorEquipment(response.data as Record<string, unknown>);
        setZones((prevZones) =>
          prevZones.map((zone) =>
            zone.id === created.zone
              ? { ...zone, equipment: [...zone.equipment, created] }
              : zone,
          ),
        );
        setSelectedEquipmentId(created.id);
      }
    } catch (error) {
      console.error('Ошибка клонирования:', error);
      alert('Не удалось клонировать оборудование.');
    }
  }, [pushUndoSnapshot, selectedEquipmentId]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent): void => {
      if (!editMode) {
        return;
      }
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
        return;
      }

      const mod = e.ctrlKey || e.metaKey;

      if (mod && e.key.toLowerCase() === 'z' && !e.shiftKey) {
        e.preventDefault();
        undo();
        return;
      }
      if (mod && (e.key.toLowerCase() === 'y' || (e.key.toLowerCase() === 'z' && e.shiftKey))) {
        e.preventDefault();
        redo();
        return;
      }
      if (mod && e.key.toLowerCase() === 'd') {
        e.preventDefault();
        void cloneSelected();
        return;
      }
      if (!mod && e.key.toLowerCase() === 'r') {
        e.preventDefault();
        void rotateSelected(e.shiftKey ? 1 : 5);
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [cloneSelected, editMode, redo, rotateSelected, undo]);

  if (loading) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-slate-900 p-10 text-center text-slate-300 shadow-2xl">
        Loading...
      </div>
    );
  }

  const transformWrapperProps = {
    initialScale: minScale,
    minScale,
    maxScale: 2,
    limitToBounds: true,
    centerOnInit: true,
    wheel: {
      step: 0.02,
      smoothStep: 0.002,
    } as WheelConfig,
    panning: {
      disabled: draggingItem !== null,
      velocityDisabled: false,
    },
    doubleClick: { disabled: true },
    autoAlignment: {
      sizeX: 0,
      sizeY: 0,
      animationTime: 0,
    },
    alignmentAnimation: { size: 0 },
  } satisfies Record<string, unknown> & TransformWrapperExtras;

  return (
    <section className="flex min-h-0 w-full flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-700/80 bg-slate-900/90 px-3 py-2 text-sm text-slate-300 shadow-lg backdrop-blur-sm">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Размеры зала (м)
        </span>
        <label className="flex items-center gap-2">
          <span className="text-slate-400">Ширина</span>
          <input
            type="number"
            min={1}
            step={0.5}
            value={dimensions.width}
            onChange={(ev) =>
              setDimensions((d) => ({
                ...d,
                width: Math.max(1, Number(ev.target.value) || 1),
              }))
            }
            className="w-20 rounded-md border border-slate-600 bg-slate-950 px-2 py-1 text-slate-100 outline-none focus:border-emerald-500"
          />
        </label>
        <label className="flex items-center gap-2">
          <span className="text-slate-400">Длина</span>
          <input
            type="number"
            min={1}
            step={0.5}
            value={dimensions.height}
            onChange={(ev) =>
              setDimensions((d) => ({
                ...d,
                height: Math.max(1, Number(ev.target.value) || 1),
              }))
            }
            className="w-20 rounded-md border border-slate-600 bg-slate-950 px-2 py-1 text-slate-100 outline-none focus:border-emerald-500"
          />
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-700/80 bg-slate-900/90 px-3 py-2 text-sm text-slate-300 shadow-lg backdrop-blur-sm">
        <button
          type="button"
          onClick={() => {
            setEditMode((v) => !v);
            setDraggingItem(null);
          }}
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
          Сетка {SNAP_GRID_PX}px ({SNAP_GRID_PX / PX_PER_CM} см) · магнит ±{MAGNETIC_THRESHOLD_PX}px
        </span>
        <span className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900 px-3 py-1">
          <Warehouse className="h-3.5 w-3.5 text-amber-300" />
          Объектов: {allEquipment.length}
        </span>
      </div>

      <div
        ref={viewportRef}
        className="relative h-[600px] w-full overflow-hidden rounded-xl border border-slate-800 bg-slate-900"
      >
        <TransformWrapper
          key={`${mapWidthPx}x${mapHeightPx}`}
          {...transformWrapperProps}
        >
          <>
            <MapZoomToolbar />
            <TransformComponent
              wrapperClass="!h-full !w-full"
              wrapperStyle={{ width: '100%', height: '100%' }}
              contentStyle={{ width: mapWidthPx, height: mapHeightPx }}
              contentClass="!shadow-none"
            >
              <div
                role={editMode ? 'presentation' : undefined}
                className={`relative h-full w-full rounded-lg ring-1 ring-slate-600/70 ${editMode ? 'cursor-crosshair' : ''}`}
                style={{
                  imageRendering: 'pixelated',
                  ...gridStyle,
                }}
                onClick={handleMapClick}
                onPointerMove={handleMapPointerMove}
                onPointerUp={handleMapPointerUp}
                onPointerLeave={handleMapPointerUp}
              >
                {zones.map((zone) =>
                  zone.equipment.map((eq) => (
                    <MapEquipmentItem
                      key={eq.id}
                      equipment={eq}
                      zoneColorHex={zone.color}
                      pxPerCm={PX_PER_CM}
                      editMode={editMode}
                      selected={selectedEquipmentId === eq.id}
                      dragging={draggingItem === eq.id}
                      collision={collisionIds.has(eq.id)}
                      onPointerDown={(ev) => {
                        if (!editMode) {
                          return;
                        }
                        ev.stopPropagation();
                        pushUndoSnapshot();
                        setSelectedEquipmentId(eq.id);
                        setDraggingItem(eq.id);
                      }}
                      onClick={(ev) => {
                        ev.stopPropagation();
                        if (!editMode) {
                          console.log(`Полки стеллажа "${eq.name}"`, eq.shelves ?? []);
                        }
                      }}
                    />
                  )),
                )}
              </div>
            </TransformComponent>
          </>
        </TransformWrapper>

        <div className="pointer-events-none absolute bottom-3 left-4 z-20 max-w-[min(100%,28rem)] rounded-lg border border-slate-700/80 bg-slate-950/85 px-3 py-2 text-[11px] text-slate-400 backdrop-blur-sm">
          Колёсико — зум · перетаскивание — панорама
          {editMode ? (
            <span className="mt-1 block text-amber-200/90">
              Клик по карте — новый объект · R / Shift+R — поворот · Ctrl+D — клон · Ctrl+Z / Ctrl+Y —
              отмена / повтор
            </span>
          ) : null}
        </div>
      </div>

      {isModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/65 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-xl border border-slate-700 bg-slate-800 p-6 shadow-2xl">
            <h3 className="mb-4 text-lg font-semibold text-slate-100">
              Новое оборудование
            </h3>

            <div className="mb-4 grid grid-cols-2 gap-3 text-sm">
              <div className="rounded-md border border-slate-700 bg-slate-900/70 px-3 py-2 text-slate-300">
                X (см):{' '}
                <span className="font-semibold text-slate-100">{newObjCoords.x}</span>
              </div>
              <div className="rounded-md border border-slate-700 bg-slate-900/70 px-3 py-2 text-slate-300">
                Y (см):{' '}
                <span className="font-semibold text-slate-100">{newObjCoords.y}</span>
              </div>
            </div>

            <div className="space-y-3">
              <label className="block text-sm text-slate-300">
                Название оборудования
                <input
                  type="text"
                  value={newEquipmentForm.name}
                  onChange={(ev) =>
                    setNewEquipmentForm((prev) => ({ ...prev, name: ev.target.value }))
                  }
                  className="mt-1 w-full rounded-md border border-slate-600 bg-slate-900 px-3 py-2 text-slate-100 outline-none focus:border-emerald-500"
                  placeholder="Например, Стеллаж №5"
                />
              </label>

              <label className="block text-sm text-slate-300">
                Тип
                <select
                  value={newEquipmentForm.type}
                  onChange={(ev) =>
                    setNewEquipmentForm((prev) => ({
                      ...prev,
                      type: ev.target.value as FloorEquipmentType,
                    }))
                  }
                  className="mt-1 w-full rounded-md border border-slate-600 bg-slate-900 px-3 py-2 text-slate-100 outline-none focus:border-emerald-500"
                >
                  <option value="shelving">Стеллаж</option>
                  <option value="pegboard">Перфорированная панель</option>
                  <option value="fridge">Холодильник</option>
                  <option value="pallet">Паллета</option>
                  <option value="display">Витрина</option>
                </select>
              </label>

              <div className="grid grid-cols-2 gap-3">
                <label className="block text-sm text-slate-300">
                  Ширина (см)
                  <input
                    type="number"
                    min={1}
                    value={newEquipmentForm.widthCm}
                    onChange={(ev) =>
                      setNewEquipmentForm((prev) => ({
                        ...prev,
                        widthCm: Math.max(1, Number(ev.target.value) || 1),
                      }))
                    }
                    className="mt-1 w-full rounded-md border border-slate-600 bg-slate-900 px-3 py-2 text-slate-100 outline-none focus:border-emerald-500"
                  />
                </label>
                <label className="block text-sm text-slate-300">
                  Глубина/длина (см)
                  <input
                    type="number"
                    min={1}
                    value={newEquipmentForm.lengthCm}
                    onChange={(ev) =>
                      setNewEquipmentForm((prev) => ({
                        ...prev,
                        lengthCm: Math.max(1, Number(ev.target.value) || 1),
                      }))
                    }
                    className="mt-1 w-full rounded-md border border-slate-600 bg-slate-900 px-3 py-2 text-slate-100 outline-none focus:border-emerald-500"
                  />
                </label>
              </div>

              <label className="block text-sm text-slate-300">
                Число полок (визуал, для стеллажа)
                <input
                  type="number"
                  min={0}
                  max={50}
                  value={newEquipmentForm.shelfCount}
                  onChange={(ev) =>
                    setNewEquipmentForm((prev) => ({
                      ...prev,
                      shelfCount: Math.max(0, Math.min(50, Number(ev.target.value) || 0)),
                    }))
                  }
                  className="mt-1 w-full rounded-md border border-slate-600 bg-slate-900 px-3 py-2 text-slate-100 outline-none focus:border-emerald-500"
                />
              </label>

              <label className="block text-sm text-slate-300">
                Угол поворота (°)
                <select
                  value={newEquipmentForm.rotation}
                  onChange={(ev) =>
                    setNewEquipmentForm((prev) => ({
                      ...prev,
                      rotation: Number(ev.target.value),
                    }))
                  }
                  className="mt-1 w-full rounded-md border border-slate-600 bg-slate-900 px-3 py-2 text-slate-100 outline-none focus:border-emerald-500"
                >
                  <option value={0}>0°</option>
                  <option value={90}>90°</option>
                  <option value={180}>180°</option>
                  <option value={270}>270°</option>
                </select>
              </label>
            </div>

            <div className="mt-6 flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => {
                  setIsModalOpen(false);
                  resetNewEquipmentForm();
                }}
                className="rounded-md border border-slate-600 bg-slate-900 px-4 py-2 text-sm text-slate-300 transition hover:border-slate-500"
              >
                Отмена
              </button>
              <button
                type="button"
                disabled={isSaving}
                onClick={handleSaveEquipment}
                className="rounded-md border border-emerald-500/70 bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isSaving ? 'Сохранение...' : 'Сохранить'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

export default StoreMap;
