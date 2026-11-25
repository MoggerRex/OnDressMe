import * as THREE from 'three';

export const RAIL_Y = 2.0;
export const PER_RAIL = 18;
export const SPACING = 0.3;
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

// shortcut: pasadas 54 prendas los huecos se reutilizan (se solapan); agregar más barras al llegar a ese límite.
export function placeItems(items) {
  return items.map((_, i) => ({ rail: FILL[Math.floor(i / PER_RAIL) % FILL.length], x: slotX(i % PER_RAIL) }));
}

export function railRange(placed, rail) {
  const xs = placed.filter((p) => p.rail === rail).map((p) => p.x);
  return xs.length ? [Math.min(...xs), Math.max(...xs)] : [0, 0];
}

// Punto en el marco local de la barra (x a lo largo, z hacia el cuarto) -> mundo.
export function railToWorld(rail, lx, ly, lz) {
  const { pos, rotY } = RAILS[rail];
  const c = Math.cos(rotY), s = Math.sin(rotY);
  return new THREE.Vector3(pos[0] + lx * c + lz * s, pos[1] + ly, pos[2] - lx * s + lz * c);
}
