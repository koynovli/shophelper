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
  shelf_count: number;
  shelves: FloorShelf[];
}

export interface FloorZone {
  id: number;
  name: string;
  store: number;
  color: string;
  equipment: FloorEquipment[];
}

export function normalizeFloorEquipment(raw: Record<string, unknown>): FloorEquipment {
  let typeRaw = String(raw.type ?? 'shelving');
  if (typeRaw === 'shelf') {
    typeRaw = 'shelving';
  }
  const rotation =
    typeof raw.rotation === 'number'
      ? raw.rotation
      : typeof raw.orientation === 'number'
        ? raw.orientation
        : 0;
  const shelfCount =
    typeof raw.shelf_count === 'number'
      ? raw.shelf_count
      : typeof raw.shelfCount === 'number'
        ? raw.shelfCount
        : 0;

  return {
    id: Number(raw.id),
    name: String(raw.name ?? ''),
    zone: Number(raw.zone ?? 0),
    type: typeRaw,
    pos_x: Number(raw.pos_x ?? 0),
    pos_y: Number(raw.pos_y ?? 0),
    width: Number(raw.width ?? 0),
    height: Number(raw.height ?? 0),
    rotation,
    shelf_count: shelfCount,
    shelves: Array.isArray(raw.shelves) ? (raw.shelves as FloorShelf[]) : [],
  };
}
