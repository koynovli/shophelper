import React, { useMemo } from 'react';
import { Ellipse, Group, Line, Rect, Text } from 'react-konva';

import { computeSlotRects } from '../../map/slotLayout';
import { getEquipmentShapeStyle } from '../../map/equipmentShapeConfig';
import type { EquipmentSlot, FloorEquipment } from '../../types/floorPlan';
import { SlotKonvaRect } from './SlotKonvaRect';

type Props = {
  equipment: FloorEquipment;
  zoneColor: string;
  pxPerCm: number;
  pendingSlotIds: Set<number>;
  selectedEquipmentId: number | null;
  selectedSlotId: number | null;
  onEquipmentSelect: (equipment: FloorEquipment) => void;
  onSlotSelect: (equipment: FloorEquipment, slot: EquipmentSlot) => void;
  onSlotHover: (slot: EquipmentSlot | null, clientX: number, clientY: number) => void;
};

export function EquipmentKonvaGroup({
  equipment,
  zoneColor,
  pxPerCm,
  pendingSlotIds,
  selectedEquipmentId,
  selectedSlotId,
  onEquipmentSelect,
  onSlotSelect,
  onSlotHover,
}: Props): React.ReactElement {
  const w = Math.max(equipment.width * pxPerCm, 8);
  const h = Math.max(equipment.height * pxPerCm, 8);
  const x = equipment.pos_x * pxPerCm;
  const y = equipment.pos_y * pxPerCm;
  const style = getEquipmentShapeStyle(String(equipment.type), zoneColor);
  const slots = useMemo(() => equipment.slots ?? [], [equipment.slots]);
  const layouts = useMemo(() => computeSlotRects(equipment, slots, w, h), [equipment, slots, w, h]);
  const slotById = useMemo(() => new Map(slots.map((s) => [s.id, s])), [slots]);
  const selectedEq = selectedEquipmentId === equipment.id;

  return (
    <Group
      x={x + w / 2}
      y={y + h / 2}
      offsetX={w / 2}
      offsetY={h / 2}
      rotation={equipment.rotation ?? 0}
      onClick={() => onEquipmentSelect(equipment)}
      onTap={() => onEquipmentSelect(equipment)}
    >
      {style.useEllipse ? (
        <Ellipse
          x={w / 2}
          y={h / 2}
          radiusX={w / 2}
          radiusY={h / 2}
          fill={style.bodyFill}
          stroke={selectedEq ? '#38bdf8' : style.bodyStroke}
          strokeWidth={selectedEq ? 3 : style.strokeWidth}
        />
      ) : (
        <Rect
          width={w}
          height={h}
          fill={style.bodyFill}
          stroke={selectedEq ? '#38bdf8' : style.bodyStroke}
          strokeWidth={selectedEq ? 3 : style.strokeWidth}
          cornerRadius={style.cornerRadius}
          shadowColor={style.showFridgeGlow ? '#0ea5e9' : undefined}
          shadowBlur={style.showFridgeGlow ? 12 : 0}
          shadowOpacity={style.showFridgeGlow ? 0.6 : 0}
        />
      )}
      {style.showHangerRail ? (
        <Line
          points={[4, h / 2, w - 4, h / 2]}
          stroke="#cbd5e1"
          strokeWidth={2}
        />
      ) : null}
      {style.showFridgeGlow ? (
        <Text
          x={w - 18}
          y={4}
          text="❄"
          fontSize={12}
          fill="#7dd3fc"
        />
      ) : null}
      <Text
        x={4}
        y={h - 16}
        width={w - 8}
        text={equipment.name}
        fontSize={10}
        fill="#f8fafc"
        ellipsis
      />
      {layouts.map((layout) => {
        const slot = slotById.get(layout.slotId);
        if (!slot) {
          return null;
        }
        return (
          <SlotKonvaRect
            key={slot.id}
            layout={layout}
            slot={slot}
            pendingSlotIds={pendingSlotIds}
            selected={selectedSlotId === slot.id}
            onHover={onSlotHover}
            onSelect={(s) => onSlotSelect(equipment, s)}
          />
        );
      })}
    </Group>
  );
}
