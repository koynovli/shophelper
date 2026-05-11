export type Vec2 = { x: number; y: number };

export const SNAP_GRID_PX = 10;

export function snapCoordPx(valuePx: number): number {
  return Math.round(valuePx / SNAP_GRID_PX) * SNAP_GRID_PX;
}

export function snapRotationDeg(deg: number): number {
  let x = Math.round(deg) % 360;
  if (x < 0) {
    x += 360;
  }
  return x;
}

function rotatePoint(px: number, py: number, cos: number, sin: number): Vec2 {
  return {
    x: px * cos - py * sin,
    y: px * sin + py * cos,
  };
}

/** Центр прямоугольника: позиция верхнего левого угла + половина размеров (как в CSS с transform-origin:center). */
export function rectCenterPx(
  leftPx: number,
  topPx: number,
  widthPx: number,
  heightPx: number,
): Vec2 {
  return {
    x: leftPx + widthPx / 2,
    y: topPx + heightPx / 2,
  };
}

export function rotatedRectCornersPx(
  leftPx: number,
  topPx: number,
  widthPx: number,
  heightPx: number,
  rotationDeg: number,
): Vec2[] {
  const cx = leftPx + widthPx / 2;
  const cy = topPx + heightPx / 2;
  const rad = (rotationDeg * Math.PI) / 180;
  const cos = Math.cos(rad);
  const sin = Math.sin(rad);
  const hw = widthPx / 2;
  const hh = heightPx / 2;
  const local: Vec2[] = [
    { x: -hw, y: -hh },
    { x: hw, y: -hh },
    { x: hw, y: hh },
    { x: -hw, y: hh },
  ];
  return local.map((p) => {
    const r = rotatePoint(p.x, p.y, cos, sin);
    return { x: cx + r.x, y: cy + r.y };
  });
}

export function aabbOfRotatedRectPx(
  leftPx: number,
  topPx: number,
  widthPx: number,
  heightPx: number,
  rotationDeg: number,
): { minX: number; maxX: number; minY: number; maxY: number } {
  const corners = rotatedRectCornersPx(leftPx, topPx, widthPx, heightPx, rotationDeg);
  const xs = corners.map((c) => c.x);
  const ys = corners.map((c) => c.y);
  return {
    minX: Math.min(...xs),
    maxX: Math.max(...xs),
    minY: Math.min(...ys),
    maxY: Math.max(...ys),
  };
}

function dot(a: Vec2, b: Vec2): number {
  return a.x * b.x + a.y * b.y;
}

function projectOntoAxis(poly: Vec2[], axis: Vec2): [number, number] {
  let min = dot(poly[0], axis);
  let max = min;
  for (let i = 1; i < poly.length; i++) {
    const p = dot(poly[i], axis);
    min = Math.min(min, p);
    max = Math.max(max, p);
  }
  return [min, max];
}

function overlap1D(a: [number, number], b: [number, number]): boolean {
  return a[1] >= b[0] && b[1] >= a[0];
}

/** SAT для двух выпуклых многоугольников (OBB стеллажа как четырёхугольник). */
export function polygonsIntersect(a: Vec2[], b: Vec2[]): boolean {
  const axes: Vec2[] = [];

  const pushAxes = (poly: Vec2[]): void => {
    for (let i = 0; i < poly.length; i++) {
      const j = (i + 1) % poly.length;
      const edge = { x: poly[j].x - poly[i].x, y: poly[j].y - poly[i].y };
      const normal = { x: -edge.y, y: edge.x };
      const len = Math.hypot(normal.x, normal.y);
      if (len < 1e-9) {
        continue;
      }
      axes.push({ x: normal.x / len, y: normal.y / len });
    }
  };

  pushAxes(a);
  pushAxes(b);

  for (const axis of axes) {
    const pa = projectOntoAxis(a, axis);
    const pb = projectOntoAxis(b, axis);
    if (!overlap1D(pa, pb)) {
      return false;
    }
  }
  return true;
}

export function obbIntersectPx(
  l1: number,
  t1: number,
  w1: number,
  h1: number,
  r1: number,
  l2: number,
  t2: number,
  w2: number,
  h2: number,
  r2: number,
): boolean {
  const polyA = rotatedRectCornersPx(l1, t1, w1, h1, r1);
  const polyB = rotatedRectCornersPx(l2, t2, w2, h2, r2);
  return polygonsIntersect(polyA, polyB);
}

export type EquipmentLayoutPx = {
  id: number;
  left: number;
  top: number;
  width: number;
  height: number;
  rotation: number;
};

/** Магнитное выравнивание по границам AABB (консервативно, быстро для редактора). */
export function magneticSnapTopLeftPx(
  leftPx: number,
  topPx: number,
  widthPx: number,
  heightPx: number,
  rotationDeg: number,
  others: EquipmentLayoutPx[],
  excludeId: number,
  thresholdPx: number,
): { left: number; top: number } {
  let l = leftPx;
  let t = topPx;

  const applyHorizontal = (delta: number): void => {
    if (Math.abs(delta) <= thresholdPx) {
      l += delta;
    }
  };
  const applyVertical = (delta: number): void => {
    if (Math.abs(delta) <= thresholdPx) {
      t += delta;
    }
  };

  for (let pass = 0; pass < 2; pass++) {
    const selfAabb = aabbOfRotatedRectPx(l, t, widthPx, heightPx, rotationDeg);

    for (const o of others) {
      if (o.id === excludeId) {
        continue;
      }
      const otherAabb = aabbOfRotatedRectPx(o.left, o.top, o.width, o.height, o.rotation);

      applyHorizontal(otherAabb.minX - selfAabb.minX);
      applyHorizontal(otherAabb.maxX - selfAabb.maxX);
      applyHorizontal(otherAabb.maxX - selfAabb.minX);
      applyHorizontal(otherAabb.minX - selfAabb.maxX);

      const selfAabb2 = aabbOfRotatedRectPx(l, t, widthPx, heightPx, rotationDeg);
      applyVertical(otherAabb.minY - selfAabb2.minY);
      applyVertical(otherAabb.maxY - selfAabb2.maxY);
      applyVertical(otherAabb.maxY - selfAabb2.minY);
      applyVertical(otherAabb.minY - selfAabb2.maxY);
    }
  }

  return { left: l, top: t };
}
