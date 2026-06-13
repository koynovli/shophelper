import type { FloorEquipmentType } from '../types/floorPlan';
import { normalizeEquipmentType } from '../types/floorPlan';

export type LayoutMode = 'grid' | 'linear' | 'single' | 'expo_vertical';

export const MANNEQUIN_ZONE_LABELS = ['Верх', 'Низ', 'Аксессуар'] as const;

export const EQUIPMENT_TYPE_OPTIONS: { value: FloorEquipmentType; label: string }[] = [
  { value: 'shelf', label: 'Стеллаж' },
  { value: 'hanger', label: 'Вешалка' },
  { value: 'fridge', label: 'Холодильник' },
  { value: 'box', label: 'Бокс / корзина' },
  { value: 'mannequin', label: 'Манекен' },
];

export const EQUIPMENT_TYPE_SHORT_LABELS: Record<FloorEquipmentType, string> = {
  shelf: 'Стеллаж',
  hanger: 'Вешалка',
  fridge: 'Холод.',
  box: 'Бокс',
  mannequin: 'Манекен',
};

type Profile = {
  layoutMode: LayoutMode;
  defaultRowsCount: number;
  maxHangerRows: number;
  mannequinZones: number;
  showsRowsField: boolean;
  rowsFieldMax: number;
  typeHint: string;
};

const PROFILES: Record<FloorEquipmentType, Profile> = {
  shelf: {
    layoutMode: 'grid',
    defaultRowsCount: 4,
    maxHangerRows: 2,
    mannequinZones: 3,
    showsRowsField: true,
    rowsFieldMax: 50,
    typeHint: 'Сетка 4 ячейки на ряд. Полки создаются автоматически.',
  },
  fridge: {
    layoutMode: 'grid',
    defaultRowsCount: 4,
    maxHangerRows: 2,
    mannequinZones: 3,
    showsRowsField: true,
    rowsFieldMax: 50,
    typeHint: 'Сетка как у стеллажа. Нештабелируемые товары — один ярус.',
  },
  hanger: {
    layoutMode: 'linear',
    defaultRowsCount: 2,
    maxHangerRows: 2,
    mannequinZones: 3,
    showsRowsField: true,
    rowsFieldMax: 2,
    typeHint: '1–2 горизонтальных рейла на всю ширину. Линейная вместимость.',
  },
  box: {
    layoutMode: 'single',
    defaultRowsCount: 1,
    maxHangerRows: 2,
    mannequinZones: 3,
    showsRowsField: false,
    rowsFieldMax: 1,
    typeHint: 'Один слот на всю ёмкость. Объёмная укладка.',
  },
  mannequin: {
    layoutMode: 'expo_vertical',
    defaultRowsCount: 3,
    maxHangerRows: 2,
    mannequinZones: 3,
    showsRowsField: false,
    rowsFieldMax: 3,
    typeHint: '3 зоны экспозиции: верх, низ, аксессуар. Макс. 1 SKU на зону.',
  },
};

export function getProfile(type: string): Profile {
  const normalized = normalizeEquipmentType(type);
  return PROFILES[normalized];
}

export function getLayoutMode(type: string): LayoutMode {
  return getProfile(type).layoutMode;
}

export function defaultRowsCountForType(type: string): number {
  return getProfile(type).defaultRowsCount;
}

export function showsRowsField(type: string): boolean {
  return getProfile(type).showsRowsField;
}

export function rowsFieldMax(type: string): number {
  return getProfile(type).rowsFieldMax;
}

export function typeHint(type: string): string {
  return getProfile(type).typeHint;
}

export function slotRowLabel(
  type: string,
  rowIndex: number,
  slotLabel?: string | null,
): string {
  if (slotLabel?.trim()) {
    return slotLabel.trim();
  }
  const normalized = normalizeEquipmentType(type);
  if (normalized === 'mannequin') {
    return MANNEQUIN_ZONE_LABELS[rowIndex] ?? `Зона ${rowIndex + 1}`;
  }
  if (normalized === 'hanger') {
    return `Рейл ${rowIndex + 1}`;
  }
  if (normalized === 'box') {
    return 'Ёмкость';
  }
  return `Ряд ${rowIndex}`;
}

export const CATALOG_EQUIPMENT_PRESETS: {
  id: string;
  label: string;
  types: FloorEquipmentType[];
  stackable?: boolean;
  hint?: string;
}[] = [
  {
    id: 'shelf-grocery',
    label: 'Полочный / бакалея',
    types: ['shelf', 'box'],
  },
  {
    id: 'hanger-clothes',
    label: 'Одежда на вешалке',
    types: ['hanger'],
    stackable: false,
  },
  {
    id: 'fridge',
    label: 'Охлаждёнка',
    types: ['fridge'],
  },
  {
    id: 'mannequin-look',
    label: 'Экспозиция / look',
    types: ['mannequin'],
    stackable: false,
    hint: 'Макс. 1 ед. на зону экспозиции.',
  },
];

export function formatAllowedEquipmentTypes(types: string[] | undefined | null): string {
  if (!types?.length) {
    return 'Все';
  }
  return types
    .map((t) => EQUIPMENT_TYPE_SHORT_LABELS[normalizeEquipmentType(t)] ?? t)
    .join(', ');
}

export function isProductAllowedOnEquipment(
  allowedTypes: string[] | undefined | null,
  equipmentType: string,
): boolean {
  if (!allowedTypes?.length) {
    return true;
  }
  const normalized = normalizeEquipmentType(equipmentType);
  return allowedTypes.some((t) => normalizeEquipmentType(t) === normalized);
}
