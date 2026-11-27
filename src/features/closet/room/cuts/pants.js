import * as THREE from 'three';

const { clamp, lerp } = THREE.MathUtils;

export const label = 'Pantalón';

// Los modelos de pantalón vienen con el volumen de unas piernas puestas (cadera, muslos, rodillas). Colgado de la
// pretina, la tela cae plana y recta, así que se ajusta por franjas de 2 cm:
const FLAT = 0.45; // grosor (frente-espalda) que conserva cada franja: la tela de adelante y la de atrás se juntan
const ROW = 0.02;

// Pantalón colgado de la pretina. El gancho, la física de tela y el balanceo los pone cloth.js igual que en playeras.
export function pose({ parts, each, h, top }) {
  const nRows = Math.ceil(h / ROW) + 2;
  const rowOf = (y) => clamp(Math.floor((top - y) / ROW), 0, nRows - 1);
  const W = new Float32Array(nRows), zLo = new Float32Array(nRows).fill(Infinity), zHi = new Float32Array(nRows).fill(-Infinity);
  each((x, y, z) => {
    const r = rowOf(y);
    W[r] = Math.max(W[r], Math.abs(x));
    zLo[r] = Math.min(zLo[r], z); zHi[r] = Math.max(zHi[r], z);
  });
  let last = nRows - 1;
  while (last > 0 && W[last] === 0) last--;
  const avg = (a, b) => { let s = 0, n = 0; for (let r = a; r <= b; r++) if (W[r]) { s += W[r]; n++; } return n ? s / n : 0; };
  const wTop = avg(0, 2), wHem = avg(last - 2, last);

  // silueta recta: de la pretina al dobladillo el ancho cambia en línea recta (sin curva de cadera ni rodilla)
  const fx = new Float32Array(nRows), zMid = new Float32Array(nRows);
  for (let r = 0; r <= last; r++) {
    const target = lerp(wTop, Math.max(wTop, wHem), r / (last || 1));
    fx[r] = W[r] ? clamp(target / W[r], 0.75, 1.1) : 1;
  }
  for (let r = 0; r <= last; r++) {
    let sx = 0, sz = 0, n = 0;
    for (let j = Math.max(0, r - 3); j <= Math.min(last, r + 3); j++) {
      sx += fx[j]; if (zLo[j] <= zHi[j]) { sz += (zLo[j] + zHi[j]) / 2; n++; }
    }
    fx[r] = sx / (Math.min(last, r + 3) - Math.max(0, r - 3) + 1);
    zMid[r] = n ? sz / n : 0;
  }

  const total = parts.reduce((a, { geo }) => a + geo.attributes.position.count, 0);
  const goal = new Float32Array(total * 3);
  let o = 0;
  parts.forEach(({ geo }) => {
    const p = geo.attributes.position;
    for (let i = 0; i < p.count; i++, o += 3) {
      const r = rowOf(p.getY(i));
      // de perfil también cuelga recto: cada franja se centra bajo la pretina (sin la curva de glúteo y rodilla)
      const x = p.getX(i) * fx[r], z = zMid[0] + (p.getZ(i) - zMid[r]) * FLAT;
      p.setX(i, x); p.setZ(i, z);
      goal[o] = x; goal[o + 1] = p.getY(i); goal[o + 2] = z;
    }
    p.needsUpdate = true;
  });
  let hw = 0;
  for (let i = 0; i < total; i++) hw = Math.max(hw, Math.abs(goal[i * 3]));
  // sin mangas: ningún vértice es "manga" y no hay axila. Normales recalculadas sobre la forma aplanada.
  return { goal, side: new Float32Array(total), hw, sleeveBottom: -Infinity, margin: 0.006, smoothNormals: true };
}
