export type FloorEquipmentType =
  | 'shelving'
  | 'pegboard'
  | 'fridge'
  | 'pallet'
  | 'display';

export interface FloorShelf {
  id: number;
  level: number;
  width: number;
  height: number;
  depth: number;
}

export interface FloorEquipment {
  id: number;
  name: string;
  zone: number;
  type: FloorEquipmentType | string;
  pos_x: number;
  pos_y: number;
  width: number;
  height: number;
  rotation: number;
  rows_count: number;
  shelves: FloorShelf[];
  slots?: EquipmentSlot[];
}

export interface EquipmentSlot {
  id: number;
  row_index: number;
  col_index: number;
  width_percent: number;
  planogram?: {
    id: number;
    product: { id: number; name: string; sku: string };
    target_quantity: number;
    stock_quantity?: number;
    pending_quantity?: number;
    replenishment_status?: 'OK' | 'IN_PROGRESS' | 'DEFICIT' | string;
  } | null;
}

export interface FloorZone {
  id: number;
  name: string;
  store: number;
  color: string;
  equipment: FloorEquipment[];
}

/** Числа из JSON иногда приходят строками; без этого поворот и координаты сбрасывались в 0. */
function parseFiniteNumber(value: unknown, fallback = 0): number {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const n = Number(value);
    if (Number.isFinite(n)) {
      return n;
    }
  }
  return fallback;
}

export function normalizeFloorEquipment(raw: Record<string, unknown>): FloorEquipment {
  let typeRaw = String(raw.type ?? 'shelving');
  if (typeRaw === 'shelf') {
    typeRaw = 'shelving';
  }
  const rotation = parseFiniteNumber(
    raw.rotation,
    parseFiniteNumber(raw.orientation, 0),
  );
  const rowsCount = Math.max(
    0,
    Math.floor(
      parseFiniteNumber(
        raw.rows_count,
        parseFiniteNumber(
          raw.shelf_count,
          parseFiniteNumber(raw.rowsCount, parseFiniteNumber(raw.shelfCount, 0)),
        ),
      ),
    ),
  );

  return {
    id: Number(raw.id),
    name: String(raw.name ?? ''),
    zone: Number(raw.zone ?? 0),
    type: typeRaw,
    pos_x: parseFiniteNumber(raw.pos_x, 0),
    pos_y: parseFiniteNumber(raw.pos_y, 0),
    width: parseFiniteNumber(raw.width, 0),
    height: parseFiniteNumber(raw.height, 0),
    rotation,
    rows_count: rowsCount,
    shelves: Array.isArray(raw.shelves) ? (raw.shelves as FloorShelf[]) : [],
    slots: Array.isArray(raw.slots) ? (raw.slots as EquipmentSlot[]) : [],
  };
}
