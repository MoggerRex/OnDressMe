import * as THREE from 'three';

export const RAIL_Y = 2.0;
export const PER_RAIL = 14;
export const SPACING = 0.4; // separación entre ganchos: las prendas no se tocan
export const RAIL_LEN = PER_RAIL * SPACING;
// Orden de navegación con ←/→: izquierda, fondo, derecha. Las prendas miran hacia el centro del cuarto.
export const RAILS = [
  { pos: [-3.7, RAIL_Y, 0], rotY: Math.PI / 2 },
  { pos: [0, RAIL_Y, -2.7], rotY: 0 },
  { pos: [3.7, RAIL_Y, 0], rotY: -Math.PI / 2 },
];
export const START_RAIL = 1;
const FILL = [1, 0, 2]; // la barra del fondo se llena primero

export const slotX = (n) => (n - (PER_RAIL - 1) / 2) * SPACING;
// lugar más cercano a una posición x a lo largo de la barra
export const slotAt = (x) => THREE.MathUtils.clamp(Math.round(x / SPACING + (PER_RAIL - 1) / 2), 0, PER_RAIL - 1);

export const FLOOR_Z = -0.17; // m: los zapatos van en el piso bajo la barra, casi contra la pared (está a -0.3)

// Cada prenda guarda su lugar fijo `slot = { rail, n }` (el usuario la puede arrastrar a otro).
// Prendas colgadas y zapatos tienen cada uno su propia fila de lugares en cada barra.
export function placeItems(items, isFloor) {
  return items.map((item) => ({ rail: item.slot.rail, x: slotX(item.slot.n), n: item.slot.n, floor: isFloor(item) }));
}

// Primer lugar libre de esa fila (la barra del fondo se llena primero).
// shortcut: con las 3 barras llenas (42 prendas o 42 zapatos) los lugares se reutilizan (se solapan); agregar barras al llegar a ese límite.
export function freeSlot(items, floor, isFloor) {
  const taken = new Set(items.filter((i) => isFloor(i) === floor).map((i) => `${i.slot.rail}:${i.slot.n}`));
  for (const rail of FILL) for (let n = 0; n < PER_RAIL; n++) if (!taken.has(`${rail}:${n}`)) return { rail, n };
  return { rail: FILL[0], n: 0 };
}

export function railRange(placed, rail, floor = false) {
  const xs = placed.filter((p) => p.rail === rail && p.floor === floor).map((p) => p.x);
  return xs.length ? [Math.min(...xs), Math.max(...xs)] : null;
}

// Mundo -> marco local de la barra (inverso de railToWorld, solo x/z): { x a lo largo, z hacia el cuarto }
export function worldToRail(rail, v) {
  const { pos, rotY } = RAILS[rail];
  const c = Math.cos(rotY), s = Math.sin(rotY), dx = v.x - pos[0], dz = v.z - pos[2];
  return { x: dx * c - dz * s, z: dx * s + dz * c };
}

// Punto en el marco local de la barra (x a lo largo, z hacia el cuarto) -> mundo.
export function railToWorld(rail, lx, ly, lz) {
  const { pos, rotY } = RAILS[rail];
  const c = Math.cos(rotY), s = Math.sin(rotY);
  return new THREE.Vector3(pos[0] + lx * c + lz * s, pos[1] + ly, pos[2] - lx * s + lz * c);
}
