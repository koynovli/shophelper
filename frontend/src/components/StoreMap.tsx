import React, {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  Copy,
  MapPinned,
  Minus,
  MousePointer2,
  Pencil,
  Plus,
  RotateCcw,
  Ruler,
  SquarePlus,
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
const MAX_HISTORY = 50;

type EditorMode = 'SELECT' | 'CREATE' | 'DUPLICATE';
type EquipmentModalMode = 'create' | 'edit';

const EQUIPMENT_TYPE_LABEL_RU: Record<FloorEquipmentType, string> = {
  shelving: 'Стеллаж',
  pegboard: 'Перфорированная панель',
  fridge: 'Холодильник',
  pallet: 'Паллета',
  display: 'Витрина',
};

function normalizeEquipmentTypeValue(type: string): FloorEquipmentType {
  return type === 'shelf' ? 'shelving' : (type as FloorEquipmentType);
}

function nextGlobalEquipmentName(zones: FloorZone[], type: FloorEquipmentType): string {
  const label = EQUIPMENT_TYPE_LABEL_RU[type];
  const existingNames = new Set(
    zones.flatMap((z) => z.equipment.map((eq) => eq.name.trim().toLowerCase())),
  );
  let counter = zones.reduce((acc, z) => acc + z.equipment.length, 0) + 1;
  let candidate = `${label} ${counter}`;
  while (existingNames.has(candidate.toLowerCase())) {
    counter += 1;
    candidate = `${label} ${counter}`;
  }
  return candidate;
}

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
  const [editorMode, setEditorMode] = useState<EditorMode>('SELECT');
  const [draggingItem, setDraggingItem] = useState<number | null>(null);
  const [selectedEquipmentId, setSelectedEquipmentId] = useState<number | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState<EquipmentModalMode>('create');
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
  const mapBoardRef = useRef<HTMLDivElement>(null);
  const suppressNextMapClickRef = useRef(false);
  const zonesRef = useRef<FloorZone[]>([]);
  const undoStackRef = useRef<FloorZone[][]>([]);
  const redoStackRef = useRef<FloorZone[][]>([]);
  const duplicateSourceRef = useRef<FloorEquipment | null>(null);
  const selectedEquipmentIdRef = useRef<number | null>(null);

  useEffect(() => {
    zonesRef.current = zones;
  }, [zones]);

  useEffect(() => {
    selectedEquipmentIdRef.current = selectedEquipmentId;
  }, [selectedEquipmentId]);

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
  const isSelectMode = editorMode === 'SELECT';
  const isCreateMode = editorMode === 'CREATE';
  const isDuplicateMode = editorMode === 'DUPLICATE';
  const selectedEquipment = allEquipment.find((eq) => eq.id === selectedEquipmentId) ?? null;

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
    (eq: Pick<FloorEquipment, 'width' | 'height'>, xCm: number, yCm: number): { x: number; y: number } => {
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

  const openCreateModalAt = useCallback(
    (xCm: number, yCm: number): void => {
      const clamped = clampEquipmentTopLeftCm({ width: 120, height: 60 }, xCm, yCm);
      setModalMode('create');
      setSelectedEquipmentId(null);
      setNewObjCoords({ x: clamped.x, y: clamped.y });
      setNewEquipmentForm({
        name: nextGlobalEquipmentName(zonesRef.current, 'shelving'),
        widthCm: 120,
        lengthCm: 60,
        rotation: 0,
        type: 'shelving',
        shelfCount: 4,
      });
      setIsModalOpen(true);
    },
    [clampEquipmentTopLeftCm],
  );

  const createFromDuplicateAt = useCallback(
    async (xCm: number, yCm: number): Promise<void> => {
      const source = duplicateSourceRef.current;
      if (!source) {
        alert('Сначала выберите эталон через окно параметров.');
        return;
      }
      const clamped = clampEquipmentTopLeftCm(source, xCm, yCm);
      const normalizedType = normalizeEquipmentTypeValue(String(source.type));
      const payload = {
        name: nextGlobalEquipmentName(zonesRef.current, normalizedType),
        zone: source.zone,
        type: normalizedType,
        pos_x: clamped.x,
        pos_y: clamped.y,
        width: source.width,
        height: source.height,
        rotation: snapRotationDeg(source.rotation),
        shelf_count: source.shelf_count ?? 0,
      };

      try {
        pushUndoSnapshot();
        const response = await api.post('/floor-equipment/', payload);
        if (response.status === 201) {
          const created = normalizeFloorEquipment(response.data as Record<string, unknown>);
          setZones((prevZones) =>
            prevZones.map((zone) =>
              zone.id === created.zone ? { ...zone, equipment: [...zone.equipment, created] } : zone,
            ),
          );
          setSelectedEquipmentId(created.id);
        }
      } catch (error) {
        console.error('Ошибка дублирования в режиме DUPLICATE:', error);
        alert('Не удалось создать копию оборудования.');
      }
    },
    [clampEquipmentTopLeftCm, pushUndoSnapshot],
  );

  const handleMapClick = (event: React.MouseEvent<HTMLDivElement>): void => {
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
    const xCm = snapCoordPx(offsetX) / PX_PER_CM;
    const yCm = snapCoordPx(offsetY) / PX_PER_CM;
    if (isCreateMode) {
      openCreateModalAt(xCm, yCm);
      return;
    }
    if (isDuplicateMode) {
      void createFromDuplicateAt(xCm, yCm);
      return;
    }
    setSelectedEquipmentId(null);
  };

  const handleMapPointerMove = (event: React.PointerEvent<HTMLDivElement>): void => {
    if (!isSelectMode) {
      return;
    }
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

  const handleMapBoardPointerLeave = (): void => {
    handleMapPointerUp();
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
      if (modalMode === 'create') {
        const response = await api.post('/floor-equipment/', {
          ...payload,
          zone: defaultZoneId,
        });
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
          setSelectedEquipmentId(createdEquipment.id);
        }
      } else if (selectedEquipmentId) {
        const response = await api.patch(`/floor-equipment/${selectedEquipmentId}/`, payload);
        if (response.status === 200) {
          setZones((prevZones) =>
            prevZones.map((zone) => ({
              ...zone,
              equipment: zone.equipment.map((eq) =>
                eq.id === selectedEquipmentId
                  ? { ...eq, ...payload, zone: eq.zone }
                  : eq,
              ),
            })),
          );
        }
      }
      setIsModalOpen(false);
      resetNewEquipmentForm();
    } catch (error) {
      console.error('Ошибка при сохранении оборудования:', error);
      alert('Не удалось сохранить оборудование. Проверьте консоль.');
    } finally {
      setIsSaving(false);
    }
  };

  const rotateSelected = useCallback(
    async (deltaDeg: number): Promise<void> => {
      const id = selectedEquipmentIdRef.current;
      if (!id) {
        return;
      }
      const sel = zonesRef.current
        .flatMap((z) => z.equipment)
        .find((eq) => eq.id === id);
      if (!sel) {
        return;
      }
      const nextRotation = snapRotationDeg(sel.rotation + deltaDeg);
      pushUndoSnapshot();
      setZones((prevZones) =>
        prevZones.map((zone) => ({
          ...zone,
          equipment: zone.equipment.map((eq) =>
            eq.id === id ? { ...eq, rotation: nextRotation } : eq,
          ),
        })),
      );
      try {
        await api.patch(`/floor-equipment/${id}/`, {
          rotation: nextRotation,
        });
      } catch (error) {
        console.error('Ошибка сохранения поворота:', error);
        alert('Не удалось сохранить поворот на сервере.');
      }
    },
    [pushUndoSnapshot],
  );

  const deleteSelectedEquipment = useCallback(async (): Promise<void> => {
    const id = selectedEquipmentIdRef.current;
    if (!id) {
      return;
    }
    const exists = zonesRef.current.flatMap((z) => z.equipment).some((e) => e.id === id);
    if (!exists) {
      setIsModalOpen(false);
      return;
    }
    if (!window.confirm('Удалить оборудование?')) {
      return;
    }
    try {
      pushUndoSnapshot();
      await api.delete(`/floor-equipment/${id}/`);
      setZones((prevZones) =>
        prevZones.map((z) => ({ ...z, equipment: z.equipment.filter((e) => e.id !== id) })),
      );
      setSelectedEquipmentId(null);
      setIsModalOpen(false);
      resetNewEquipmentForm();
    } catch (error) {
      console.error('Ошибка удаления оборудования:', error);
      alert('Не удалось удалить оборудование.');
    }
  }, [pushUndoSnapshot]);

  const openEditModal = useCallback((equipment: FloorEquipment): void => {
    setModalMode('edit');
    setSelectedEquipmentId(equipment.id);
    setNewObjCoords({ x: equipment.pos_x, y: equipment.pos_y });
    setNewEquipmentForm({
      name: equipment.name,
      widthCm: equipment.width,
      lengthCm: equipment.height,
      rotation: equipment.rotation,
      type: normalizeEquipmentTypeValue(String(equipment.type)),
      shelfCount: equipment.shelf_count ?? 0,
    });
    setIsModalOpen(true);
  }, []);

  const activateDuplicateModeFromSelected = useCallback((): void => {
    if (!selectedEquipmentId) {
      return;
    }
    const selected = zonesRef.current
      .flatMap((z) => z.equipment)
      .find((eq) => eq.id === selectedEquipmentId);
    if (!selected) {
      return;
    }
    duplicateSourceRef.current = selected;
    setEditorMode('DUPLICATE');
    setIsModalOpen(false);
  }, [selectedEquipmentId]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent): void => {
      const target = e.target;
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement
      ) {
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
      if (!mod && e.key.toLowerCase() === 'a') {
        e.preventDefault();
        void rotateSelected(e.shiftKey ? -1 : -5);
        return;
      }
      if (!mod && e.key.toLowerCase() === 'd') {
        e.preventDefault();
        void rotateSelected(e.shiftKey ? 1 : 5);
        return;
      }
      if (!mod && e.key.toLowerCase() === 'e') {
        e.preventDefault();
        setEditorMode('CREATE');
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [redo, rotateSelected, undo]);

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

      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-700/80 bg-slate-900/90 px-3 py-2 text-sm text-slate-300 shadow-lg backdrop-blur-sm">
        <button
          type="button"
          onClick={() => {
            setEditorMode('SELECT');
            setDraggingItem(null);
          }}
          className={`inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
            isSelectMode
              ? 'border-sky-500/70 bg-sky-500/15 text-sky-200'
              : 'border-slate-600 bg-slate-800 text-slate-300 hover:border-slate-500'
          }`}
        >
          <MousePointer2 className="h-3.5 w-3.5" />
          SELECT
        </button>
        <button
          type="button"
          onClick={() => setEditorMode('CREATE')}
          className={`inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
            isCreateMode
              ? 'border-emerald-500/70 bg-emerald-500/15 text-emerald-200'
              : 'border-slate-600 bg-slate-800 text-slate-300 hover:border-slate-500'
          }`}
          title="Создать оборудование (E)"
          aria-label="Создать оборудование (E)"
        >
          <SquarePlus className="h-3.5 w-3.5" />
          CREATE
        </button>
        <button
          type="button"
          onClick={() => setEditorMode('DUPLICATE')}
          disabled={!duplicateSourceRef.current}
          className={`inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
            isDuplicateMode
              ? 'border-violet-500/70 bg-violet-500/15 text-violet-200'
              : 'border-slate-600 bg-slate-800 text-slate-300 hover:border-slate-500'
          } disabled:cursor-not-allowed disabled:opacity-50`}
          title="Режим дублирования по клику"
        >
          <Copy className="h-3.5 w-3.5" />
          DUPLICATE
        </button>
        <span className="ml-2 text-xs text-slate-400">
          Текущий режим: <span className="font-semibold text-slate-200">{editorMode}</span>
        </span>
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
        {selectedEquipment ? (
          <span className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900 px-3 py-1">
            <Pencil className="h-3.5 w-3.5 text-sky-300" />
            Поворот: {Math.round(selectedEquipment.rotation ?? 0)}°
          </span>
        ) : null}
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
                ref={mapBoardRef}
                role="presentation"
                className={`relative h-full w-full rounded-lg ring-1 ring-slate-600/70 ${isCreateMode || isDuplicateMode ? 'cursor-crosshair' : ''}`}
                style={{
                  imageRendering: 'pixelated',
                  ...gridStyle,
                }}
                onClick={handleMapClick}
                onPointerMove={handleMapPointerMove}
                onPointerUp={handleMapPointerUp}
                onPointerLeave={handleMapBoardPointerLeave}
              >
                {zones.map((zone) =>
                  zone.equipment.map((eq) => (
                    <MapEquipmentItem
                      key={eq.id}
                      equipment={eq}
                      zoneColorHex={zone.color}
                      pxPerCm={PX_PER_CM}
                      editMode={isSelectMode}
                      selected={selectedEquipmentId === eq.id}
                      dragging={draggingItem === eq.id}
                      collision={collisionIds.has(eq.id)}
                      onPointerDown={(ev) => {
                        if (!isSelectMode) {
                          return;
                        }
                        ev.stopPropagation();
                        pushUndoSnapshot();
                        setSelectedEquipmentId(eq.id);
                        setDraggingItem(eq.id);
                      }}
                      onClick={(ev) => {
                        ev.stopPropagation();
                        setSelectedEquipmentId(eq.id);
                      }}
                      onDoubleClick={(ev) => {
                        ev.stopPropagation();
                        openEditModal(eq);
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
          {isSelectMode || isCreateMode || isDuplicateMode ? (
            <span className="mt-1 block text-amber-200/90">
              E — включить CREATE · A/D (+ Shift) — поворот · Double click — параметры · Ctrl+Z / Ctrl+Y
            </span>
          ) : null}
        </div>
      </div>

      {isModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/65 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-xl border border-slate-700 bg-slate-800 p-6 shadow-2xl">
            <h3 className="mb-4 text-lg font-semibold text-slate-100">
              {modalMode === 'create' ? 'Новое оборудование' : 'Параметры оборудования'}
            </h3>
            {modalMode === 'edit' ? (
              <div className="mb-3 text-xs text-slate-300">
                Текущий угол: <span className="font-semibold text-slate-100">{Math.round(newEquipmentForm.rotation)}°</span>
              </div>
            ) : null}

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
              {modalMode === 'edit' ? (
                <button
                  type="button"
                  onClick={activateDuplicateModeFromSelected}
                  className="mr-auto rounded-md border border-violet-500/70 bg-violet-600/20 px-4 py-2 text-sm font-medium text-violet-100 transition hover:bg-violet-500/30"
                >
                  Дублировать
                </button>
              ) : null}
              {modalMode === 'edit' ? (
                <button
                  type="button"
                  onClick={() => void deleteSelectedEquipment()}
                  className="rounded-md border border-red-500/70 bg-red-600/15 px-4 py-2 text-sm font-medium text-red-100 transition hover:bg-red-500/25"
                >
                  Удалить
                </button>
              ) : null}
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
                {isSaving ? 'Сохранение...' : modalMode === 'create' ? 'Создать' : 'Сохранить'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

export default StoreMap;
