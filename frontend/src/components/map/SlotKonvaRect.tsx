import React, { useEffect, useRef } from 'react';
import { Group, Rect, Text } from 'react-konva';
import Konva from 'konva';

import type { EquipmentSlot } from '../../types/floorPlan';
import type { SlotRect } from '../../map/slotLayout';
import { getSlotVisualState } from '../../map/slotVisualState';

type Props = {
  layout: SlotRect;
  slot: EquipmentSlot;
  pendingSlotIds: Set<number>;
  selected: boolean;
  onHover: (slot: EquipmentSlot | null, clientX: number, clientY: number) => void;
  onSelect: (slot: EquipmentSlot) => void;
};

export function SlotKonvaRect({
  layout,
  slot,
  pendingSlotIds,
  selected,
  onHover,
  onSelect,
}: Props): React.ReactElement {
  const groupRef = useRef<Konva.Group>(null);
  const visual = getSlotVisualState(slot, pendingSlotIds);

  useEffect(() => {
    const node = groupRef.current;
    if (!node || !visual.pulse) {
      return;
    }
    const anim = new Konva.Animation((frame: Konva.Frame | undefined) => {
      if (!frame) {
        return;
      }
      const opacity = 0.55 + Math.sin((frame.time * 2 * Math.PI) / 900) * 0.25;
      node.opacity(opacity);
    }, node.getLayer());
    anim.start();
    return () => {
      anim.stop();
    };
  }, [visual.pulse]);

  return (
    <Group
      ref={groupRef}
      x={layout.x}
      y={layout.y}
      onMouseEnter={(e: Konva.KonvaEventObject<MouseEvent>) => {
        const stage = e.target.getStage();
        const pos = stage?.getPointerPosition();
        if (pos) {
          onHover(slot, pos.x, pos.y);
        }
      }}
      onMouseLeave={() => onHover(null, 0, 0)}
      onClick={(e: Konva.KonvaEventObject<MouseEvent>) => {
        e.cancelBubble = true;
        onSelect(slot);
      }}
      onTap={(e: Konva.KonvaEventObject<Event>) => {
        e.cancelBubble = true;
        onSelect(slot);
      }}
    >
      <Rect
        width={layout.width}
        height={layout.height}
        fill={visual.fillHex}
        stroke={selected ? '#38bdf8' : visual.strokeHex}
        strokeWidth={selected ? 2 : 1}
        dash={visual.pulse ? [4, 3] : undefined}
        cornerRadius={2}
      />
      {visual.showAlert ? (
        <Text
          text="!"
          width={layout.width}
          height={layout.height}
          align="center"
          verticalAlign="middle"
          fontSize={Math.min(14, layout.height * 0.6)}
          fill="#fef08a"
          fontStyle="bold"
        />
      ) : null}
    </Group>
  );
}
