import type { FloorEquipmentType } from '../types/floorPlan';
import { normalizeEquipmentType } from '../types/floorPlan';

export type EquipmentShapeStyle = {
  bodyFill: string;
  bodyStroke: string;
  strokeWidth: number;
  cornerRadius: number;
  useEllipse: boolean;
  showFridgeGlow: boolean;
  showHangerRail: boolean;
};

export function getEquipmentShapeStyle(
  type: string,
  zoneColor: string,
): EquipmentShapeStyle {
  const t = normalizeEquipmentType(type);

  const base: EquipmentShapeStyle = {
    bodyFill: 'rgba(71, 85, 105, 0.85)',
    bodyStroke: zoneColor.startsWith('#') ? zoneColor : '#64748b',
    strokeWidth: 2,
    cornerRadius: 6,
    useEllipse: false,
    showFridgeGlow: false,
    showHangerRail: false,
  };

  switch (t as FloorEquipmentType) {
    case 'fridge':
      return {
        ...base,
        bodyFill: 'rgba(14, 165, 233, 0.25)',
        bodyStroke: '#38bdf8',
        strokeWidth: 3,
        showFridgeGlow: true,
      };
    case 'hanger':
      return {
        ...base,
        bodyFill: 'rgba(51, 65, 85, 0.6)',
        bodyStroke: '#94a3b8',
        cornerRadius: 2,
        showHangerRail: true,
      };
    case 'box':
      return {
        ...base,
        bodyFill: 'rgba(180, 83, 9, 0.35)',
        bodyStroke: '#d97706',
        cornerRadius: 4,
      };
    case 'mannequin':
      return {
        ...base,
        bodyFill: 'rgba(129, 140, 248, 0.35)',
        bodyStroke: '#818cf8',
        useEllipse: true,
      };
    default:
      return base;
  }
}
