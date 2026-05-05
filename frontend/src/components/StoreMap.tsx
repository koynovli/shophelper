import React, { useEffect, useMemo, useState } from 'react';
import { MapPinned, Ruler, Warehouse } from 'lucide-react';

import api from '../api';

type Shelf = {
  id: number;
  level: number;
  width: number;
  height: number;
  depth: number;
};

type Equipment = {
  id: number;
  name: string;
  type: string;
  pos_x: number;
  pos_y: number;
  width: number;
  height: number;
  orientation: number;
  shelves: Shelf[];
};

type Zone = {
  id: number;
  name: string;
  color: string;
  equipment: Equipment[];
};

const SCALE = 10; // 1 единица координат -> 10px
const PADDING = 64;

const normalizeColor = (value: string): string => {
  if (!value) {
    return '#334155';
  }
  return /^#([A-Fa-f0-9]{3}|[A-Fa-f0-9]{6})$/.test(value) ? value : '#334155';
};

const withAlpha = (hexColor: string, alpha: number): string => {
  const color = normalizeColor(hexColor).replace('#', '');
  const normalized = color.length === 3
    ? color.split('').map((c) => `${c}${c}`).join('')
    : color;
  const a = Math.max(0, Math.min(255, Math.round(alpha * 255)))
    .toString(16)
    .padStart(2, '0');
  return `#${normalized}${a}`;
};

function StoreMap() {
  const [zones, setZones] = useState<Zone[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    const fetchZones = async (): Promise<void> => {
      try {
        const response = await api.get('/zones/');
        const payload = Array.isArray(response.data) ? response.data : response.data.results ?? [];
        setZones(payload as Zone[]);
      } catch (error) {
        console.error('Не удалось загрузить карту зала:', error);
        setZones([]);
      } finally {
        setLoading(false);
      }
    };

    fetchZones();
  }, []);

  const allEquipment = useMemo(
    () => zones.flatMap((zone) => zone.equipment.map((eq) => ({ ...eq, zoneName: zone.name, zoneColor: zone.color }))),
    [zones],
  );

  const bounds = useMemo(() => {
    if (allEquipment.length === 0) {
      return {
        minX: 0,
        minY: 0,
        width: 1200,
        height: 700,
      };
    }

    const minX = Math.min(...allEquipment.map((eq) => eq.pos_x - eq.width / 2));
    const maxX = Math.max(...allEquipment.map((eq) => eq.pos_x + eq.width / 2));
    const minY = Math.min(...allEquipment.map((eq) => eq.pos_y - eq.height / 2));
    const maxY = Math.max(...allEquipment.map((eq) => eq.pos_y + eq.height / 2));

    return {
      minX,
      minY,
      width: Math.max((maxX - minX) * SCALE + PADDING * 2, 900),
      height: Math.max((maxY - minY) * SCALE + PADDING * 2, 520),
    };
  }, [allEquipment]);

  if (loading) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-slate-900 p-10 text-center text-slate-300 shadow-2xl">
        Loading...
      </div>
    );
  }

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 text-sm text-slate-400">
        <span className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900 px-3 py-1.5">
          <MapPinned className="h-4 w-4 text-emerald-300" />
          Digital Twin
        </span>
        <span className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900 px-3 py-1.5">
          <Ruler className="h-4 w-4 text-indigo-300" />
          Масштаб: 1 ед. = {SCALE}px
        </span>
        <span className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900 px-3 py-1.5">
          <Warehouse className="h-4 w-4 text-amber-300" />
          Объектов: {allEquipment.length}
        </span>
      </div>

      <div className="overflow-auto rounded-2xl border border-slate-800 bg-slate-950 p-4 shadow-2xl">
        <div
          className="relative rounded-xl border border-slate-800 bg-gradient-to-br from-slate-900 to-zinc-900"
          style={{
            width: `${bounds.width}px`,
            height: `${bounds.height}px`,
            backgroundImage:
              'radial-gradient(circle at 1px 1px, rgba(148,163,184,0.18) 1px, transparent 0)',
            backgroundSize: '22px 22px',
          }}
        >
          {zones.map((zone) =>
            zone.equipment.map((eq) => {
              const left = (eq.pos_x - bounds.minX - eq.width / 2) * SCALE + PADDING;
              const top = (eq.pos_y - bounds.minY - eq.height / 2) * SCALE + PADDING;
              const pixelWidth = Math.max(eq.width * SCALE, 14);
              const pixelHeight = Math.max(eq.height * SCALE, 14);
              const zoneColor = normalizeColor(zone.color);

              return (
                <button
                  key={eq.id}
                  type="button"
                  className="group absolute rounded-md border border-slate-700/80 bg-slate-800/70 text-left outline-none transition hover:border-emerald-400 hover:shadow-[0_0_24px_rgba(16,185,129,0.24)]"
                  style={{
                    left: `${left}px`,
                    top: `${top}px`,
                    width: `${pixelWidth}px`,
                    height: `${pixelHeight}px`,
                    transform: `rotate(${eq.orientation || 0}deg)`,
                    transformOrigin: 'center center',
                    backgroundColor: withAlpha(zoneColor, 0.18),
                    borderColor: withAlpha(zoneColor, 0.75),
                  }}
                  onClick={() => {
                    console.log(`Полки стеллажа "${eq.name}"`, eq.shelves ?? []);
                  }}
                >
                  <span className="pointer-events-none absolute inset-0 rounded-md ring-1 ring-inset ring-white/5" />
                  <span className="pointer-events-none absolute left-1 top-1 rounded bg-black/45 px-1.5 py-0.5 text-[10px] font-medium text-slate-100">
                    {eq.type}
                  </span>

                  <span className="pointer-events-none absolute -top-8 left-1/2 z-20 hidden -translate-x-1/2 whitespace-nowrap rounded-md border border-slate-600 bg-slate-950 px-2 py-1 text-xs text-slate-100 shadow-lg group-hover:block">
                    {eq.name}
                  </span>
                </button>
              );
            }),
          )}
        </div>
      </div>
    </section>
  );
}

export default StoreMap;
