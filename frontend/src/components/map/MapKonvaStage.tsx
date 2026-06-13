import React, { useCallback, useRef, useState } from 'react';
import { Layer, Rect, Stage } from 'react-konva';

import type { EquipmentSlot, FloorEquipment, FloorZone } from '../../types/floorPlan';
import { EquipmentKonvaGroup } from './EquipmentKonvaGroup';
import { MapSlotTooltip } from './MapSlotTooltip';

/** react-konva typings lag behind React 19 children prop */
const KonvaStage = Stage as React.FC<{
  width: number;
  height: number;
  children?: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
}>;

const MAP_BG = '#0f172a';
const METER_GRID_PX = 100 * 10;

type Props = {
  zones: FloorZone[];
  mapWidthPx: number;
  mapHeightPx: number;
  pxPerCm: number;
  pendingSlotIds: Set<number>;
  selectedEquipmentId: number | null;
  selectedSlotId: number | null;
  onEquipmentSelect: (equipment: FloorEquipment) => void;
  onSlotSelect: (equipment: FloorEquipment, slot: EquipmentSlot) => void;
};

function MapGridBackground({
  width,
  height,
}: {
  width: number;
  height: number;
}): React.ReactElement {
  const lines: React.ReactElement[] = [];
  for (let x = 0; x <= width; x += METER_GRID_PX) {
    lines.push(
      <Rect
        key={`v-${x}`}
        x={x}
        y={0}
        width={1}
        height={height}
        fill="rgba(148, 163, 184, 0.22)"
        listening={false}
      />,
    );
  }
  for (let y = 0; y <= height; y += METER_GRID_PX) {
    lines.push(
      <Rect
        key={`h-${y}`}
        x={0}
        y={y}
        width={width}
        height={1}
        fill="rgba(148, 163, 184, 0.22)"
        listening={false}
      />,
    );
  }
  return (
    <>
      <Rect width={width} height={height} fill={MAP_BG} listening={false} />
      {lines}
    </>
  );
}

export function MapKonvaStage({
  zones,
  mapWidthPx,
  mapHeightPx,
  pxPerCm,
  pendingSlotIds,
  selectedEquipmentId,
  selectedSlotId,
  onEquipmentSelect,
  onSlotSelect,
}: Props): React.ReactElement {
  const stageRef = useRef<HTMLDivElement>(null);
  const [hoverSlot, setHoverSlot] = useState<EquipmentSlot | null>(null);
  const [pointer, setPointer] = useState({ x: 0, y: 0 });

  const handleSlotHover = useCallback((slot: EquipmentSlot | null, x: number, y: number) => {
    setHoverSlot(slot);
    setPointer({ x, y });
  }, []);

  const stageRect = stageRef.current?.getBoundingClientRect() ?? null;

  return (
    <div
      ref={stageRef}
      className="map-konva-host absolute left-0 top-0"
      style={{ width: mapWidthPx, height: mapHeightPx }}
    >
      <KonvaStage
        width={mapWidthPx}
        height={mapHeightPx}
        className="map-konva-stage"
        style={{ background: 'transparent' }}
      >
        <Layer>
          <MapGridBackground width={mapWidthPx} height={mapHeightPx} />
          {zones.map((zone) =>
            zone.equipment.map((eq) => (
              <EquipmentKonvaGroup
                key={eq.id}
                equipment={eq}
                zoneColor={zone.color || '#475569'}
                pxPerCm={pxPerCm}
                pendingSlotIds={pendingSlotIds}
                selectedEquipmentId={selectedEquipmentId}
                selectedSlotId={selectedSlotId}
                onEquipmentSelect={onEquipmentSelect}
                onSlotSelect={onSlotSelect}
                onSlotHover={handleSlotHover}
              />
            )),
          )}
        </Layer>
      </KonvaStage>
      <MapSlotTooltip
        slot={hoverSlot}
        stageRect={stageRect}
        pointerX={pointer.x}
        pointerY={pointer.y}
      />
    </div>
  );
}
