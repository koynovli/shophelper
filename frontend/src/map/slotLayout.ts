import type { EquipmentSlot, FloorEquipment, FloorEquipmentType } from '../types/floorPlan';
import { normalizeEquipmentType } from '../types/floorPlan';

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

function rowCountForEquipment(
  equipment: FloorEquipment,
  slots: EquipmentSlot[],
): number {
  const eqType = normalizeEquipmentType(String(equipment.type));
  if (eqType === 'box' || eqType === 'mannequin') {
    return 1;
  }
  if (eqType === 'hanger') {
    const fromSlots = slots.length
      ? Math.max(...slots.map((s) => s.row_index)) + 1
      : 1;
    return Math.min(2, Math.max(fromSlots, equipment.rows_count || 1));
  }
  const fromSlots = slots.length ? Math.max(...slots.map((s) => s.row_index)) + 1 : 0;
  return Math.max(fromSlots, equipment.rows_count || 1, 1);
}

export function computeSlotRects(
  equipment: FloorEquipment,
  slots: EquipmentSlot[],
  pixelWidth: number,
  pixelHeight: number,
): SlotRect[] {
  const eqType = normalizeEquipmentType(String(equipment.type)) as FloorEquipmentType;
  const innerW = Math.max(1, pixelWidth - PADDING * 2);
  const innerH = Math.max(1, pixelHeight - PADDING * 2);
  const rowCount = rowCountForEquipment(equipment, slots);

  if (slots.length === 0) {
    return [];
  }

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

    let rowHeight: number;
    if (eqType === 'hanger') {
      rowHeight = innerH * 0.18;
    } else {
      rowHeight = innerH / rowCount;
    }
    const rowY = PADDING + (eqType === 'hanger' ? innerH * 0.4 + row * (rowHeight + 4) : row * rowHeight);

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

  if (eqType === 'box' || eqType === 'mannequin') {
    const single = slots[0];
    if (single) {
      return [
        {
          slotId: single.id,
          rowIndex: single.row_index,
          colIndex: single.col_index,
          x: PADDING,
          y: PADDING,
          width: innerW,
          height: innerH,
        },
      ];
    }
  }

  return rects;
}
