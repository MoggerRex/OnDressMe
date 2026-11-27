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

const slotX = (n) => (n - (PER_RAIL - 1) / 2) * SPACING;

export const FLOOR_Z = 0.25; // m: los zapatos van en el piso, un poco hacia el cuarto bajo las prendas colgadas

// Prendas colgadas y zapatos en el piso llevan cada uno su propia fila de lugares (n = lugar dentro de su barra).
// shortcut: pasadas 42 prendas (o 42 zapatos) los lugares se reutilizan (se solapan); agregar barras al llegar a ese límite.
export function placeItems(items, isFloor) {
  const count = { hang: 0, floor: 0 };
  return items.map((item) => {
    const floor = isFloor(item);
    const i = count[floor ? 'floor' : 'hang']++;
    const n = i % PER_RAIL;
    return { rail: FILL[Math.floor(i / PER_RAIL) % FILL.length], x: slotX(n), n, floor };
  });
}

export function railRange(placed, rail, floor = false) {
  const xs = placed.filter((p) => p.rail === rail && p.floor === floor).map((p) => p.x);
  return xs.length ? [Math.min(...xs), Math.max(...xs)] : null;
}

// Punto en el marco local de la barra (x a lo largo, z hacia el cuarto) -> mundo.
export function railToWorld(rail, lx, ly, lz) {
  const { pos, rotY } = RAILS[rail];
  const c = Math.cos(rotY), s = Math.sin(rotY);
  return new THREE.Vector3(pos[0] + lx * c + lz * s, pos[1] + ly, pos[2] - lx * s + lz * c);
}
