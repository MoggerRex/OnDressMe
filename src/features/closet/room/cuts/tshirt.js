import * as THREE from 'three';

const { smoothstep, lerp, clamp } = THREE.MathUtils;

export const label = 'Playera manga corta';

// Pose colgada de una playera de manga corta (modelo en "T"): las mangas giran sobre el hombro hasta colgar.
export function pose({ parts, each, h, top }) {
  // Medidas: ancho del cuerpo (mitad inferior) y largo de manga
  let hw = 0, maxX = 0;
  each((x, y) => {
    maxX = Math.max(maxX, Math.abs(x));
    if (y < top - 0.65 * h) hw = Math.max(hw, Math.abs(x));
  });
  hw = hw || maxX;
  const ratio = (maxX - hw) / h;

  // Caída de mangas: girar sobre el hombro hasta que cuelguen (cortas ~66°, largas ~88° bajo la horizontal)
  const px = hw * 0.9, py = top - 0.07 * h;
  let theta = 0;
  if (ratio > 0.04) {
    let sy = 0, n = 0;
    each((x, y) => { if (Math.abs(x) > 0.92 * maxX) { sy += y; n++; } });
    const slope = Math.atan2(py - sy / n, maxX - px);
    const target = lerp(1.15, 1.54, clamp((ratio - 0.2) / 0.35, 0, 1));
    theta = Math.max(0, target - slope);
  }

  // Bajo de la manga (axila) en la pose original: por debajo de ahí todo es torso (costillas, cintura, dobladillo)
  let sleeveBottom = Infinity;
  each((x, y) => { if (Math.abs(x) > hw * 1.15) sleeveBottom = Math.min(sleeveBottom, y); });
  sleeveBottom -= 0.01;

  const total = parts.reduce((a, { geo }) => a + geo.attributes.position.count, 0);
  const goal = new Float32Array(total * 3);
  // peso de manga con signo (-1..1): 0 en torso; sube suave desde la axila para que la unión manga-torso no se estire
  const side = new Float32Array(total);
  let o = 0;
  parts.forEach(({ geo }) => {
    const p = geo.attributes.position, nr = geo.attributes.normal;
    for (let i = 0; i < p.count; i++, o += 3) {
      let x = p.getX(i), y = p.getY(i);
      const w = smoothstep(Math.abs(x), hw * 0.98, hw * 1.3);
      if (w > 0 && y >= sleeveBottom) side[o / 3] = (x < 0 ? -1 : 1) * smoothstep(w, 0, 0.5);
      if (theta && w) {
        const sg = x < 0 ? -1 : 1, f = -sg * theta * w, cs = Math.cos(f), sn = Math.sin(f);
        const dx = x - sg * px, dy = y - py;
        x = sg * px + dx * cs - dy * sn;
        y = py + dx * sn + dy * cs;
        const nx = nr.getX(i), ny = nr.getY(i);
        nr.setXY(i, nx * cs - ny * sn, nx * sn + ny * cs);
        p.setXY(i, x, y);
      }
      goal[o] = x; goal[o + 1] = y; goal[o + 2] = p.getZ(i);
    }
    nr.needsUpdate = true;
  });

  return { goal, side, hw, sleeveBottom, margin: 0.006 };
}
