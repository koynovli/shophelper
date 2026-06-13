import type { EquipmentSlot, FloorEquipment } from '../types/floorPlan';
import { normalizeEquipmentType } from '../types/floorPlan';
import { getLayoutMode, getProfile } from './equipmentProfiles';

export type SlotRect = {
  slotId: number;
  rowIndex: number;
  colIndex: number;
  x: number;
  y: number;
  width: number;
  height: number;
};

const PADDING = 2;

function computeGridRects(
  slots: EquipmentSlot[],
  rowCount: number,
  innerW: number,
  innerH: number,
): SlotRect[] {
  const byRow = new Map<number, EquipmentSlot[]>();
  for (const slot of slots) {
    const list = byRow.get(slot.row_index) ?? [];
    list.push(slot);
    byRow.set(slot.row_index, list);
  }

  const rects: SlotRect[] = [];
  for (let row = 0; row < rowCount; row += 1) {
    const rowSlots = (byRow.get(row) ?? []).sort((a, b) => a.col_index - b.col_index);
    if (rowSlots.length === 0) {
      continue;
    }
    const rowHeight = innerH / rowCount;
    const rowY = PADDING + row * rowHeight;
    const totalPct = rowSlots.reduce((sum, s) => sum + (s.width_percent || 0), 0) || 100;
    let xCursor = PADDING;

    for (const slot of rowSlots) {
      const pct = slot.width_percent || 100 / rowSlots.length;
      const cellW = innerW * (pct / totalPct);
      rects.push({
        slotId: slot.id,
        rowIndex: slot.row_index,
        colIndex: slot.col_index,
        x: xCursor,
        y: rowY,
        width: Math.max(2, cellW - 1),
        height: Math.max(2, rowHeight - 1),
      });
      xCursor += cellW;
    }
  }
  return rects;
}

function computeLinearRects(
  slots: EquipmentSlot[],
  rowCount: number,
  innerW: number,
  innerH: number,
): SlotRect[] {
  const byRow = new Map<number, EquipmentSlot>();
  for (const slot of slots) {
    if (!byRow.has(slot.row_index)) {
      byRow.set(slot.row_index, slot);
    }
  }

  const effectiveRows = Math.max(1, rowCount, byRow.size);
  const rowHeight = innerH / effectiveRows;
  const rects: SlotRect[] = [];

  for (let row = 0; row < effectiveRows; row += 1) {
    const slot = byRow.get(row);
    if (!slot) {
      continue;
    }
    rects.push({
      slotId: slot.id,
      rowIndex: slot.row_index,
      colIndex: slot.col_index,
      x: PADDING,
      y: PADDING + row * rowHeight,
      width: innerW,
      height: Math.max(2, rowHeight - 1),
    });
  }
  return rects;
}

function computeSingleRect(slots: EquipmentSlot[], innerW: number, innerH: number): SlotRect[] {
  const slot = slots[0];
  if (!slot) {
    return [];
  }
  return [
    {
      slotId: slot.id,
      rowIndex: slot.row_index,
      colIndex: slot.col_index,
      x: PADDING,
      y: PADDING,
      width: innerW,
      height: innerH,
    },
  ];
}

function computeExpoVerticalRects(
  slots: EquipmentSlot[],
  zoneCount: number,
  innerW: number,
  innerH: number,
): SlotRect[] {
  const byRow = new Map<number, EquipmentSlot>();
  for (const slot of slots) {
    byRow.set(slot.row_index, slot);
  }

  const rows = Math.max(zoneCount, byRow.size, 1);
  const rowHeight = innerH / rows;
  const rects: SlotRect[] = [];

  for (let row = 0; row < rows; row += 1) {
    const slot = byRow.get(row);
    if (!slot) {
      continue;
    }
    rects.push({
      slotId: slot.id,
      rowIndex: slot.row_index,
      colIndex: slot.col_index,
      x: PADDING,
      y: PADDING + row * rowHeight,
      width: innerW,
      height: Math.max(2, rowHeight - 1),
    });
  }
  return rects;
}

function rowCountForEquipment(
  equipment: FloorEquipment,
  slots: EquipmentSlot[],
): number {
  const profile = getProfile(String(equipment.type));
  const fromSlots = slots.length ? Math.max(...slots.map((s) => s.row_index)) + 1 : 0;

  if (profile.layoutMode === 'single') {
    return 1;
  }
  if (profile.layoutMode === 'expo_vertical') {
    return profile.mannequinZones;
  }
  if (profile.layoutMode === 'linear') {
    return Math.min(
      profile.maxHangerRows,
      Math.max(fromSlots, equipment.rows_count || profile.defaultRowsCount, 1),
    );
  }
  return Math.max(fromSlots, equipment.rows_count || profile.defaultRowsCount, 1);
}

export function computeSlotRects(
  equipment: FloorEquipment,
  slots: EquipmentSlot[],
  pixelWidth: number,
  pixelHeight: number,
): SlotRect[] {
  const innerW = Math.max(1, pixelWidth - PADDING * 2);
  const innerH = Math.max(1, pixelHeight - PADDING * 2);
  if (slots.length === 0) {
    return [];
  }

  const eqType = normalizeEquipmentType(String(equipment.type));
  const layoutMode = getLayoutMode(eqType);
  const profile = getProfile(eqType);
  const rowCount = rowCountForEquipment(equipment, slots);

  switch (layoutMode) {
    case 'linear':
      return computeLinearRects(slots, rowCount, innerW, innerH);
    case 'single':
      return computeSingleRect(slots, innerW, innerH);
    case 'expo_vertical':
      return computeExpoVerticalRects(slots, profile.mannequinZones, innerW, innerH);
    case 'grid':
    default:
      return computeGridRects(slots, rowCount, innerW, innerH);
  }
}
