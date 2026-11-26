import * as THREE from 'three';
import * as tshirt from './tshirt';

const { smoothstep, clamp } = THREE.MathUtils;
const FLARE = 0.1; // leve apertura del brazo hacia afuera al girarlo (~6°)

export const label = 'Playera manga larga';

// Pose colgada de una playera de manga larga. Los modelos de manga larga suelen venir en pose "A" (brazos ya
// inclinados hacia abajo); si el modelo viene en "T", se cuelga como la de manga corta.
export function pose({ parts, each, h, top }) {
  // Torso por franjas de 2 cm: el tramo continuo de tela alrededor del centro (|x| sin huecos de 8 cm o más).
  // Así los puños de una manga larga, que pueden llegar tan abajo como el dobladillo, no cuentan como torso.
  const RB = 0.02, nRows = Math.ceil(h / RB) + 2;
  const rowOf = (y) => clamp(Math.floor((top - y) / RB), 0, nRows - 1);
  const occ = Array.from({ length: nRows }, () => new Set());
  each((x, y) => occ[rowOf(y)].add(Math.floor(Math.abs(x) / 0.01)));
  const runEnd = occ.map((set) => { let i = 0, gap = 0; while (gap < 8 && i < 400) { gap = set.has(i) ? 0 : gap + 1; i++; } return (i - gap) * 0.01; });
  const inTorso = (x, y) => Math.abs(x) < runEnd[rowOf(y)];
  const rowExt = new Float32Array(nRows);
  let hw = 0, maxX = 0;
  each((x, y) => {
    maxX = Math.max(maxX, Math.abs(x));
    if (!inTorso(x, y)) return;
    const r = rowOf(y);
    rowExt[r] = Math.max(rowExt[r], Math.abs(x));
    if (y < top - 0.65 * h) hw = Math.max(hw, Math.abs(x));
  });
  hw = hw || maxX;

  const py = top - 0.07 * h; // altura del pivote del hombro

  // Axila en la pose original: bajando desde arriba, tras pasar por la zona ancha (hombros + mangas pegadas),
  // la primera franja que vuelve al ancho del torso. Por debajo, solo es manga lo que está separado del torso.
  let sleeveBottom = Infinity, wide = false;
  for (let r = 0; r < nRows; r++) {
    if (rowExt[r] > hw * 1.15) wide = true;
    else if (wide && rowExt[r] > 0 && rowExt[r] <= hw * 1.1) { sleeveBottom = top - r * RB - 0.01; break; }
  }

  // Pose "A" (mangas ya inclinadas hacia abajo, p. ej. manga larga): el brazo sale del torso bajo la axila.
  // El brazo entero gira casi rígido sobre el borde del hombro hasta quedar vertical, pegado al costado:
  // la orilla exterior de la manga baja recta desde el hombro (sin abultarse ni inclinarse hacia adentro).
  let below = 0;
  each((x, y) => { if (!inTorso(x, y) && smoothstep(Math.abs(x), hw * 0.98, hw * 1.3) > 0.25 && y < sleeveBottom - 0.1) below++; });
  const aPose = below > 50;
  if (!aPose) return tshirt.pose({ parts, each, h, top });
  const arm = {};
  {
    for (const sg of [1, -1]) {
      let cx = 0, cy = 0, n = 0;
      each((x, y) => { if (sg * x > 0.92 * maxX) { cx += sg * x; cy += y; n++; } });
      const C = [cx / n, cy / n];
      // grosor del brazo: medio ancho horizontal de sus franjas (separadas del torso) corregido por la inclinación
      const lo = new Float32Array(nRows).fill(Infinity), hi = new Float32Array(nRows).fill(-Infinity);
      each((x, y) => {
        if (sg * x <= 0 || inTorso(x, y)) return;
        const r = rowOf(y);
        lo[r] = Math.min(lo[r], sg * x); hi[r] = Math.max(hi[r], sg * x);
      });
      let hs = 0, hn = 0;
      for (let r = 0; r < nRows; r++) if (hi[r] > lo[r]) { hs += (hi[r] - lo[r]) / 2; hn++; }
      const a0 = Math.atan2(py - C[1], C[0] - hw);
      const radius = (hn ? hs / hn : 0.05) * Math.sin(a0);
      const S = [hw + 0.35 * radius, py]; // la manga nace en la orilla del hombro: su borde exterior sigue la línea del hombro
      const ax = C[0] - S[0], ay = C[1] - S[1];
      const alpha = Math.atan2(S[1] - C[1], C[0] - S[0]); // ángulo actual bajo la horizontal
      arm[sg] = { S, ax, ay, len2: ax * ax + ay * ay || 1, rotA: Math.max(0, Math.PI / 2 - FLARE - alpha) };
    }
  }

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
      if (w > 0 && (y >= sleeveBottom || !inTorso(x, y))) side[o / 3] = (x < 0 ? -1 : 1) * smoothstep(w, 0, 0.5);
      if (side[o / 3]) {
        const sg = x < 0 ? -1 : 1, A = arm[sg];
        const t = ((sg * x - A.S[0]) * A.ax + (y - A.S[1]) * A.ay) / A.len2;
        // hombro: el giro entra gradual a lo largo de la parte alta del brazo: la manga sale del hombro con su inclinación
        // y se va curvando hasta quedar vertical, así el hombro cae en curva redondeada hacia afuera (sin hundirse)
        const blendIn = Math.max(Math.abs(side[o / 3]), smoothstep(t, 0.1, 0.3));
        const f = -sg * A.rotA * smoothstep(t, -0.1, 0.45) * blendIn, cs = Math.cos(f), sn = Math.sin(f);
        const dx = x - sg * A.S[0], dy = y - A.S[1];
        x = sg * A.S[0] + dx * cs - dy * sn;
        y = A.S[1] + dx * sn + dy * cs;
        const nx = nr.getX(i), ny = nr.getY(i);
        nr.setXY(i, nx * cs - ny * sn, nx * sn + ny * cs);
        p.setXY(i, x, y);
      }
      goal[o] = x; goal[o + 1] = y; goal[o + 2] = p.getZ(i);
    }
    nr.needsUpdate = true;
  });

  // Pose "A": el brazo del modelo viene algo curvado; tras girarlo, cada franja de la manga se centra bajo el hombro
  // para que caiga recta hasta el puño (sin que la muñeca se doble hacia adentro)
  {
    for (const sg of [1, -1]) {
      const lo = new Float32Array(nRows).fill(Infinity), hi = new Float32Array(nRows).fill(-Infinity);
      for (let v = 0; v < total; v++) {
        if (side[v] * sg < 0.5 || goal[v * 3 + 1] > arm[sg].S[1] - 0.05) continue;
        const r = rowOf(goal[v * 3 + 1]);
        lo[r] = Math.min(lo[r], sg * goal[v * 3]); hi[r] = Math.max(hi[r], sg * goal[v * 3]);
      }
      // eje de la manga por franja (suavizado)
      const axis = new Float32Array(nRows).fill(NaN);
      for (let r = 0; r < nRows; r++) {
        let sum = 0, cnt = 0;
        for (let j = Math.max(0, r - 2); j <= Math.min(nRows - 1, r + 2); j++) {
          if (hi[j] > lo[j]) { sum += (hi[j] + lo[j]) / 2; cnt++; }
        }
        if (cnt) axis[r] = sum / cnt;
      }
      // Bajo la curva del hombro la manga baja VERTICAL desde el punto más afuera de esa curva (como cae una manga real):
      // ni se mete hacia adentro (hundidura) ni se abre hacia afuera
      let ref = -Infinity, peak = 0;
      for (let r = rowOf(arm[sg].S[1]); r <= rowOf(arm[sg].S[1] - 0.15); r++) {
        if (!Number.isNaN(axis[r]) && axis[r] > ref) { ref = axis[r]; peak = r; }
      }
      const shift = new Float32Array(nRows);
      for (let r = peak + 1; r < nRows; r++) {
        if (!Number.isNaN(axis[r]) && ref > -Infinity) shift[r] = Math.max(0, ref - axis[r]);
      }
      for (let v = 0; v < total; v++) {
        if (side[v] * sg <= 0) continue;
        const y = goal[v * 3 + 1];
        goal[v * 3] += sg * shift[rowOf(y)] * Math.abs(side[v]); // solo bajo el punto más ancho del hombro, y solo hacia afuera
      }

    }
  }


  return { goal, side, hw, sleeveBottom, margin: 0.015 };
}
