import type { EquipmentSlot } from '../types/floorPlan';
import { slotFillMetrics } from '../types/floorPlan';

export type SlotFillLevel = 'green' | 'yellow' | 'red' | 'empty';

export type SlotVisualState = {
  level: SlotFillLevel;
  fillHex: string;
  strokeHex: string;
  pulse: boolean;
  showAlert: boolean;
};

const COLORS: Record<SlotFillLevel, { fill: string; stroke: string }> = {
  green: { fill: 'rgba(34, 197, 94, 0.75)', stroke: '#4ade80' },
  yellow: { fill: 'rgba(234, 179, 8, 0.75)', stroke: '#facc15' },
  red: { fill: 'rgba(239, 68, 68, 0.8)', stroke: '#f87171' },
  empty: { fill: 'rgba(71, 85, 105, 0.5)', stroke: '#64748b' },
};

export function getSlotVisualState(
  slot: EquipmentSlot,
  pendingSlotIds: Set<number>,
): SlotVisualState {
  const fill = slotFillMetrics(slot);
  const hasTask =
    pendingSlotIds.has(slot.id) ||
    Boolean(slot.active_placement_task) ||
    slot.planogram?.replenishment_status === 'IN_PROGRESS';

  let level: SlotFillLevel = 'empty';
  if (slot.planogram) {
    if (fill.cap > 0) {
      const ratio = fill.current / fill.cap;
      if (ratio > 0.7) {
        level = 'green';
      } else if (ratio >= 0.3) {
        level = 'yellow';
      } else {
        level = 'red';
      }
    } else {
      level = 'yellow';
    }
  }

  if (hasTask && level === 'green') {
    level = 'yellow';
  }

  const palette = COLORS[level];
  return {
    level,
    fillHex: palette.fill,
    strokeHex: palette.stroke,
    pulse: hasTask,
    showAlert: hasTask,
  };
}
